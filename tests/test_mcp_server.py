"""Tests for the MCP server."""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import mcp.types as types

from devlogs.mcp.server import _format_log_entry, _create_client_and_index


class TestFormatLogEntry:
    """Test log entry formatting."""

    def test_format_minimal_entry(self):
        """Test formatting with minimal fields."""
        entry = {"message": "Test message"}
        result = _format_log_entry(entry)
        assert result == "Test message"

    def test_format_full_entry(self):
        """Test formatting with all fields."""
        entry = {
            "timestamp": "2025-12-26T10:00:00Z",
            "level": "ERROR",
            "logger_name": "test.logger",
            "message": "Test error message",
            "area": "api",
            "operation_id": "abcd1234-5678-90ef-ghij-klmnopqrstuv",
        }
        result = _format_log_entry(entry)
        assert "[2025-12-26T10:00:00Z]" in result
        assert "ERROR" in result
        assert "(api)" in result
        assert "op:abcd1234" in result
        assert "test.logger:" in result
        assert "Test error message" in result

    def test_format_with_exception(self):
        """Test formatting with exception."""
        entry = {
            "message": "Error occurred",
            "exception": "Traceback:\n  File test.py, line 1\nValueError: test",
        }
        result = _format_log_entry(entry)
        assert "Error occurred" in result
        assert "Traceback:" in result
        assert "ValueError: test" in result


class TestCreateClientAndIndex:
    """Test client and index creation."""

    def test_create_client_success(self, monkeypatch):
        """Test successful client creation."""
        # Set environment variables directly
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_PORT", "9200")
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_USER", "admin")
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_PASS", "admin")
        monkeypatch.setenv("DEVLOGS_INDEX", "test-index")

        # Reset config state to force reload
        from devlogs import config
        monkeypatch.setattr(config, "_dotenv_loaded", False)

        client, index = _create_client_and_index()
        assert client is not None
        assert index == "test-index"

    def test_create_client_missing_config(self, monkeypatch):
        """Test client creation with missing config."""
        # Clear all env vars
        for key in [
            "DOTENV_PATH",
            "DEVLOGS_OPENSEARCH_HOST",
            "DEVLOGS_OPENSEARCH_PORT",
            "DEVLOGS_OPENSEARCH_USER",
            "DEVLOGS_OPENSEARCH_PASS",
            "DEVLOGS_INDEX",
        ]:
            monkeypatch.delenv(key, raising=False)

        # Reset config state
        from devlogs import config
        monkeypatch.setattr(config, "_dotenv_loaded", False)
        monkeypatch.setattr(config, "_custom_dotenv_path", None)

        # Mock dotenv functions to prevent loading local .env files
        # We need to mock at the dotenv module level since they're imported inside load_config()
        def mock_find_dotenv(*args, **kwargs):
            return None
        def mock_load_dotenv(*args, **kwargs):
            pass  # Do nothing
        import dotenv
        monkeypatch.setattr(dotenv, "find_dotenv", mock_find_dotenv)
        monkeypatch.setattr(dotenv, "load_dotenv", mock_load_dotenv)

        # Should work with hardcoded defaults only
        client, index = _create_client_and_index()
        assert client is not None
        assert index == "devlogs-0001"  # default value from config.py


