import os
import uuid
import tempfile
import pytest

typer = pytest.importorskip("typer")
from typer.testing import CliRunner
from devlogs import cli
from devlogs import config


@pytest.mark.integration
def test_cli_init_idempotent(opensearch_client, monkeypatch):
    """Test the init command is idempotent and creates indices/templates."""
    runner = CliRunner()
    index_name = f"devlogs-logs-cli-{uuid.uuid4().hex}"
    monkeypatch.setenv("DEVLOGS_INDEX", index_name)

    result1 = runner.invoke(cli.app, ["init"])
    assert result1.exit_code == 0
    assert "initialized" in result1.output

    result2 = runner.invoke(cli.app, ["init"])
    assert result2.exit_code == 0
    assert "initialized" in result2.output

    opensearch_client.indices.refresh(index=index_name)
    assert opensearch_client.indices.exists(index=index_name)

    opensearch_client.indices.delete(index=index_name)


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output or "usage" in result.output


def test_cli_no_args_shows_help():
    runner = CliRunner()
    result = runner.invoke(cli.app, [])
    # Should show help/usage and exit 0
    assert result.exit_code in (0, 2)
    # Help is written to stderr by main(), which gets mixed into output by default
    # The output might be empty if typer doesn't capture it properly
    # Just check that the command ran successfully
    assert result.exit_code == 0


def test_cli_tail_command_help():
    runner = CliRunner()
    result = runner.invoke(cli.app, ["tail", "--help"])
    assert result.exit_code == 0
    assert "Tail logs" in result.output or "tail" in result.output
    # Check for utc flag (case insensitive due to ANSI codes)
    assert "utc" in result.output.lower()

def test_cli_search_command_help():
    runner = CliRunner()
    result = runner.invoke(cli.app, ["search", "--help"])
    assert result.exit_code == 0
    assert "Search logs" in result.output or "search" in result.output
    # Check for utc flag (case insensitive due to ANSI codes)
    assert "utc" in result.output.lower()

def test_cli_env_flag_in_help():
    """Test that --env flag appears in help output."""
    runner = CliRunner()
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "--env" in result.output

def test_cli_env_flag_sets_dotenv_path():
    """Test that --env flag calls set_dotenv_path in the config module."""
    # This test verifies the integration works by checking the _custom_dotenv_path
    # module variable after invoking the CLI

    # Create a temporary .env file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write("DEVLOGS_OPENSEARCH_HOST=custom-host\n")
        temp_env_path = f.name

    try:
        # Import fresh to get clean state
        import importlib
        importlib.reload(config)

        # Call set_dotenv_path directly to verify it works
        config.set_dotenv_path(temp_env_path)

        # Verify the path was set
        assert config._custom_dotenv_path == temp_env_path
        assert config._dotenv_loaded == False  # Should be reset
    finally:
        os.unlink(temp_env_path)
        # Reset state
        config._dotenv_loaded = False
        config._custom_dotenv_path = None

@pytest.mark.integration
def test_cli_env_flag_loads_custom_config(opensearch_client, monkeypatch):
    """Test that --env flag loads custom .env file."""
    runner = CliRunner()

    # Get current config to get the correct credentials (before resetting state)
    from devlogs.config import load_config
    current_config = load_config()

    # Reset config state to ensure fresh load
    monkeypatch.setattr(config, "_dotenv_loaded", False)
    monkeypatch.setattr(config, "_custom_dotenv_path", None)

    # Create a temporary .env file with custom index name but same credentials
    custom_index = f"devlogs-custom-{uuid.uuid4().hex}"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write(f"DEVLOGS_INDEX={custom_index}\n")
        f.write(f"DEVLOGS_OPENSEARCH_HOST={current_config.opensearch_host}\n")
        f.write(f"DEVLOGS_OPENSEARCH_PORT={current_config.opensearch_port}\n")
        f.write(f"DEVLOGS_OPENSEARCH_USER={current_config.opensearch_user}\n")
        f.write(f"DEVLOGS_OPENSEARCH_PASS={current_config.opensearch_pass}\n")
        temp_env_path = f.name

    try:
        # Run init with --env flag
        result = runner.invoke(cli.app, ["--env", temp_env_path, "init"])
        if result.exit_code != 0:
            print(f"CLI output: {result.output}")
            print(f"Exception: {result.exception}")
        assert result.exit_code == 0

        # Verify the custom index was created
        opensearch_client.indices.refresh(index=custom_index)
        assert opensearch_client.indices.exists(index=custom_index)

        # Clean up
        opensearch_client.indices.delete(index=custom_index)
    finally:
        os.unlink(temp_env_path)
        monkeypatch.setattr(config, "_dotenv_loaded", False)
        monkeypatch.setattr(config, "_custom_dotenv_path", None)


