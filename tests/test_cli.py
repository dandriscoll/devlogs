import os
import uuid
import pytest

typer = pytest.importorskip("typer")
from typer.testing import CliRunner
from devlogs import cli


@pytest.mark.integration
def test_cli_init_idempotent(opensearch_client, monkeypatch):
    """Test the init command is idempotent and creates indices/templates."""
    runner = CliRunner()
    index_name = f"devlogs-logs-cli-{uuid.uuid4().hex}"
    monkeypatch.setenv("DEVLOGS_INDEX_LOGS", index_name)

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
    assert "Usage" in result.output or "usage" in result.output


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
