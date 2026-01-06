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
	DevlogsDisabledError,
)
from .opensearch.mappings import build_log_index_template, get_template_names
from .opensearch.queries import normalize_log_entries, search_logs, tail_logs, get_last_errors
from .retention import cleanup_old_logs, get_retention_stats

app = typer.Typer()

OLD_TEMPLATE_NAMES = ("devlogs-template", "devlogs-logs-template")

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
	try:
		cfg = load_config()
		client = get_opensearch_client()
		check_connection(client)
		if check_idx:
			check_index(client, cfg.index)
	except OpenSearchError as e:
		typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED), err=True)
		raise typer.Exit(1)
	return client, cfg


def _delete_template_any_variant(client, template_name):
	"""Attempt to delete both composable and legacy templates with the given name."""
	errors = []
	for variant_label, deleter in (
		("composable", client.indices.delete_index_template),
		("legacy", client.indices.delete_template),
	):
		try:
			result = deleter(name=template_name)
			if result:
				return variant_label, []
		except OpenSearchError as exc:
			errors.append((variant_label, exc))
		except Exception as exc:  # pragma: no cover - unexpected errors
			errors.append((variant_label, exc))
	return None, errors


def _write_json_config(
	path: Path,
	root_key: str,
	server_name: str,
	server_config: dict,
) -> str:
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
	existing = servers.get(server_name)
	if existing is not None:
		if existing == server_config:
			return "skipped"
		raise ValueError(
			f"{path} already defines '{server_name}' under '{root_key}'. Update it manually to avoid overwriting."
		)
	servers[server_name] = server_config
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
	return "written"


def _write_codex_config(path: Path, python_path: str) -> str:
	import tomllib

	block_lines = [
		"[mcp_servers.devlogs]",
		f'command = "{python_path}"',
		'args = ["-m", "devlogs.mcp.server"]',
	]
	block = "\n".join(block_lines) + "\n"
	desired = {
		"command": python_path,
		"args": ["-m", "devlogs.mcp.server"],
	}

	text = ""
	if path.is_file():
		text = path.read_text(encoding="utf-8")
		if text.strip():
			try:
				data = tomllib.loads(text)
			except tomllib.TOMLDecodeError as exc:
				raise ValueError(f"{path} is not valid TOML: {exc}") from exc
		else:
			data = {}
		if not isinstance(data, dict):
			raise ValueError(f"{path} must contain a TOML table.")
		existing = data.get("mcp_servers", {}).get("devlogs")
		if existing is not None:
			if (
				isinstance(existing, dict)
				and existing.get("command") == desired["command"]
				and existing.get("args") == desired["args"]
			):
				return "skipped"
			raise ValueError(
				f"{path} already defines mcp_servers.devlogs. Update it manually to avoid overwriting."
			)
		if text and not text.endswith("\n"):
			text += "\n"
	path.parent.mkdir(parents=True, exist_ok=True)
	separator = "\n" if text else ""
	path.write_text(text + separator + block, encoding="utf-8")
	return "written"


@app.command()
def init():
	"""Initialize OpenSearch indices and templates (idempotent)."""
	client, cfg = require_opensearch(check_idx=False)
	# Create or update index templates
	template_body = build_log_index_template(cfg.index)
	template_name, legacy_template_name = get_template_names(cfg.index)
	# Remove any conflicting templates before creating a new one
	names_to_remove = {template_name, legacy_template_name}
	names_to_remove.update(OLD_TEMPLATE_NAMES)
	for name in names_to_remove:
		variant, errors = _delete_template_any_variant(client, name)
		if errors:
			for variant_label, exc in errors:
				typer.echo(
					typer.style(
						f"Warning: failed to remove {variant_label} template '{name}': {exc}",
						fg=typer.colors.YELLOW,
					),
					err=True,
				)
	client.indices.put_index_template(name=template_name, body=template_body)
	# Create initial index with explicit mappings if it doesn't exist
	if not client.indices.exists(index=cfg.index):
		client.indices.create(index=cfg.index, body=template_body["template"])
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
		status = _write_json_config(path, "mcpServers", "devlogs", config)
		results.append((status, "Claude", path))

	def _write_copilot():
		path = root / ".vscode" / "mcp.json"
		config = {
			"command": python_path,
			"args": ["-m", "devlogs.mcp.server"],
		}
		status = _write_json_config(path, "servers", "devlogs", config)
		results.append((status, "Copilot", path))

	def _write_codex():
		path = Path("~/.codex/config.toml").expanduser()
		status = _write_codex_config(path, python_path)
		results.append((status, "Codex", path))

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

	for status, label, path in results:
		if status == "written":
			typer.echo(f"Wrote {label}: {path}")
		else:
			typer.echo(f"Skipped {label}: {path} already configured")

