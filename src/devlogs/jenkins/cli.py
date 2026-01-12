# CLI commands for Jenkins integration

import sys
import typer

from .core import (
	detect_jenkins_environment,
	run_attach,
	run_snapshot,
	stop_attach_process,
	read_state,
	is_process_running,
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

jenkins_app = typer.Typer(help="Jenkins log streaming commands")

# Common options for jenkins commands (use --opensearch-url to avoid conflict with --url for Jenkins build URL)
JENKINS_ENV_OPTION = typer.Option(None, "--env", help="Path to .env file to load")
JENKINS_OPENSEARCH_URL_OPTION = typer.Option(None, "--opensearch-url", help="OpenSearch URL (e.g., https://user:pass@host:port/index)")


def _apply_common_options(env: str = None, opensearch_url: str = None):
	"""Apply common options (--env, --opensearch-url) to configure the client."""
	if env:
		set_dotenv_path(env)
	if opensearch_url:
		set_url(opensearch_url)


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
def attach(
	build_url: str = typer.Option(
		None,
		"--url",
		help="Jenkins build URL (auto-detected from BUILD_URL env var if not specified)",
	),
	background: bool = typer.Option(
		False,
		"--background",
		"-b",
		help="Run in background mode",
	),
	no_resume: bool = typer.Option(
		False,
		"--no-resume",
		help="Don't resume from last indexed offset",
	),
	verbose: bool = typer.Option(
		False,
		"--verbose",
		"-v",
		help="Enable verbose output",
	),
	env: str = JENKINS_ENV_OPTION,
	opensearch_url: str = JENKINS_OPENSEARCH_URL_OPTION,
):
	"""Attach to a Jenkins build and stream logs to OpenSearch.

	This command streams logs from a Jenkins build to OpenSearch in near real-time.
	It automatically detects the current build from Jenkins environment variables
	when run from within a Jenkins Pipeline.

	Required environment variables (when run inside Jenkins):
	  BUILD_URL: Canonical URL of the build (auto-set by Jenkins)

	Optional environment variables:
	  JENKINS_USER: Username for Jenkins authentication
	  JENKINS_TOKEN: API token for Jenkins authentication
	  JOB_NAME, BUILD_NUMBER, BUILD_TAG, BRANCH_NAME, GIT_COMMIT: Build metadata

	Example Jenkinsfile usage:
	  stage('Attach logs') {
	    steps {
	      sh 'devlogs jenkins attach --background'
	    }
	  }
	  post {
	    always {
	      sh 'devlogs jenkins stop || true'
	    }
	  }
	"""
	# Apply common options and verify OpenSearch connection
	_apply_common_options(env, opensearch_url)
	_require_opensearch()

	try:
		build_info = detect_jenkins_environment(build_url)
	except JenkinsEnvironmentError as e:
		typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED), err=True)
		raise typer.Exit(1)

	if verbose:
		typer.echo(f"Attaching to build: {build_info.build_url}")
		if build_info.job_name:
			typer.echo(f"  Job: {build_info.job_name}")
		if build_info.build_number:
			typer.echo(f"  Build: #{build_info.build_number}")
		if build_info.branch_name:
			typer.echo(f"  Branch: {build_info.branch_name}")
		typer.echo(f"  Run ID: {build_info.run_id}")

	try:
		run_attach(
			build_info,
			background=background,
			resume=not no_resume,
			verbose=verbose,
		)
	except JenkinsAuthError as e:
		typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED), err=True)
		raise typer.Exit(1)
	except JenkinsError as e:
		typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED), err=True)
		raise typer.Exit(1)


@jenkins_app.command()
def stop():
	"""Stop a running background attach process.

	This command finds and stops a devlogs jenkins attach process that was
	started with --background in the current workspace.

	Example Jenkinsfile usage:
	  post {
	    always {
	      sh 'devlogs jenkins stop || true'
	    }
	  }
	"""
	state = read_state()

	if not state:
		typer.echo(typer.style("No attach process found.", dim=True))
		raise typer.Exit(0)

	if not is_process_running(state.pid):
		typer.echo(typer.style(
			f"Attach process (PID {state.pid}) is no longer running.",
			dim=True,
		))
		from .core import clear_state
		clear_state()
		raise typer.Exit(0)

	if stop_attach_process():
		typer.echo(typer.style(
			f"Stopped attach process (PID {state.pid})",
			fg=typer.colors.GREEN,
		))
	else:
		typer.echo(typer.style(
			"Failed to stop attach process.",
			fg=typer.colors.RED,
		), err=True)
		raise typer.Exit(1)


@jenkins_app.command()
def snapshot(
	build_url: str = typer.Option(
		None,
		"--url",
		help="Jenkins build URL (auto-detected from BUILD_URL env var if not specified)",
	),
	verbose: bool = typer.Option(
		False,
		"--verbose",
		"-v",
		help="Enable verbose output",
	),
	env: str = JENKINS_ENV_OPTION,
	opensearch_url: str = JENKINS_OPENSEARCH_URL_OPTION,
):
	"""Take a one-time snapshot of Jenkins build logs.

	Unlike 'attach', this command fetches all currently available logs
	and exits immediately. It does not stream logs in real-time.

	This is useful for:
	  - Capturing logs from completed builds
	  - One-time log imports
	  - Debugging without continuous streaming

	Example:
	  devlogs jenkins snapshot --url https://jenkins.example.com/job/my-job/123/
	"""
	# Apply common options and verify OpenSearch connection
	_apply_common_options(env, opensearch_url)
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


@jenkins_app.command()
def status():
	"""Show the status of the current attach process."""
	state = read_state()

	if not state:
		typer.echo(typer.style("No attach process found.", dim=True))
		raise typer.Exit(0)

	running = is_process_running(state.pid)

	typer.echo(f"Attach process status:")
	typer.echo(f"  PID: {state.pid}")
	typer.echo(f"  Status: {typer.style('running', fg=typer.colors.GREEN) if running else typer.style('stopped', fg=typer.colors.RED)}")
	typer.echo(f"  Run ID: {state.run_id}")
	typer.echo(f"  Build URL: {state.build_url}")
	typer.echo(f"  Offset: {state.offset}")
	typer.echo(f"  Started: {state.started_at}")

	if not running:
		from .core import clear_state
		clear_state()