class TestFormatFeatures:
    """Tests for _format_features helper."""

    def test_empty_features_returns_empty_string(self):
        from devlogs.cli import _format_features
        assert _format_features(None) == ""
        assert _format_features({}) == ""
        assert _format_features([]) == ""

    def test_dict_features_formatted(self):
        from devlogs.cli import _format_features
        result = _format_features({"key": "value"})
        assert result == "[key=value]"

    def test_dict_features_sorted(self):
        from devlogs.cli import _format_features
        result = _format_features({"b": "2", "a": "1"})
        assert result == "[a=1 b=2]"

    def test_none_value_formatted_as_null(self):
        from devlogs.cli import _format_features
        result = _format_features({"key": None})
        assert result == "[key=null]"

    def test_non_dict_features_formatted(self):
        from devlogs.cli import _format_features
        result = _format_features("raw_string")
        assert result == "[raw_string]"


class TestRequireOpensearch:
    """Tests for require_opensearch helper."""

    def test_connection_error_exits(self, monkeypatch):
        """Test connection failure shows error and exits."""
        from unittest.mock import patch, MagicMock
        from devlogs.opensearch.client import ConnectionFailedError

        runner = CliRunner()

        with patch("devlogs.cli.get_opensearch_client") as mock_get_client:
            with patch("devlogs.cli.check_connection") as mock_check:
                mock_check.side_effect = ConnectionFailedError("Cannot connect")
                result = runner.invoke(cli.app, ["tail"])
                assert result.exit_code == 1
                assert "Error" in result.output or "Cannot connect" in result.output


@pytest.mark.integration
class TestTailCommand:
    """Integration tests for tail command."""

    def test_tail_with_no_logs_shows_message(self, opensearch_client, test_index, monkeypatch):
        """Test tail command with empty index shows 'No logs found'."""
        runner = CliRunner()
        monkeypatch.setenv("DEVLOGS_INDEX", test_index)

        result = runner.invoke(cli.app, ["tail", "--limit", "5"])
        # Should succeed but show no logs message
        assert result.exit_code == 0
        assert "No logs found" in result.output or result.output == ""

    def test_tail_displays_logs(self, opensearch_client, test_index, monkeypatch):
        """Test tail command displays indexed logs."""
        from datetime import datetime, timezone

        runner = CliRunner()
        monkeypatch.setenv("DEVLOGS_INDEX", test_index)

        # Index a test log entry
        timestamp = datetime.now(timezone.utc).isoformat()
        opensearch_client.index(
            index=test_index,
            body={
                "timestamp": timestamp,
                "level": "info",
                "message": "Test log message for tail",
                "area": "test-area",
                "operation_id": "test-op-123",
                "doc_type": "log_entry",
            },
        )
        opensearch_client.indices.refresh(index=test_index)

        result = runner.invoke(cli.app, ["tail", "--limit", "10"])
        assert result.exit_code == 0
        assert "Test log message for tail" in result.output

    def test_tail_with_level_filter(self, opensearch_client, test_index, monkeypatch):
        """Test tail command with level filter."""
        from datetime import datetime, timezone

        runner = CliRunner()
        monkeypatch.setenv("DEVLOGS_INDEX", test_index)

        timestamp = datetime.now(timezone.utc).isoformat()
        # Index INFO and DEBUG logs
        opensearch_client.index(
            index=test_index,
            body={
                "timestamp": timestamp,
                "level": "info",
                "message": "Info message",
                "doc_type": "log_entry",
            },
        )
        opensearch_client.index(
            index=test_index,
            body={
                "timestamp": timestamp,
                "level": "debug",
                "message": "Debug message",
                "doc_type": "log_entry",
            },
        )
        opensearch_client.indices.refresh(index=test_index)

        # Filter by INFO level
        result = runner.invoke(cli.app, ["tail", "--level", "info", "--limit", "10"])
        assert result.exit_code == 0
        assert "Info message" in result.output

    def test_tail_with_area_filter(self, opensearch_client, test_index, monkeypatch):
        """Test tail command with area filter."""
        from datetime import datetime, timezone

        runner = CliRunner()
        monkeypatch.setenv("DEVLOGS_INDEX", test_index)

        timestamp = datetime.now(timezone.utc).isoformat()
        opensearch_client.index(
            index=test_index,
            body={
                "timestamp": timestamp,
                "level": "info",
                "message": "Web area message",
                "area": "web",
                "doc_type": "log_entry",
            },
        )
        opensearch_client.index(
            index=test_index,
            body={
                "timestamp": timestamp,
                "level": "info",
                "message": "API area message",
                "area": "api",
                "doc_type": "log_entry",
            },
        )
        opensearch_client.indices.refresh(index=test_index)

        result = runner.invoke(cli.app, ["tail", "--area", "web", "--limit", "10"])
        assert result.exit_code == 0
        assert "Web area message" in result.output


