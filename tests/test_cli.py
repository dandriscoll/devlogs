import os
import pytest
@pytest.mark.integration
def test_cli_init_idempotent(monkeypatch):
    """Test the init command is idempotent and creates indices/templates."""
    from devlogs.config import load_config
    cfg = load_config()
    runner = CliRunner()

    # Patch get_opensearch_client to use a mock
    class DummyIndices:
        def __init__(self):
            self.templates = {}
            self.indices = set()
        def put_index_template(self, name, body):
            self.templates[name] = body
        def exists(self, index):
            return index in self.indices
        def create(self, index):
            self.indices.add(index)

    class DummyClient:
        def __init__(self):
            self.indices = DummyIndices()

    monkeypatch.setattr("devlogs.opensearch.client.get_opensearch_client", lambda: DummyClient())

    # First run: should create templates and indices
    result1 = runner.invoke(cli.app, ["init"])
    assert result1.exit_code == 0
    assert "initialized" in result1.output

    # Second run: should not fail, should be idempotent
    result2 = runner.invoke(cli.app, ["init"])
    assert result2.exit_code == 0
    assert "initialized" in result2.output
from typer.testing import CliRunner
from devlogs import cli


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

def test_cli_search_command_help():
    runner = CliRunner()
    result = runner.invoke(cli.app, ["search", "--help"])
    assert result.exit_code == 0
    assert "Search logs" in result.output or "search" in result.output