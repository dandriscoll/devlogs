from typer.testing import CliRunner
from devlogs import cli

def test_cli_runs():
    runner = CliRunner()
    result = runner.invoke(cli.app, [])
    assert result.exit_code == 0 or result.exit_code == 1