@app.command()
def diagnose():
	"""Diagnose common devlogs setup issues."""
	import os
	import tomllib
	from . import config as config_module

	errors = 0

	def _emit(status: str, message: str) -> None:
		nonlocal errors
		label = {"ok": "OK", "warn": "WARN", "error": "ERROR"}[status]
		color = {
			"ok": typer.colors.GREEN,
			"warn": typer.colors.YELLOW,
			"error": typer.colors.RED,
		}[status]
		if status == "error":
			errors += 1
		typer.echo(f"{typer.style(f'[{label}]', fg=color)} {message}")

	def _resolve_dotenv_path():
		explicit = os.getenv("DOTENV_PATH")
		if explicit:
			return Path(explicit).expanduser(), "DOTENV_PATH"
		custom = getattr(config_module, "_custom_dotenv_path", None)
		if custom:
			return Path(custom).expanduser(), "--env"
		try:
			from dotenv import find_dotenv
		except ModuleNotFoundError:
			return None, None
		found = find_dotenv(usecwd=True)
		if found:
			return Path(found), "auto-discovered"
		return None, None

	def _env_has_devlogs_settings(env: dict) -> bool:
		if not isinstance(env, dict):
			return False
		for key in env.keys():
			if key == "DOTENV_PATH" or key.startswith("DEVLOGS_"):
				return True
		return False

	def _args_has_mcp_module(args) -> bool:
		if isinstance(args, list):
			return "devlogs.mcp.server" in args
		if isinstance(args, str):
			return "devlogs.mcp.server" in args
		return False

	def _check_json_mcp(path: Path, root_key: str, label: str) -> None:
		if not path.is_file():
			_emit("warn", f"MCP ({label}): {path} not found")
			return
		try:
			data = json.loads(path.read_text(encoding="utf-8"))
		except json.JSONDecodeError as exc:
			_emit("error", f"MCP ({label}): invalid JSON in {path}: {exc}")
			return
		if not isinstance(data, dict):
			_emit("error", f"MCP ({label}): {path} must contain a JSON object")
			return
		servers = data.get(root_key)
		if not isinstance(servers, dict):
			_emit("warn", f"MCP ({label}): missing '{root_key}' in {path}")
			return
		server = servers.get("devlogs")
		if not isinstance(server, dict):
			_emit("warn", f"MCP ({label}): devlogs server not configured in {path}")
			return
		issues = []
		if not server.get("command"):
			issues.append("missing command")
		if not _args_has_mcp_module(server.get("args")):
			issues.append("missing devlogs.mcp.server args")
		if not _env_has_devlogs_settings(server.get("env", {})):
			issues.append("missing DOTENV_PATH or DEVLOGS_* env")
		if issues:
			_emit("warn", f"MCP ({label}): devlogs config incomplete in {path} ({', '.join(issues)})")
		else:
			_emit("ok", f"MCP ({label}): devlogs configured in {path}")

	def _check_toml_mcp(path: Path, label: str) -> None:
		if not path.is_file():
			_emit("warn", f"MCP ({label}): {path} not found")
			return
		try:
			data = tomllib.loads(path.read_text(encoding="utf-8"))
		except tomllib.TOMLDecodeError as exc:
			_emit("error", f"MCP ({label}): invalid TOML in {path}: {exc}")
			return
		if not isinstance(data, dict):
			_emit("error", f"MCP ({label}): {path} must contain a TOML table")
			return
		servers = data.get("mcp_servers")
		if not isinstance(servers, dict):
			_emit("warn", f"MCP ({label}): missing 'mcp_servers' in {path}")
			return
		server = servers.get("devlogs")
		if not isinstance(server, dict):
			_emit("warn", f"MCP ({label}): devlogs server not configured in {path}")
			return
		issues = []
		if not server.get("command"):
			issues.append("missing command")
		if not _args_has_mcp_module(server.get("args")):
			issues.append("missing devlogs.mcp.server args")
		if not _env_has_devlogs_settings(server.get("env", {})):
			issues.append("missing DOTENV_PATH or DEVLOGS_* env")
		if issues:
			_emit("warn", f"MCP ({label}): devlogs config incomplete in {path} ({', '.join(issues)})")
		else:
			_emit("ok", f"MCP ({label}): devlogs configured in {path}")

	typer.echo("Devlogs diagnostics:")

	cfg = load_config()
	dotenv_path, dotenv_source = _resolve_dotenv_path()
	if dotenv_path:
		if dotenv_path.is_file():
			if cfg.enabled:
				_emit("ok", f".env: {dotenv_path} ({dotenv_source})")
			else:
				_emit("warn", f".env: {dotenv_path} ({dotenv_source}) found, but no DEVLOGS_* settings detected")
		else:
			_emit("error", f".env: {dotenv_path} ({dotenv_source}) not found")
	else:
		if cfg.enabled:
			_emit("warn", ".env: not found, using environment variables only")
		else:
			_emit("warn", ".env: not found and no DEVLOGS_* settings detected")

	client = None
	connection_ok = False
	try:
		client = get_opensearch_client()
	except DevlogsDisabledError as exc:
		_emit("error", f"OpenSearch: {exc}")
	except OpenSearchError as exc:
		_emit("error", f"OpenSearch: {exc}")
	else:
		try:
			check_connection(client)
			connection_ok = True
			_emit("ok", f"OpenSearch: connected to {cfg.opensearch_host}:{cfg.opensearch_port}")
		except OpenSearchError as exc:
			_emit("error", f"OpenSearch: {exc}")

	index_exists = False
	if client and connection_ok:
		try:
			if client.indices.exists(index=cfg.index):
				_emit("ok", f"Index: {cfg.index} exists")
				index_exists = True
			else:
				_emit("error", f"Index: {cfg.index} does not exist (run 'devlogs init')")
		except OpenSearchError as exc:
			_emit("error", f"Index: {exc}")
		except Exception as exc:
			_emit("error", f"Index: unexpected error: {type(exc).__name__}: {exc}")
	else:
		_emit("warn", "Index: skipped (OpenSearch connection unavailable)")

	if client and connection_ok and index_exists:
		try:
			response = client.count(index=cfg.index)
			count = response.get("count", 0) if isinstance(response, dict) else 0
			if count:
				_emit("ok", f"Logs: found {count} entries")
			else:
				_emit("warn", "Logs: no entries found (index is empty)")
		except OpenSearchError as exc:
			_emit("error", f"Logs: {exc}")
		except Exception as exc:
			_emit("error", f"Logs: unexpected error: {type(exc).__name__}: {exc}")
	else:
		_emit("warn", "Logs: skipped (index unavailable)")

	_check_json_mcp(Path.cwd() / ".mcp.json", "mcpServers", "Claude")
	_check_json_mcp(Path.cwd() / ".vscode" / "mcp.json", "servers", "Copilot")
	_check_toml_mcp(Path.home() / ".codex" / "config.toml", "Codex")

	if errors:
		raise typer.Exit(1)


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
def last_error(
	q: str = typer.Option("", "--q", help="Search query"),
	area: str = typer.Option(None, "--area"),
	operation_id: str = typer.Option(None, "--operation", "-o"),
	since: str = typer.Option(None, "--since"),
	until: str = typer.Option(None, "--until"),
	limit: int = typer.Option(1, "--limit"),
	utc: bool = typer.Option(False, "--utc", help="Display timestamps in UTC instead of local time"),
):
	"""Show the most recent error/critical log entries."""
	import urllib.error

	client, cfg = require_opensearch()

	try:
		docs = get_last_errors(
			client,
			cfg.index,
			query=q,
			area=area,
			operation_id=operation_id,
			since=since,
			until=until,
			limit=limit,
		)
		entries = normalize_log_entries(docs, limit=limit)
	except (ConnectionFailedError, urllib.error.URLError) as e:
		typer.echo(typer.style(
			f"Error: Lost connection to OpenSearch ({e})",
			fg=typer.colors.RED
		), err=True)
		raise typer.Exit(1)
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

	if not entries:
		typer.echo(typer.style("No errors found.", dim=True), err=True)
		return

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
def clean(
	force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
	"""Delete the devlogs index and templates (destructive)."""
	client, cfg = require_opensearch(check_idx=False)
	template_name, legacy_template_name = get_template_names(cfg.index)
	warning_text = (
		"This action permanently deletes all devlogs data by removing the index and its templates."
	)
	typer.echo(typer.style("WARNING: " + warning_text, fg=typer.colors.RED, bold=True))
	if not force:
		confirmed = typer.confirm("Do you want to continue?")
		if not confirmed:
			typer.echo("Clean operation cancelled.")
			raise typer.Exit(0)

	status_code = 0

	try:
		if client.indices.exists(index=cfg.index):
			client.indices.delete(index=cfg.index)
			typer.echo(typer.style(f"Deleted index '{cfg.index}'.", fg=typer.colors.GREEN))
		else:
			typer.echo(typer.style(f"Index '{cfg.index}' not found.", fg=typer.colors.YELLOW))
	except OpenSearchError as e:
		typer.echo(
			typer.style(f"Error deleting index '{cfg.index}': {e}", fg=typer.colors.RED),
			err=True,
		)
		status_code = 1
	except Exception as e:  # pragma: no cover - unexpected errors
		typer.echo(
			typer.style(f"Unexpected error deleting index '{cfg.index}': {e}", fg=typer.colors.RED),
			err=True,
		)
		status_code = 1

	all_template_names = [template_name, legacy_template_name, *OLD_TEMPLATE_NAMES]
	for template in all_template_names:
		variant, errors = _delete_template_any_variant(client, template)
		if variant:
			variant_label = "composable" if variant == "composable" else "legacy"
			typer.echo(
				typer.style(
					f"Deleted {variant_label} template '{template}'.",
					fg=typer.colors.GREEN,
				),
			)
		elif errors:
			for variant_label, exc in errors:
				typer.echo(
					typer.style(
						f"Error deleting {variant_label} template '{template}': {exc}",
						fg=typer.colors.RED,
					),
					err=True,
				)
			status_code = 1
		else:
			typer.echo(
				typer.style(
					f"Template '{template}' not found.",
					fg=typer.colors.YELLOW,
				),
			)

	if status_code != 0:
		raise typer.Exit(status_code)

	typer.echo(typer.style("Clean operation complete.", fg=typer.colors.GREEN))


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
