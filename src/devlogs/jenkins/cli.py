# CLI commands for Jenkins integration

import sys
import typer

from .core import (
	detect_jenkins_environment,
	run_snapshot,
	JenkinsError,
	JenkinsAuthError,
	JenkinsEnvironmentError,
)
from ..config import load_config, set_dotenv_path, set_url
from ..opensearch.client import (
	get_opensearch_client,
	check_connection,
	check_index,
	OpenSearchError,
)

jenkins_app = typer.Typer(help="Jenkins log commands")

# Common options for jenkins commands
JENKINS_ENV_OPTION = typer.Option(None, "--env", help="Path to .env file to load")
JENKINS_URL_OPTION = typer.Option(None, "--url", "--opensearch-url", help="OpenSearch URL (e.g., opensearchs://user:pass@host:port/index)")


def _apply_common_options(env: str = None, url: str = None):
	"""Apply common options (--env, --url) to configure the client."""
	if env:
		set_dotenv_path(env)
	if url:
		set_url(url)


def _require_opensearch():
	"""Get client and verify OpenSearch is accessible."""
	try:
		cfg = load_config()
		client = get_opensearch_client()
		check_connection(client)
		check_index(client, cfg.index)
	except OpenSearchError as e:
		typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED), err=True)
		raise typer.Exit(1)
	return client, cfg


@jenkins_app.command()
def snapshot(
	build_url: str = typer.Option(
		None,
		"--build-url",
		help="Jenkins build URL (auto-detected from BUILD_URL env var if not specified)",
	),
	verbose: bool = typer.Option(
		False,
		"--verbose",
		"-v",
		help="Enable verbose output",
	),
	env: str = JENKINS_ENV_OPTION,
	url: str = JENKINS_URL_OPTION,
):
	"""Take a one-time snapshot of Jenkins build logs.

	Fetches all currently available logs from a Jenkins build and indexes
	them into OpenSearch. Does not stream logs in real-time.

	This is useful for:
	  - Capturing logs from completed builds
	  - One-time log imports
	  - Debugging without continuous streaming

	For real-time log streaming during builds, use the Devlogs Jenkins Plugin instead.
	See jenkins-plugin/README.md for details.

	Example:
	  devlogs jenkins snapshot --build-url https://jenkins.example.com/job/my-job/123/
	"""
	# Apply common options and verify OpenSearch connection
	_apply_common_options(env, url)
	_require_opensearch()

	try:
		build_info = detect_jenkins_environment(build_url)
	except JenkinsEnvironmentError as e:
		typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED), err=True)
		raise typer.Exit(1)

	if verbose:
		typer.echo(f"Taking snapshot of build: {build_info.build_url}")

	try:
		run_snapshot(build_info, verbose=verbose)
		typer.echo(typer.style("Snapshot complete.", fg=typer.colors.GREEN))
	except JenkinsAuthError as e:
		typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED), err=True)
		raise typer.Exit(1)
	except JenkinsError as e:
		typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED), err=True)
		raise typer.Exit(1)
