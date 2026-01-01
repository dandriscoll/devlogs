"""Tests for the retention module."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from devlogs.retention import (
    cleanup_old_logs,
    get_retention_stats,
    _delete_by_level_and_time,
    _delete_by_time,
)


class TestDeleteByLevelAndTime:
    """Tests for _delete_by_level_and_time helper."""

    def test_dry_run_counts_only(self):
        """Test dry_run mode only counts documents."""
        mock_client = MagicMock()
        mock_client.count.return_value = {"count": 42}
        cutoff = datetime.now(timezone.utc)

        result = _delete_by_level_and_time(
            mock_client, "test-index", "debug", cutoff, dry_run=True
        )

        assert result == 42
        mock_client.count.assert_called_once()
        mock_client.delete_by_query.assert_not_called()
        # Verify query structure
        call_args = mock_client.count.call_args
        query = call_args.kwargs["body"]["query"]
        assert query["bool"]["filter"][0] == {"term": {"level": "debug"}}

    def test_delete_mode_deletes_documents(self):
        """Test delete mode actually deletes documents."""
        mock_client = MagicMock()
        mock_client.delete_by_query.return_value = {"deleted": 15}
        cutoff = datetime.now(timezone.utc)

        result = _delete_by_level_and_time(
            mock_client, "test-index", "info", cutoff, dry_run=False
        )

        assert result == 15
        mock_client.delete_by_query.assert_called_once()
        mock_client.count.assert_not_called()
        # Verify delete_by_query call
        call_args = mock_client.delete_by_query.call_args
        assert call_args.kwargs["index"] == "test-index"
        assert call_args.kwargs["conflicts"] == "proceed"
        assert call_args.kwargs["refresh"] is False

    def test_query_includes_level_and_timestamp(self):
        """Test query filters by level and timestamp."""
        mock_client = MagicMock()
        mock_client.count.return_value = {"count": 0}
        cutoff = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        _delete_by_level_and_time(
            mock_client, "test-index", "warning", cutoff, dry_run=True
        )

        call_args = mock_client.count.call_args
        query = call_args.kwargs["body"]["query"]
        filters = query["bool"]["filter"]
        assert {"term": {"level": "warning"}} in filters
        # Check timestamp filter
        timestamp_filter = next(f for f in filters if "range" in f)
        assert "lt" in timestamp_filter["range"]["timestamp"]


class TestDeleteByTime:
    """Tests for _delete_by_time helper."""

    def test_dry_run_counts_only(self):
        """Test dry_run mode only counts documents."""
        mock_client = MagicMock()
        mock_client.count.return_value = {"count": 100}
        cutoff = datetime.now(timezone.utc)

        result = _delete_by_time(mock_client, "test-index", cutoff, dry_run=True)

        assert result == 100
        mock_client.count.assert_called_once()
        mock_client.delete_by_query.assert_not_called()

    def test_delete_mode_deletes_documents(self):
        """Test delete mode actually deletes documents."""
        mock_client = MagicMock()
        mock_client.delete_by_query.return_value = {"deleted": 50}
        cutoff = datetime.now(timezone.utc)

        result = _delete_by_time(mock_client, "test-index", cutoff, dry_run=False)

        assert result == 50
        mock_client.delete_by_query.assert_called_once()

    def test_query_only_filters_by_timestamp(self):
        """Test query only filters by timestamp (all levels)."""
        mock_client = MagicMock()
        mock_client.count.return_value = {"count": 0}
        cutoff = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        _delete_by_time(mock_client, "test-index", cutoff, dry_run=True)

        call_args = mock_client.count.call_args
        query = call_args.kwargs["body"]["query"]
        # Should be a simple range query, not a bool
        assert "range" in query
        assert "timestamp" in query["range"]


class TestCleanupOldLogs:
    """Tests for cleanup_old_logs function."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config."""
        config = MagicMock()
        config.index = "devlogs-logs"
        config.retention_debug_hours = 6
        config.retention_info_days = 7
        config.retention_warning_days = 30
        return config

    def test_dry_run_returns_counts(self, mock_config):
        """Test dry_run mode returns counts without deleting."""
        mock_client = MagicMock()
        mock_client.count.side_effect = [
            {"count": 10},  # debug
            {"count": 20},  # info
            {"count": 5},   # warning+
        ]

        result = cleanup_old_logs(mock_client, mock_config, dry_run=True)

        assert result["debug_deleted"] == 10
        assert result["info_deleted"] == 20
        assert result["warning_deleted"] == 5
        assert result["dry_run"] is True
        mock_client.delete_by_query.assert_not_called()

    def test_delete_mode_deletes_all_tiers(self, mock_config):
        """Test delete mode processes all three tiers."""
        mock_client = MagicMock()
        mock_client.delete_by_query.side_effect = [
            {"deleted": 100},  # debug
            {"deleted": 50},   # info
            {"deleted": 10},   # warning+
        ]

        result = cleanup_old_logs(mock_client, mock_config, dry_run=False)

        assert result["debug_deleted"] == 100
        assert result["info_deleted"] == 50
        assert result["warning_deleted"] == 10
        assert result["dry_run"] is False
        assert mock_client.delete_by_query.call_count == 3

    def test_uses_correct_cutoff_times(self, mock_config):
        """Test retention cutoffs are calculated correctly."""
        mock_client = MagicMock()
        mock_client.delete_by_query.return_value = {"deleted": 0}

        with patch("devlogs.retention.datetime") as mock_datetime:
            # Fix "now" to a known time
            fixed_now = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
            mock_datetime.now.return_value = fixed_now
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            cleanup_old_logs(mock_client, mock_config, dry_run=False)

        # Check the queries for correct cutoff times
        calls = mock_client.delete_by_query.call_args_list

        # Debug: 6 hours ago
        debug_query = calls[0].kwargs["body"]["query"]
        debug_cutoff_str = debug_query["bool"]["filter"][1]["range"]["timestamp"]["lt"]
        assert "2024-06-15T06:00:00" in debug_cutoff_str

        # Info: 7 days ago
        info_query = calls[1].kwargs["body"]["query"]
        info_cutoff_str = info_query["bool"]["filter"][1]["range"]["timestamp"]["lt"]
        assert "2024-06-08T12:00:00" in info_cutoff_str

        # Warning: 30 days ago
        warning_query = calls[2].kwargs["body"]["query"]
        warning_cutoff_str = warning_query["range"]["timestamp"]["lt"]
        assert "2024-05-16T12:00:00" in warning_cutoff_str

    def test_uses_config_index(self, mock_config):
        """Test uses index from config."""
        mock_config.index = "custom-index"
        mock_client = MagicMock()
        mock_client.delete_by_query.return_value = {"deleted": 0}

        cleanup_old_logs(mock_client, mock_config, dry_run=False)

        for call in mock_client.delete_by_query.call_args_list:
            assert call.kwargs["index"] == "custom-index"