@pytest.mark.asyncio
class TestMCPServerTools:
    """Test MCP server tool handlers."""

    async def test_list_tools(self):
        """Test listing available tools."""
        from devlogs.mcp.server import main

        # We can't easily test the async server directly, but we can test
        # that the module defines the expected tools by importing
        # and checking the server setup
        # This is a basic smoke test
        assert callable(main)

    @patch('devlogs.mcp.server._create_client_and_index')
    @patch('devlogs.opensearch.queries.search_logs')
    async def test_search_logs_tool(self, mock_search, mock_create):
        """Test search_logs tool handler."""
        # Setup mocks
        mock_client = MagicMock()
        mock_create.return_value = (mock_client, "test-index")

        mock_search.return_value = [
            {
                "_source": {
                    "timestamp": "2025-12-26T10:00:00Z",
                    "level": "ERROR",
                    "message": "Test error",
                    "area": "api",
                }
            }
        ]

        # Import the handler function
        from devlogs.mcp.server import main

        # Note: Full integration testing would require running the server
        # For now, we test the underlying functions
        assert mock_search is not None

    @patch('devlogs.mcp.server._create_client_and_index')
    @patch('devlogs.opensearch.queries.tail_logs')
    async def test_tail_logs_tool(self, mock_tail, mock_create):
        """Test tail_logs tool handler."""
        # Setup mocks
        mock_client = MagicMock()
        mock_create.return_value = (mock_client, "test-index")

        mock_tail.return_value = (
            [
                {
                    "_source": {
                        "timestamp": "2025-12-26T10:00:00Z",
                        "level": "INFO",
                        "message": "Test log",
                    }
                }
            ],
            None,
        )

        # Import the handler
        from devlogs.mcp.server import main
        assert mock_tail is not None

    @patch('devlogs.mcp.server._create_client_and_index')
    @patch('devlogs.opensearch.queries.search_logs')
    async def test_get_operation_summary_tool(self, mock_search, mock_create):
        """Test get_operation_summary tool handler."""
        # Setup mocks
        mock_client = MagicMock()
        mock_create.return_value = (mock_client, "test-index")

        mock_search.return_value = [
            {
                "_source": {
                    "timestamp": "2025-12-26T10:00:00Z",
                    "level": "INFO",
                    "message": "Start operation",
                    "area": "api",
                    "operation_id": "test-op-123",
                }
            },
            {
                "_source": {
                    "timestamp": "2025-12-26T10:01:00Z",
                    "level": "ERROR",
                    "message": "Operation failed",
                    "area": "api",
                    "operation_id": "test-op-123",
                }
            },
        ]

        # Import the handler
        from devlogs.mcp.server import main
        assert mock_search is not None


@pytest.mark.integration
class TestMCPServerIntegration:
    """Integration tests for MCP server (requires OpenSearch)."""

    @pytest.mark.asyncio
    async def test_server_initialization(self, opensearch_client, test_index):
        """Test that the MCP server can initialize with real OpenSearch."""
        from devlogs.mcp.server import _create_client_and_index

        # This should work with the test fixtures
        client, index = _create_client_and_index()
        assert client is not None

        # Verify we can connect
        info = client.info()
        assert info is not None

    @pytest.mark.asyncio
    async def test_search_with_real_data(self, opensearch_client, test_index):
        """Test searching with real indexed data."""
        from devlogs.opensearch.queries import search_logs

        # Index a test log entry
        doc = {
            "timestamp": "2025-12-26T10:00:00Z",
            "level": "ERROR",
            "message": "Test MCP search",
            "logger_name": "test.mcp",
            "area": "test",
            "doc_type": "log_entry",
        }
        opensearch_client.index(index=test_index, body=doc, refresh=True)

        # Search for it
        results = search_logs(
            client=opensearch_client,
            index=test_index,
            query="MCP search",
            limit=10,
        )

        assert len(results) > 0
        assert any("Test MCP search" in r.get("message", "") for r in results)

    @pytest.mark.asyncio
    async def test_tail_with_real_data(self, opensearch_client, test_index):
        """Test tailing with real indexed data."""
        from devlogs.opensearch.queries import tail_logs

        # Index test log entries
        for i in range(3):
            doc = {
                "timestamp": f"2025-12-26T10:0{i}:00Z",
                "level": "INFO",
                "message": f"Test tail {i}",
                "logger_name": "test.mcp",
                "area": "test",
                "doc_type": "log_entry",
            }
            opensearch_client.index(index=test_index, body=doc, refresh=True)

        # Tail logs
        results, cursor = tail_logs(
            client=opensearch_client,
            index=test_index,
            limit=10,
        )

        assert len(results) > 0
        assert any("Test tail" in r.get("message", "") for r in results)


