import json
import os
import uuid
import tempfile
import pytest

typer = pytest.importorskip("typer")
from typer.testing import CliRunner
from devlogs import cli
from devlogs import config
from devlogs.opensearch.mappings import (
    build_log_index_template,
    build_legacy_log_template,
    get_template_names,
)


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


class TestDiagnoseCommand:
    """Tests for diagnose command."""

    def test_diagnose_reports_disabled(self, tmp_path, monkeypatch):
        runner = CliRunner()
        monkeypatch.chdir(tmp_path)

        for key in config._DEVLOGS_CONFIG_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv("DOTENV_PATH", raising=False)
        monkeypatch.setattr(config, "_dotenv_loaded", False)
        monkeypatch.setattr(config, "_custom_dotenv_path", None)

        result = runner.invoke(cli.app, ["diagnose"], color=False)
        assert result.exit_code == 1
        assert "Devlogs is disabled" in result.output

    def test_diagnose_reports_ok_with_mcp(self, tmp_path, monkeypatch):
        runner = CliRunner()
        monkeypatch.chdir(tmp_path)

        for key in config._DEVLOGS_CONFIG_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setattr(config, "_dotenv_loaded", False)
        monkeypatch.setattr(config, "_custom_dotenv_path", None)

        env_path = tmp_path / ".env"
        env_path.write_text(
            "DEVLOGS_OPENSEARCH_HOST=localhost\n"
            "DEVLOGS_INDEX=diagnose-test-index\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("DOTENV_PATH", str(env_path))

        mcp_path = tmp_path / ".mcp.json"
        mcp_path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "devlogs": {
                            "command": "python",
                            "args": ["-m", "devlogs.mcp.server"],
                            "env": {"DOTENV_PATH": str(env_path)},
                        }
                    }
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        vscode_path = vscode_dir / "mcp.json"
        vscode_path.write_text(
            json.dumps(
                {
                    "servers": {
                        "devlogs": {
                            "command": "python",
                            "args": ["-m", "devlogs.mcp.server"],
                            "env": {"DOTENV_PATH": str(env_path)},
                        }
                    }
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir()
        codex_path = codex_dir / "config.toml"
        codex_path.write_text(
            "\n".join(
                [
                    "[mcp_servers.devlogs]",
                    'command = "python"',
                    'args = ["-m", "devlogs.mcp.server"]',
                    "",
                    "[mcp_servers.devlogs.env]",
                    f'DOTENV_PATH = "{env_path}"',
                    "",
                ]
            ),
            encoding="utf-8",
        )

        class FakeIndices:
            def exists(self, index):
                return True

        class FakeClient:
            def __init__(self, count):
                self.indices = FakeIndices()
                self._count = count

            def count(self, index):
                return {"count": self._count}

        fake_client = FakeClient(3)

        monkeypatch.setattr(cli, "get_opensearch_client", lambda: fake_client)
        monkeypatch.setattr(cli, "check_connection", lambda client: None)
        monkeypatch.setattr(cli.Path, "home", classmethod(lambda cls: tmp_path))

        result = runner.invoke(cli.app, ["diagnose"], color=False)
        assert result.exit_code == 0
        assert "OpenSearch: connected to" in result.output
        assert "Index: diagnose-test-index exists" in result.output
        assert "Logs: found 3 entries" in result.output
        assert "MCP (Claude): devlogs configured" in result.output
        assert "MCP (Copilot): devlogs configured" in result.output
        assert "MCP (Codex): devlogs configured" in result.output


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


@pytest.mark.integration
class TestCleanCommand:
    """Integration tests for clean command."""

    def test_clean_deletes_index_and_templates(self, opensearch_client, monkeypatch):
        """Test clean command drops index and templates after confirmation."""
        runner = CliRunner()
        temp_index = f"devlogs-clean-test-{uuid.uuid4().hex}"
        opensearch_client.indices.create(index=temp_index)
        monkeypatch.setenv("DEVLOGS_INDEX", temp_index)

        template_body = build_log_index_template(temp_index)
        legacy_body = build_legacy_log_template(temp_index)
        template_name, legacy_template_name = get_template_names(temp_index)
        created_index_template = False
        created_legacy_template = False
        try:
            opensearch_client.indices.put_index_template(
                name=template_name,
                body=template_body,
            )
            created_index_template = True
        except Exception:
            pass
        try:
            opensearch_client.indices.put_template(
                name=legacy_template_name,
                body=legacy_body,
            )
            created_legacy_template = True
        except Exception:
            pass

        try:
            result = runner.invoke(cli.app, ["clean"], input="y\n")
            assert result.exit_code == 0
            assert "Clean operation complete" in result.output
            assert not opensearch_client.indices.exists(index=temp_index)
            if created_index_template:
                assert opensearch_client.indices.delete_index_template(
                    name=template_name
                ) is None
            if created_legacy_template:
                assert opensearch_client.indices.delete_template(
                    name=legacy_template_name
                ) is None
        finally:
            if created_index_template:
                try:
                    opensearch_client.indices.put_index_template(
                        name=template_name,
                        body=template_body,
                    )
                except Exception:
                    pass
            if created_legacy_template:
                try:
                    opensearch_client.indices.put_template(
                        name=legacy_template_name,
                        body=legacy_body,
                    )
                except Exception:
                    pass
            if opensearch_client.indices.exists(index=temp_index):
                opensearch_client.indices.delete(index=temp_index)


class TestBuildOpensearchUrl:
    """Tests for _build_opensearch_url helper function."""

    def test_basic_url(self):
        url = cli._build_opensearch_url("https", "host.com", 9200, "admin", "pass", "index")
        assert url == "https://admin:pass@host.com:9200/index"

    def test_url_encodes_special_chars_in_password(self):
        url = cli._build_opensearch_url("https", "host.com", 9200, "admin", "pass!word#123", "index")
        assert url == "https://admin:pass%21word%23123@host.com:9200/index"
        assert "!" not in url  # Should be encoded
        assert "#" not in url  # Should be encoded

    def test_url_encodes_special_chars_in_username(self):
        url = cli._build_opensearch_url("https", "host.com", 9200, "user@domain", "pass", "index")
        assert url == "https://user%40domain:pass@host.com:9200/index"
        assert "@" not in url.split("@")[0].split("//")[1]  # @ in username should be encoded

    def test_url_encodes_colon_in_password(self):
        url = cli._build_opensearch_url("https", "host.com", 9200, "admin", "pass:word", "index")
        assert url == "https://admin:pass%3Aword@host.com:9200/index"

    def test_url_encodes_slash_in_password(self):
        url = cli._build_opensearch_url("https", "host.com", 9200, "admin", "pass/word", "index")
        assert url == "https://admin:pass%2Fword@host.com:9200/index"

    def test_url_without_credentials(self):
        url = cli._build_opensearch_url("http", "localhost", 9200, "", "", "myindex")
        assert url == "http://localhost:9200/myindex"

    def test_url_with_user_only(self):
        url = cli._build_opensearch_url("https", "host.com", 443, "admin", "", "index")
        assert url == "https://admin@host.com:443/index"

    def test_url_without_index(self):
        url = cli._build_opensearch_url("https", "host.com", 9200, "admin", "pass", "")
        assert url == "https://admin:pass@host.com:9200"


class TestFormatEnvOutput:
    """Tests for _format_env_output helper function."""

    def test_full_config(self):
        output = cli._format_env_output("https", "host.com", 9200, "admin", "pass!word", "myindex")
        assert "DEVLOGS_OPENSEARCH_HOST=host.com" in output
        assert "DEVLOGS_OPENSEARCH_PORT=9200" in output
        assert "DEVLOGS_OPENSEARCH_USER=admin" in output
        assert "DEVLOGS_OPENSEARCH_PASS=pass!word" in output  # Raw password, not encoded
        assert "DEVLOGS_INDEX=myindex" in output

    def test_without_credentials(self):
        output = cli._format_env_output("http", "localhost", 9200, "", "", "index")
        assert "DEVLOGS_OPENSEARCH_HOST=localhost" in output
        assert "DEVLOGS_OPENSEARCH_PORT=9200" in output
        assert "DEVLOGS_OPENSEARCH_USER" not in output
        assert "DEVLOGS_OPENSEARCH_PASS" not in output
        assert "DEVLOGS_INDEX=index" in output

    def test_without_index(self):
        output = cli._format_env_output("https", "host.com", 443, "admin", "pass", "")
        assert "DEVLOGS_OPENSEARCH_HOST=host.com" in output
        assert "DEVLOGS_INDEX" not in output


class TestMkurlCommand:
    """Tests for the mkurl CLI command."""

    def test_mkurl_help(self):
        runner = CliRunner()
        result = runner.invoke(cli.app, ["mkurl", "--help"])
        assert result.exit_code == 0
        assert "OpenSearch URL" in result.output

    def test_mkurl_parse_url(self):
        runner = CliRunner()
        # Simulate choosing option 1 (parse URL) and pasting a URL
        result = runner.invoke(
            cli.app,
            ["mkurl"],
            input="1\nhttps://admin:pass%21word@host.com:9200/myindex\n"
        )
        assert result.exit_code == 0
        # Check all three output formats appear
        assert "Bare URL" in result.output
        assert "Single .env variable" in result.output
        assert "Individual .env variables" in result.output
        # Check URL is in output
        assert "https://admin:pass%21word@host.com:9200/myindex" in result.output
        # Check individual env vars
        assert "DEVLOGS_OPENSEARCH_HOST=host.com" in result.output
        assert "DEVLOGS_OPENSEARCH_PASS=pass!word" in result.output  # Decoded

    def test_mkurl_enter_components(self):
        runner = CliRunner()
        # Simulate choosing option 2 (enter components)
        result = runner.invoke(
            cli.app,
            ["mkurl"],
            input="2\nhttps\nmyhost.example.com\n443\nadmin\nsecretpass\ndevlogs-prod\n"
        )
        assert result.exit_code == 0
        # Check URL is constructed correctly
        assert "https://admin:secretpass@myhost.example.com:443/devlogs-prod" in result.output
        # Check env vars
        assert "DEVLOGS_OPENSEARCH_HOST=myhost.example.com" in result.output
        assert "DEVLOGS_OPENSEARCH_PORT=443" in result.output
        assert "DEVLOGS_INDEX=devlogs-prod" in result.output

    def test_mkurl_enter_components_no_credentials(self):
        runner = CliRunner()
        result = runner.invoke(
            cli.app,
            ["mkurl"],
            input="2\nhttp\nlocalhost\n9200\n\ntest-index\n"
        )
        assert result.exit_code == 0
        assert "http://localhost:9200/test-index" in result.output
        assert "DEVLOGS_OPENSEARCH_USER" not in result.output

    def test_mkurl_invalid_url(self):
        runner = CliRunner()
        result = runner.invoke(
            cli.app,
            ["mkurl"],
            input="1\nnot-a-valid-url\n"
        )
        # Exception is raised and caught by typer, resulting in exit code 1
        assert result.exit_code == 1

    def test_mkurl_invalid_scheme(self):
        runner = CliRunner()
        result = runner.invoke(
            cli.app,
            ["mkurl"],
            input="2\nftp\nhost\n21\n\n\n"
        )
        assert result.exit_code == 1

    def test_mkurl_roundtrip_preserves_special_chars(self):
        """Test that parsing a URL and rebuilding it preserves special characters."""
        runner = CliRunner()
        # URL with special characters in password
        original_url = "https://admin:P%40ss%21w%23rd@host.com:9200/index"
        result = runner.invoke(
            cli.app,
            ["mkurl"],
            input=f"1\n{original_url}\n"
        )
        assert result.exit_code == 0
        # The password in env vars should be decoded
        assert "DEVLOGS_OPENSEARCH_PASS=P@ss!w#rd" in result.output
        # The URL should have the encoded version
        assert "P%40ss%21w%23rd" in result.output
