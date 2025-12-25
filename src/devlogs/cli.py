import signal
import sys

# Handle Ctrl+C gracefully before any other imports
signal.signal(signal.SIGINT, lambda *_: sys.exit(130))

import time
import click
import typer

from .config import load_config
from .formatting import format_timestamp
from .opensearch.client import (
	get_opensearch_client,
	check_connection,
	check_index,
	OpenSearchError,
	ConnectionFailedError,
)
from .opensearch.mappings import LOG_INDEX_TEMPLATE
from .opensearch.queries import normalize_log_entries, search_logs, tail_logs
from .rollup import rollup_operations

app = typer.Typer()


def require_opensearch(check_idx=True):
	"""Get client and verify OpenSearch is accessible. Optionally check index exists."""
	cfg = load_config()
	client = get_opensearch_client()
	try:
		check_connection(client)
		if check_idx:
			check_index(client, cfg.index_logs)
	except OpenSearchError as e:
		typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED), err=True)
		raise typer.Exit(1)
	return client, cfg


@app.command()
def init():
	"""Initialize OpenSearch indices and templates (idempotent)."""
	client, cfg = require_opensearch(check_idx=False)
	# Create or update index templates
	client.indices.put_index_template(name="devlogs-template", body=LOG_INDEX_TEMPLATE)
	# Create initial indices if not exist
	if not client.indices.exists(index=cfg.index_logs):
		client.indices.create(index=cfg.index_logs)
		typer.echo(f"Created index '{cfg.index_logs}'.")
	typer.echo("OpenSearch indices and templates initialized.")


@app.command()
def tail(
	operation_id: str = typer.Option(None, "--operation", "-o"),
	area: str = typer.Option(None, "--area"),
	level: str = typer.Option(None, "--level"),
	since: str = typer.Option(None, "--since"),
	limit: int = typer.Option(20, "--limit"),
	follow: bool = typer.Option(False, "--follow", "-f"),
	utc: bool = typer.Option(False, "--utc", help="Display timestamps in UTC instead of local time"),
):
	"""Tail logs for a given area/operation."""
	import urllib.error

	client, cfg = require_opensearch()
	typer.echo(typer.style(
		f"Connected to OpenSearch, tailing index '{cfg.index_logs}'...",
		fg=typer.colors.GREEN
	), err=True)

	search_after = None
	consecutive_errors = 0
	max_errors = 3
	first_poll = True

	while True:
		try:
			docs, search_after = tail_logs(
				client,
				cfg.index_logs,
				operation_id=operation_id,
				area=area,
				level=level,
				since=since,
				limit=limit,
				search_after=search_after,
			)
			entries = normalize_log_entries(docs)
			consecutive_errors = 0  # Reset on success
		except (ConnectionFailedError, urllib.error.URLError) as e:
			consecutive_errors += 1
			if not follow or consecutive_errors >= max_errors:
				typer.echo(typer.style(
					f"Error: Lost connection to OpenSearch ({consecutive_errors} attempts)",
					fg=typer.colors.RED
				), err=True)
				raise typer.Exit(1)
			typer.echo(typer.style(
				f"Connection error, retrying... ({consecutive_errors}/{max_errors})",
				fg=typer.colors.YELLOW
			), err=True)
			time.sleep(2)
			continue
		except urllib.error.HTTPError as e:
			typer.echo(typer.style(
				f"Error: OpenSearch error: HTTP {e.code} - {e.reason}",
				fg=typer.colors.RED
			), err=True)
			raise typer.Exit(1)
		except Exception as e:
			typer.echo(typer.style(
				f"Error: Unexpected error: {type(e).__name__}: {e}",
				fg=typer.colors.RED
			), err=True)
			raise typer.Exit(1)

		if first_poll and not entries:
			typer.echo(typer.style("No logs found.", dim=True), err=True)
		first_poll = False

		for doc in entries:
			timestamp = format_timestamp(doc.get("timestamp") or "", use_utc=utc)
			entry_level = doc.get("level") or ""
			entry_area = doc.get("area") or ""
			entry_operation = doc.get("operation_id") or ""
			message = doc.get("message") or ""
			typer.echo(f"{timestamp} {entry_level} {entry_area} {entry_operation} {message}")

		if not follow:
			break
		time.sleep(2)