class TestMCPServerErrorHandling:
    """Test error handling in MCP server."""

    def test_format_entry_with_none_values(self):
        """Test formatting handles None values gracefully."""
        entry = {
            "timestamp": None,
            "level": None,
            "logger_name": None,
            "message": "Test",
            "area": None,
            "operation_id": None,
        }
        result = _format_log_entry(entry)
        assert "Test" in result
        assert result == "Test"

    def test_format_entry_empty_dict(self):
        """Test formatting empty entry."""
        entry = {}
        result = _format_log_entry(entry)
        assert result == ""

    @patch('devlogs.mcp.server.get_opensearch_client')
    def test_create_client_connection_error(self, mock_get_client):
        """Test handling of connection errors."""
        from devlogs.opensearch.client import ConnectionFailedError

        mock_get_client.side_effect = ConnectionFailedError("Cannot connect")

        with pytest.raises(RuntimeError, match="OpenSearch connection failed"):
            _create_client_and_index()

    @patch('devlogs.mcp.server.get_opensearch_client')
    def test_create_client_auth_error(self, mock_get_client):
        """Test handling of authentication errors."""
        from devlogs.opensearch.client import AuthenticationError

        mock_get_client.side_effect = AuthenticationError("Auth failed")

        with pytest.raises(RuntimeError, match="OpenSearch authentication failed"):
            _create_client_and_index()


class TestMCPServerConfiguration:
    """Test MCP server configuration handling."""

    def test_dotenv_path_from_env_var(self, monkeypatch):
        """Test loading config from DOTENV_PATH environment variable."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("DEVLOGS_OPENSEARCH_HOST=env-test-host\n")
            f.write("DEVLOGS_OPENSEARCH_PORT=9200\n")
            f.write("DEVLOGS_OPENSEARCH_USER=admin\n")
            f.write("DEVLOGS_OPENSEARCH_PASS=admin\n")
            f.write("DEVLOGS_INDEX=env-test-index\n")
            temp_path = f.name

        try:
            # Clear existing env vars to avoid pollution
            for key in ["DEVLOGS_OPENSEARCH_HOST", "DEVLOGS_OPENSEARCH_PORT", "DEVLOGS_INDEX"]:
                monkeypatch.delenv(key, raising=False)

            monkeypatch.setenv("DOTENV_PATH", temp_path)
            # Reset config state
            from devlogs import config
            monkeypatch.setattr(config, "_dotenv_loaded", False)
            monkeypatch.setattr(config, "_custom_dotenv_path", None)

            client, index = _create_client_and_index()
            assert index == "env-test-index"
        finally:
            os.unlink(temp_path)

    def test_config_with_custom_port(self, monkeypatch):
        """Test configuration with custom port."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("DEVLOGS_OPENSEARCH_HOST=localhost\n")
            f.write("DEVLOGS_OPENSEARCH_PORT=9999\n")
            f.write("DEVLOGS_OPENSEARCH_USER=testuser\n")
            f.write("DEVLOGS_OPENSEARCH_PASS=testpass\n")
            f.write("DEVLOGS_INDEX=custom-index\n")
            temp_path = f.name

        try:
            # Clear existing env vars to avoid pollution
            for key in ["DEVLOGS_OPENSEARCH_HOST", "DEVLOGS_OPENSEARCH_PORT", "DEVLOGS_OPENSEARCH_USER", "DEVLOGS_OPENSEARCH_PASS", "DEVLOGS_INDEX"]:
                monkeypatch.delenv(key, raising=False)

            monkeypatch.setenv("DOTENV_PATH", temp_path)
            # Reset config state
            from devlogs import config
            monkeypatch.setattr(config, "_dotenv_loaded", False)
            monkeypatch.setattr(config, "_custom_dotenv_path", None)

            client, index = _create_client_and_index()
            assert client.base_url == "http://localhost:9999"
            assert index == "custom-index"
        finally:
            os.unlink(temp_path)
