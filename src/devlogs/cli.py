import signal
import sys

# Handle Ctrl+C gracefully before any other imports
signal.signal(signal.SIGINT, lambda *_: sys.exit(130))

import json
import time
import click
import typer
from pathlib import Path

from .config import load_config, set_dotenv_path
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
from .retention import cleanup_old_logs, get_retention_stats

app = typer.Typer()

# Global callback to handle --env flag before any command runs
@app.callback(invoke_without_command=True)
def main_callback(
	ctx: typer.Context,
	env: str = typer.Option(None, "--env", help="Path to .env file to load"),
):
	"""devlogs - Developer-focused logging with OpenSearch integration."""
	if env:
		set_dotenv_path(env)


def _format_features(features):
	if not features:
		return ""
	if isinstance(features, dict):
		items = sorted(features.items(), key=lambda item: str(item[0]))
		parts = []
		for key, value in items:
			key_text = str(key)
			if value is None:
				value_text = "null"
			else:
				value_text = str(value)
			parts.append(f"{key_text}={value_text}")
		return f"[{' '.join(parts)}]" if parts else ""
	return f"[{features}]"


def require_opensearch(check_idx=True):
	"""Get client and verify OpenSearch is accessible. Optionally check index exists."""
	cfg = load_config()
	client = get_opensearch_client()
	try:
		check_connection(client)
		if check_idx:
			check_index(client, cfg.index)
	except OpenSearchError as e:
		typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED), err=True)
		raise typer.Exit(1)
	return client, cfg


def _write_json_config(path: Path, root_key: str, server_name: str, server_config: dict) -> None:
	data = {}
	if path.is_file():
		try:
			data = json.loads(path.read_text(encoding="utf-8"))
		except json.JSONDecodeError as exc:
			raise ValueError(f"{path} is not valid JSON: {exc}") from exc
	if not isinstance(data, dict):
		raise ValueError(f"{path} must contain a JSON object.")
	servers = data.get(root_key)
	if servers is None:
		servers = {}
		data[root_key] = servers
	if not isinstance(servers, dict):
		raise ValueError(f"{path} field '{root_key}' must be a JSON object.")
	servers[server_name] = server_config
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _strip_toml_table(text: str, table_name: str) -> str:
	lines = text.splitlines()
	output = []
	skip = False
	for line in lines:
		stripped = line.strip()
		if stripped.startswith("[") and stripped.endswith("]"):
			if stripped == f"[{table_name}]":
				skip = True
				continue
			if skip:
				skip = False
		if not skip:
			output.append(line)
	result = "\n".join(output)
	if text.endswith("\n"):
		result += "\n"
	return result


def _write_codex_config(path: Path, python_path: str) -> None:
	block_lines = [
		"[mcp_servers.devlogs]",
		f'command = "{python_path}"',
		'args = ["-m", "devlogs.mcp.server"]',
	]
	block = "\n".join(block_lines) + "\n"

	text = ""
	if path.is_file():
		text = path.read_text(encoding="utf-8")
		text = _strip_toml_table(text, "mcp_servers.devlogs")
		text = _strip_toml_table(text, "mcp_servers.devlogs.env")
		if text and not text.endswith("\n"):
			text += "\n"
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(text + block, encoding="utf-8")


@app.command()
def init():
	"""Initialize OpenSearch indices and templates (idempotent)."""
	client, cfg = require_opensearch(check_idx=False)
	# Create or update index templates
	client.indices.put_index_template(name="devlogs-template", body=LOG_INDEX_TEMPLATE)
	# Create initial index with explicit mappings if it doesn't exist
	if not client.indices.exists(index=cfg.index):
		client.indices.create(index=cfg.index, body=LOG_INDEX_TEMPLATE["template"])
		typer.echo(f"Created index '{cfg.index}'.")
	typer.echo("OpenSearch indices and templates initialized.")


@app.command()
def initmcp(
	agent: str = typer.Argument(
		...,
		help="Target agent: copilot, claude, codex, or all",
	),
):
	"""Write MCP config for supported agents."""
	agent_key = agent.strip().lower()
	valid_agents = {"copilot", "claude", "codex", "all"}
	if agent_key not in valid_agents:
		typer.echo(typer.style(f"Error: Unknown agent '{agent}'.", fg=typer.colors.RED), err=True)
		raise typer.Exit(1)

	python_path = sys.executable
	root = Path.cwd()
	results = []

	def _write_claude():
		path = root / ".mcp.json"
		config = {
			"command": python_path,
			"args": ["-m", "devlogs.mcp.server"],
		}
		_write_json_config(path, "mcpServers", "devlogs", config)
		results.append(f"Claude: {path}")

	def _write_copilot():
		path = root / ".vscode" / "mcp.json"
		config = {
			"command": python_path,
			"args": ["-m", "devlogs.mcp.server"],
		}
		_write_json_config(path, "servers", "devlogs", config)
		results.append(f"Copilot: {path}")

	def _write_codex():
		path = Path("~/.codex/config.toml").expanduser()
		_write_codex_config(path, python_path)
		results.append(f"Codex: {path}")

	try:
		if agent_key in {"claude", "all"}:
			_write_claude()
		if agent_key in {"copilot", "all"}:
			_write_copilot()
		if agent_key in {"codex", "all"}:
			_write_codex()
	except ValueError as exc:
		typer.echo(typer.style(f"Error: {exc}", fg=typer.colors.RED), err=True)
		raise typer.Exit(1)

	for line in results:
		typer.echo(f"Wrote {line}")