@app.command()
def search(
	q: str = typer.Option("", "--q", help="Search query"),
	area: str = typer.Option(None, "--area"),
	level: str = typer.Option(None, "--level"),
	operation_id: str = typer.Option(None, "--operation", "-o"),
	since: str = typer.Option(None, "--since"),
	limit: int = typer.Option(50, "--limit"),
	follow: bool = typer.Option(False, "--follow", "-f"),
	utc: bool = typer.Option(False, "--utc", help="Display timestamps in UTC instead of local time"),
):
	"""Search logs for a query."""
	import urllib.error

	client, cfg = require_opensearch()
	search_after = None
	consecutive_errors = 0
	max_errors = 3
	first_poll = True

	while True:
		try:
			if follow:
				docs, search_after = tail_logs(
					client,
					cfg.index_logs,
					query=q,
					operation_id=operation_id,
					area=area,
					level=level,
					since=since,
					limit=limit,
					search_after=search_after,
				)
			else:
				docs = search_logs(
					client,
					cfg.index_logs,
					query=q,
					area=area,
					operation_id=operation_id,
					level=level,
					since=since,
					limit=limit,
				)
			entries = normalize_log_entries(docs, limit=limit)
			consecutive_errors = 0
		except (ConnectionFailedError, urllib.error.URLError) as e:
			consecutive_errors += 1
			if not follow or consecutive_errors >= max_errors:
				typer.echo(typer.style(
					f"Error: Lost connection to OpenSearch ({consecutive_errors} attempts)",
					fg=typer.colors.RED
				), err=True)
				raise typer.Exit(1)
			typer.echo(typer.style(
				f"Connection error, retrying... ({consecutive_errors}/{max_errors})",
				fg=typer.colors.YELLOW
			), err=True)
			time.sleep(2)
			continue
		except urllib.error.HTTPError as e:
			typer.echo(typer.style(
				f"Error: OpenSearch error: HTTP {e.code} - {e.reason}",
				fg=typer.colors.RED
			), err=True)
			raise typer.Exit(1)
		except Exception as e:
			typer.echo(typer.style(
				f"Error: Unexpected error: {type(e).__name__}: {e}",
				fg=typer.colors.RED
			), err=True)
			raise typer.Exit(1)

		if first_poll and not entries:
			typer.echo(typer.style("No logs found.", dim=True), err=True)
		first_poll = False

		for doc in entries:
			timestamp = format_timestamp(doc.get("timestamp") or "", use_utc=utc)
			entry_level = doc.get("level") or ""
			entry_area = doc.get("area") or ""
			entry_operation = doc.get("operation_id") or ""
			message = doc.get("message") or ""
			typer.echo(f"{timestamp} {entry_level} {entry_area} {entry_operation} {message}")

		if not follow:
			break
		time.sleep(2)


@app.command()
def rollup(
	since: str = typer.Option(None, "--since", help="Only roll up logs since timestamp"),
):
	"""Roll up any dangling child logs into their parent operations."""
	client, cfg = require_opensearch()
	child_total, parent_total = rollup_operations(client, cfg.index_logs, since=since)
	typer.echo(f"Rollup complete: {child_total} children into {parent_total} parents.")


@app.command()
def demo(
	duration: int = typer.Option(10, "--duration", "-t", help="Duration in seconds"),
	count: int = typer.Option(50, "--count", "-n", help="Number of log entries to generate"),
	defer_rollup: bool = typer.Option(False, "--defer-rollup", help="Defer rollup until you run devlogs rollup"),
):
	"""Generate demo logs to illustrate devlogs capabilities."""
	from .demo import run_demo
	run_demo(duration, count, require_opensearch, defer_rollup)


@app.command()
def serve(
	port: int = typer.Option(8888, "--port", "-p", help="Port to serve on"),
	host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
	reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload for development"),
):
	"""Start the web UI server."""
	import uvicorn
	uvicorn.run("devlogs.web.server:app", host=host, port=port, reload=reload)


def main():
	if len(sys.argv) == 1:
		# No arguments: show help
		command = typer.main.get_command(app)
		ctx = click.Context(command)
		typer.echo(command.get_help(ctx), err=True)
		raise typer.Exit(0)
	try:
		app()
	except typer.Exit:
		raise
	except Exception as e:
		typer.echo(typer.style(
			f"Fatal error: {type(e).__name__}: {e}",
			fg=typer.colors.RED
		), err=True)
		sys.exit(1)

if __name__ == "__main__":
	main()