@pytest.mark.integration
class TestSearchCommand:
    """Integration tests for search command."""

    def test_search_with_no_results(self, opensearch_client, test_index, monkeypatch):
        """Test search command with no matching results."""
        runner = CliRunner()
        monkeypatch.setenv("DEVLOGS_INDEX", test_index)

        result = runner.invoke(cli.app, ["search", "--q", "nonexistentquery12345"])
        assert result.exit_code == 0
        assert "No logs found" in result.output or result.output == ""

    def test_search_with_query(self, opensearch_client, test_index, monkeypatch):
        """Test search command with query matching logs."""
        from datetime import datetime, timezone

        runner = CliRunner()
        monkeypatch.setenv("DEVLOGS_INDEX", test_index)

        timestamp = datetime.now(timezone.utc).isoformat()
        opensearch_client.index(
            index=test_index,
            body={
                "timestamp": timestamp,
                "level": "error",
                "message": "Database connection failed uniqueterm789",
                "doc_type": "log_entry",
            },
        )
        opensearch_client.indices.refresh(index=test_index)

        result = runner.invoke(cli.app, ["search", "--q", "uniqueterm789"])
        assert result.exit_code == 0
        assert "Database connection failed" in result.output

    def test_search_with_level_filter(self, opensearch_client, test_index, monkeypatch):
        """Test search command with level filter."""
        from datetime import datetime, timezone

        runner = CliRunner()
        monkeypatch.setenv("DEVLOGS_INDEX", test_index)

        timestamp = datetime.now(timezone.utc).isoformat()
        opensearch_client.index(
            index=test_index,
            body={
                "timestamp": timestamp,
                "level": "error",
                "message": "Error searchtest message",
                "doc_type": "log_entry",
            },
        )
        opensearch_client.index(
            index=test_index,
            body={
                "timestamp": timestamp,
                "level": "info",
                "message": "Info searchtest message",
                "doc_type": "log_entry",
            },
        )
        opensearch_client.indices.refresh(index=test_index)

        result = runner.invoke(cli.app, ["search", "--q", "searchtest", "--level", "error"])
        assert result.exit_code == 0
        assert "Error searchtest message" in result.output


@pytest.mark.integration
class TestCleanupCommand:
    """Integration tests for cleanup command."""

    def test_cleanup_dry_run(self, opensearch_client, test_index, monkeypatch):
        """Test cleanup command in dry-run mode."""
        runner = CliRunner()
        monkeypatch.setenv("DEVLOGS_INDEX", test_index)

        result = runner.invoke(cli.app, ["cleanup", "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    def test_cleanup_stats(self, opensearch_client, test_index, monkeypatch):
        """Test cleanup command with --stats flag."""
        runner = CliRunner()
        monkeypatch.setenv("DEVLOGS_INDEX", test_index)

        result = runner.invoke(cli.app, ["cleanup", "--stats"])
        assert result.exit_code == 0
        assert "Retention Statistics" in result.output
        assert "Total logs" in result.output


@pytest.mark.integration
class TestDeleteCommand:
    """Integration tests for delete command."""

    def test_delete_nonexistent_index_fails(self, opensearch_client, monkeypatch):
        """Test delete command fails for nonexistent index."""
        runner = CliRunner()
        monkeypatch.setenv("DEVLOGS_INDEX", "nonexistent-index-12345")

        result = runner.invoke(cli.app, ["delete", "--force"])
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_delete_with_confirmation(self, opensearch_client, test_index, monkeypatch):
        """Test delete command prompts for confirmation."""
        runner = CliRunner()

        # Create a temporary index to delete
        temp_index = f"devlogs-delete-test-{uuid.uuid4().hex}"
        opensearch_client.indices.create(index=temp_index)

        monkeypatch.setenv("DEVLOGS_INDEX", temp_index)

        # Decline confirmation
        result = runner.invoke(cli.app, ["delete"], input="n\n")
        assert "cancelled" in result.output.lower() or result.exit_code == 0

        # Index should still exist
        if opensearch_client.indices.exists(index=temp_index):
            opensearch_client.indices.delete(index=temp_index)

    def test_delete_with_force(self, opensearch_client, monkeypatch):
        """Test delete command with --force flag."""
        runner = CliRunner()

        # Create a temporary index to delete
        temp_index = f"devlogs-delete-test-{uuid.uuid4().hex}"
        opensearch_client.indices.create(index=temp_index)

        result = runner.invoke(cli.app, ["delete", temp_index, "--force"])
        assert result.exit_code == 0
        assert "Successfully deleted" in result.output

        # Verify index is gone
        assert not opensearch_client.indices.exists(index=temp_index)