class TestGetRetentionStats:
    """Tests for get_retention_stats function."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config."""
        config = MagicMock()
        config.index = "devlogs-logs"
        config.retention_debug_hours = 6
        config.retention_info_days = 7
        config.retention_warning_days = 30
        return config

    def test_returns_all_stats(self, mock_config):
        """Test returns complete statistics structure."""
        mock_client = MagicMock()
        mock_client.count.side_effect = [
            {"count": 1000},  # total
            {"count": 800},   # hot tier
            {"count": 50},    # debug eligible
            {"count": 100},   # info eligible
            {"count": 30},    # all old
        ]

        result = get_retention_stats(mock_client, mock_config)

        assert result["total_logs"] == 1000
        assert result["hot_tier"] == 800
        assert result["eligible_for_deletion"]["debug"] == 50
        assert result["eligible_for_deletion"]["info"] == 100
        assert result["eligible_for_deletion"]["all"] == 30

    def test_makes_five_count_queries(self, mock_config):
        """Test makes correct number of count queries."""
        mock_client = MagicMock()
        mock_client.count.return_value = {"count": 0}

        get_retention_stats(mock_client, mock_config)

        assert mock_client.count.call_count == 5

    def test_handles_missing_count_field(self, mock_config):
        """Test handles missing count field gracefully."""
        mock_client = MagicMock()
        mock_client.count.return_value = {}  # Missing "count" key

        result = get_retention_stats(mock_client, mock_config)

        assert result["total_logs"] == 0
        assert result["hot_tier"] == 0


class TestRetentionIntegration:
    """Integration tests for retention (requires OpenSearch)."""

    @pytest.mark.integration
    def test_cleanup_with_real_opensearch(self, opensearch_client, test_index):
        """Test cleanup works with real OpenSearch."""
        from devlogs.config import load_config

        # Index some test documents with old timestamps
        old_timestamp = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        for i in range(5):
            opensearch_client.index(
                index=test_index,
                body={
                    "timestamp": old_timestamp,
                    "level": "debug",
                    "message": f"old debug {i}",
                    "doc_type": "log_entry",
                },
            )
        opensearch_client.indices.refresh(index=test_index)

        # Create config with short retention
        config = MagicMock()
        config.index = test_index
        config.retention_debug_hours = 1  # 1 hour - should delete our 24h old logs
        config.retention_info_days = 7
        config.retention_warning_days = 30

        # Dry run first
        result = cleanup_old_logs(opensearch_client, config, dry_run=True)
        assert result["debug_deleted"] >= 5

        # Actual cleanup
        result = cleanup_old_logs(opensearch_client, config, dry_run=False)
        assert result["debug_deleted"] >= 5