@app.command()
def tail(
	operation_id: str = typer.Option(None, "--operation", "-o"),
	area: str = typer.Option(None, "--area"),
	level: str = typer.Option(None, "--level"),
	since: str = typer.Option(None, "--since"),
	limit: int = typer.Option(20, "--limit"),
	follow: bool = typer.Option(False, "--follow", "-f"),
	verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
	utc: bool = typer.Option(False, "--utc", help="Display timestamps in UTC instead of local time"),
):
	"""Tail logs for a given area/operation."""
	import urllib.error
	import traceback

	client, cfg = require_opensearch()

	def _verbose_echo(message, color=typer.colors.BLUE):
		if verbose:
			typer.echo(typer.style(message, fg=color), err=True)

	def _log_doc_anomalies(docs):
		bad_docs = 0
		bad_entries = 0
		for doc_index, doc in enumerate(docs):
			if not isinstance(doc, dict):
				bad_docs += 1
				if bad_docs <= 3:
					_verbose_echo(
						f"Warning: doc #{doc_index} is {type(doc).__name__}: {doc!r}",
						color=typer.colors.YELLOW,
					)
				continue
			entries = doc.get("entries")
			if isinstance(entries, list):
				for entry_index, entry in enumerate(entries):
					if not isinstance(entry, dict):
						bad_entries += 1
						if bad_entries <= 3:
							_verbose_echo(
								f"Warning: doc #{doc_index} entry #{entry_index} is {type(entry).__name__}: {entry!r}",
								color=typer.colors.YELLOW,
							)
		if bad_docs or bad_entries:
			_verbose_echo(
				f"Anomalies detected: {bad_docs} non-dict docs, {bad_entries} non-dict entries",
				color=typer.colors.YELLOW,
			)

	if verbose:
		parts = []
		if operation_id:
			parts.append(f"operation={operation_id}")
		if area:
			parts.append(f"area={area}")
		if level:
			parts.append(f"level={level}")
		if since:
			parts.append(f"since={since}")
		filter_text = " ".join(parts) if parts else "no filters"
		_verbose_echo(f"Tailing index '{cfg.index}' ({filter_text}), limit={limit}, follow={follow}")

	search_after = None
	consecutive_errors = 0
	max_errors = 3
	first_poll = True

	while True:
		try:
			_verbose_echo(f"Polling OpenSearch with cursor={search_after}")
			docs, search_after = tail_logs(
				client,
				cfg.index,
				operation_id=operation_id,
				area=area,
				level=level,
				since=since,
				limit=limit,
				search_after=search_after,
			)
			_verbose_echo(f"Received {len(docs)} docs, next cursor={search_after}")
			if verbose and docs:
				sample = docs[0]
				if isinstance(sample, dict):
					keys = ", ".join(sorted(sample.keys()))
					_verbose_echo(f"Sample doc keys: {keys}")
				else:
					_verbose_echo(f"Sample doc type: {type(sample).__name__}")
				_log_doc_anomalies(docs)
			try:
				entries = normalize_log_entries(docs)
			except Exception as e:
				_verbose_echo(
					f"normalize_log_entries failed: {type(e).__name__}: {e}",
					color=typer.colors.RED,
				)
				if docs:
					_verbose_echo(f"Sample doc repr: {docs[0]!r}", color=typer.colors.RED)
				raise
			_verbose_echo(f"Normalized {len(entries)} entries")
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
		except OpenSearchError as e:
			typer.echo(typer.style(
				f"Error: {e}",
				fg=typer.colors.RED
			), err=True)
			raise typer.Exit(1)
		except Exception as e:
			if verbose:
				typer.echo(typer.style("Verbose stack trace:", fg=typer.colors.RED), err=True)
				traceback.print_exc()
			typer.echo(typer.style(
				f"Error: Unexpected error: {type(e).__name__}: {e}",
				fg=typer.colors.RED
			), err=True)
			raise typer.Exit(1)

		if first_poll and not entries:
			typer.echo(typer.style("No logs found.", dim=True), err=True)
		first_poll = False

		for entry_index, doc in enumerate(entries):
			try:
				timestamp = format_timestamp(doc.get("timestamp") or "", use_utc=utc)
				entry_level = doc.get("level") or ""
				entry_area = doc.get("area") or ""
				entry_operation = doc.get("operation_id") or ""
				message = doc.get("message") or ""
				features = _format_features(doc.get("features"))
				if features:
					typer.echo(f"{timestamp} {entry_level} {entry_area} {entry_operation} {features} {message}")
				else:
					typer.echo(f"{timestamp} {entry_level} {entry_area} {entry_operation} {message}")
			except Exception as e:
				_verbose_echo(
					f"Failed rendering entry #{entry_index}: {type(e).__name__}: {e}",
					color=typer.colors.RED,
				)
				_verbose_echo(f"Entry repr: {doc!r}", color=typer.colors.RED)
				raise

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
					cfg.index,
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
					cfg.index,
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
		except OpenSearchError as e:
			typer.echo(typer.style(
				f"Error: {e}",
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
			features = _format_features(doc.get("features"))
			if features:
				typer.echo(f"{timestamp} {entry_level} {entry_area} {entry_operation} {features} {message}")
			else:
				typer.echo(f"{timestamp} {entry_level} {entry_area} {entry_operation} {message}")

		if not follow:
			break
		time.sleep(2)


@app.command()
def cleanup(
	dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted without actually deleting"),
	stats: bool = typer.Option(False, "--stats", help="Show retention statistics only"),
):
	"""Clean up old logs based on retention policy.

	Retention tiers:
	- DEBUG logs: Deleted after DEVLOGS_RETENTION_DEBUG_HOURS (default: 6 hours)
	- INFO logs: Deleted after DEVLOGS_RETENTION_INFO_DAYS (default: 7 days)
	- WARNING/ERROR/CRITICAL: Deleted after DEVLOGS_RETENTION_WARNING_DAYS (default: 30 days)
	"""
	client, cfg = require_opensearch()

	if stats:
		# Show retention statistics
		stats_result = get_retention_stats(client, cfg)
		typer.echo("Retention Statistics:")
		typer.echo(f"  Total logs: {stats_result['total_logs']}")
		typer.echo(f"  Hot tier (recent): {stats_result['hot_tier']}")
		typer.echo()
		typer.echo("Eligible for deletion:")
		typer.echo(f"  DEBUG logs (older than {cfg.retention_debug_hours}h): {stats_result['eligible_for_deletion']['debug']}")
		typer.echo(f"  INFO logs (older than {cfg.retention_info_days}d): {stats_result['eligible_for_deletion']['info']}")
		typer.echo(f"  All logs (older than {cfg.retention_warning_days}d): {stats_result['eligible_for_deletion']['all']}")
		return

	# Run cleanup
	if dry_run:
		typer.echo("DRY RUN: No logs will be deleted")
		typer.echo()

	results = cleanup_old_logs(client, cfg, dry_run=dry_run)

	action = "Would delete" if dry_run else "Deleted"
	typer.echo(f"Cleanup results:")
	typer.echo(f"  {action} {results['debug_deleted']} DEBUG logs (older than {cfg.retention_debug_hours}h)")
	typer.echo(f"  {action} {results['info_deleted']} INFO logs (older than {cfg.retention_info_days}d)")
	typer.echo(f"  {action} {results['warning_deleted']} WARNING+ logs (older than {cfg.retention_warning_days}d)")
	typer.echo(f"  Total: {action} {results['debug_deleted'] + results['info_deleted'] + results['warning_deleted']} logs")

	if not dry_run:
		typer.echo(typer.style("Cleanup complete.", fg=typer.colors.GREEN))


@app.command()
def delete(
	index: str = typer.Argument(None, help="Index name to delete (defaults to configured index)"),
	force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
	"""Delete a devlogs index.

	This command permanently deletes an OpenSearch index. By default, it will prompt
	for confirmation unless --force is used.

	Examples:
	  devlogs delete                    # Delete the configured index (with confirmation)
	  devlogs delete my-index           # Delete a specific index (with confirmation)
	  devlogs delete --force            # Delete without confirmation
	  devlogs delete my-index --force   # Delete specific index without confirmation
	"""
	client, cfg = require_opensearch(check_idx=False)

	# Use configured index if none provided
	index_to_delete = index or cfg.index

	# Check if index exists
	if not client.indices.exists(index=index_to_delete):
		typer.echo(typer.style(f"Error: Index '{index_to_delete}' does not exist.", fg=typer.colors.RED), err=True)
		raise typer.Exit(1)

	# Prompt for confirmation unless --force is used
	if not force:
		typer.echo(f"You are about to delete index: {typer.style(index_to_delete, fg=typer.colors.YELLOW, bold=True)}")
		typer.echo(typer.style("This action cannot be undone!", fg=typer.colors.RED, bold=True))
		confirm = typer.confirm("Are you sure you want to continue?")
		if not confirm:
			typer.echo("Delete operation cancelled.")
			raise typer.Exit(0)

	# Delete the index
	try:
		client.indices.delete(index=index_to_delete)
		typer.echo(typer.style(f"Successfully deleted index '{index_to_delete}'.", fg=typer.colors.GREEN))
	except OpenSearchError as e:
		typer.echo(typer.style(f"Error: Failed to delete index: {e}", fg=typer.colors.RED), err=True)
		raise typer.Exit(1)


@app.command()
def demo(
	duration: int = typer.Option(10, "--duration", "-t", help="Duration in seconds"),
	count: int = typer.Option(50, "--count", "-n", help="Number of log entries to generate"),
):
	"""Generate demo logs to illustrate devlogs capabilities."""
	from .demo import run_demo
	run_demo(duration, count, require_opensearch)


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
		return 0
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
