Implement a Python project named `devlogs` (all lowercase) — a developer-focused logging library that writes logs to a **local OpenSearch** instance while integrating with the **standard Python `logging` pipeline**. It must support (1) a reusable Python library, (2) a CLI tool + Linux shell wrapper to run every function, (3) Docker-based OpenSearch setup/config scripts, (4) a lightweight embeddable web UI, and (5) robust tests covering all modules (library, CLI, web UI).

Hard requirements
- Must integrate as a standard `logging.Handler` so existing `logger.debug/info/warn/error` calls work without changes.
- Must allow different handler levels:
  - devlogs handler captures **DEBUG and above** always.
  - console handler (or any other handler) can be configured to show higher levels (e.g., WARNING+).
- Must support two-dimensional organization:
  1) `area` (coarse subsystem like "web", "jobs", etc.)
  2) `operation_id` (correlates all logs for one logical operation like a single request/job run)
- Must support lightweight developer usage:
  - Developers should NOT need to pass operation_id on every log call.
  - Provide a context mechanism that sets operation_id at the start of an operation and automatically injects it into all logs within that context.
- OpenSearch storage model:
  - Use a **parent-child** style relationship *or equivalent approach* that supports:
    - Streaming/real-time visibility of individual log entries as they’re written.
    - A later “roll-up”/aggregation job that summarizes children into a parent operation document.
  - Expect 1–1000 log entries per operation.
- Scrubbing/retention:
  - Keep all levels initially (including DEBUG).
  - After ~24 hours, remove DEBUG-level entries to reduce index size, but retain higher levels longer.
- Everything runnable from command line:
  - Provide a Python CLI (`python -m devlogs ...` or installed console script `devlogs ...`).
  - Provide a small Linux shell wrapper script to invoke the CLI commands.
- Web UI:
  - Must not have features that are absent from the console app (feature parity).
  - Must be embeddable into another website: provide simple HTML/JS that renders logs as divs plus a search box, etc.
  - It can be minimal: single-page UI is fine.
- Tests:
  - Robust set of tests for library behavior, CLI commands, OpenSearch integration boundaries, and web UI endpoints/components.
  - Prefer pytest for Python; include test fixtures and mocks where appropriate.

Tech constraints / assumptions
- Language: Python 3.11+.
- OpenSearch runs locally via Docker (OpenSearch official image).
- Use `opensearch-py` client.
- Keep dependencies light; use `typer` (or `click`) for CLI; `fastapi` (or minimal Flask) for web server.
- Provide good defaults but allow configuration via env vars and CLI flags:
  - OPENSEARCH_HOST, OPENSEARCH_PORT, OPENSEARCH_USER, OPENSEARCH_PASS
  - index names, retention windows, area default, etc.

Deliverables (project structure)
Create a repo with at least:
- `devlogs/`
  - `__init__.py`
  - `config.py` (env/config loading)
  - `context.py` (context vars + context manager for operation_id/area)
  - `handler.py` (logging.Handler that writes to OpenSearch)
  - `opensearch/`
    - `client.py` (client factory + retry/backoff)
    - `mappings.py` (index templates/mappings/settings)
    - `indexing.py` (write log entry docs + parent operation docs)
    - `queries.py` (search APIs used by CLI and web)
  - `rollup.py` (aggregate children -> parent summary)
  - `scrub.py` (delete/prune old DEBUG entries)
  - `cli.py` (CLI entrypoint)
  - `web/`
    - `server.py` (API endpoints used by UI; should mirror CLI)
    - `static/` (embeddable UI: minimal HTML/JS/CSS)
- `scripts/`
  - `opensearch_up.sh` (docker compose up or docker run)
  - `opensearch_down.sh`
  - `opensearch_init.sh` (create indices/templates)
  - `devlogs.sh` (Linux wrapper to call CLI)
  - optionally `docker-compose.yml`
- `tests/`
  - unit tests (context injection, handler formatting, config parsing)
  - integration tests (requires OpenSearch docker; mark as integration)
  - CLI tests (invoke commands, check outputs)
  - web tests (API endpoints + basic static UI asset presence)
- `README.md` with quickstart (docker up, init, use in code, tail/search from CLI, open web UI)

Library behavior details
1) Context injection
- Use `contextvars.ContextVar` to store:
  - operation_id (string)
  - area (string)
- Provide:
  - `devlogs.operation(operation_id: str | None = None, area: str | None = None)` context manager.
    - If operation_id is None, generate a UUID4.
    - Ensure nested contexts work (stack-like behavior).
- Provide helper:
  - `devlogs.set_area(area: str)` and `devlogs.get_area()`
  - `devlogs.get_operation_id()`
- Ensure logs emitted inside the context automatically include `operation_id` and `area` via a logging Filter or within the Handler’s emit() reading ContextVars.

2) Logging handler
- Implement `OpenSearchHandler(logging.Handler)`:
  - Level should default to DEBUG.
  - On emit(record):
    - Build a JSON document with fields:
      - timestamp (UTC ISO8601)
      - level, levelno
      - logger_name
      - message (formatted)
      - pathname, lineno, funcName
      - thread, process
      - exception info (if present) as string/stack
      - area (from contextvar or record.extra)
      - operation_id (from contextvar or record.extra)
      - optional tags/extra fields
    - Index a “log entry” doc as a child of operation_id (or linked via join field).
  - Must be resilient: failures to index should not crash app; implement bounded retry/backoff and a fallback (e.g., drop with internal warning).

OpenSearch design
- Implement index templates and mappings for:
  - `devlogs-logs-*` (log entry docs)
  - `devlogs-ops-*` (operation parent docs) OR a single index with join field if you choose.
- If using join field:
  - parent type: `operation`
  - child type: `log_entry`
  - route all child docs with routing=operation_id so queries are efficient.
- Parent operation doc fields:
  - operation_id
  - area
  - start_time, end_time (optional)
  - counts by level
  - summary fields: last_message, first_message, error_count, etc.
  - optional aggregated text blob of recent messages (bounded)
- Roll-up job:
  - Periodically query for operations with recent child docs and update parent summary:
    - counts per level
    - most recent timestamp
    - maybe store top N recent messages
  - Implement as idempotent.

MCP server
- Add a lightweight, read-only MCP (Model Context Protocol) server to allow a coding LLM to query devlogs during development.
- Module: `devlogs/mcp/server.py`
- Runnable via:
  - `devlogs mcp`
  - `python -m devlogs.mcp.server`
- Default transport: stdio
- Stateless and thin; no business logic
- All MCP tools must call the same query functions used by the CLI and web API
- No MCP-only capabilities
- Errors must be returned as structured MCP errors
- Expose the following MCP tools:
    1) search_logs
    - Args: query?, area?, operation_id?, level?, since?, limit=50
    - Returns: list of log entries:
    timestamp, level, message, logger_name, area, operation_id, pathname, lineno, exception?
    2) tail_logs
    - Args: operation_id?, area?, level?, limit=20
    - Returns: same log entry shape as search_logs
    3) get_operation_summary
    - Args: operation_id (required)
    - Returns: operation_id, area, start_time, end_time, counts_by_level, error_count, last_message

“Streaming / tail” requirement
- OpenSearch doesn’t push changes by default; implement “tail” as polling:
  - CLI command: `devlogs tail --operation <id> [--follow] [--since <timestamp>]`
  - For follow mode, poll every N seconds using a search_after sort on timestamp + tiebreaker id.
  - Print to console as lines; include level, time, message, area, operation_id.
- Also implement:
  - `devlogs search --q "<query>" [--area web] [--level INFO] [--operation <id>] [--last 10m]`
  - Ensure web UI uses the same query API as CLI.

Scrubbing / retention
- Implement a scrubber:
  - CLI command: `devlogs scrub --debug-older-than 24h`
  - It deletes documents where level=DEBUG and timestamp < now - 24h.
  - Keep other levels (don’t delete unless explicitly configured).
  - Implement safely (by query with slices) and log what it did.

CLI commands (minimum)
- `devlogs up` (starts docker OpenSearch if using compose; or prints instructions if not)
- `devlogs init` (create templates/mappings; verify connection)
- `devlogs status` (health check, index existence, doc counts)
- `devlogs tail ...` (see above)
- `devlogs search ...` (see above)
- `devlogs rollup --since 1h` (run roll-up once)
- `devlogs scrub --debug-older-than 24h`
- `devlogs web --port 8088` (run web server that serves API + static UI)
All commands must be runnable via:
- `devlogs mcp` to start the MCP server
- `python -m devlogs ...` and as `devlogs ...` if installed.

Web UI requirements
- Provide an embeddable UI bundle in `devlogs/web/static`:
  - minimal `index.html` + `devlogs.js` that can be embedded (e.g., as an iframe or script include).
  - renders:
    - search box
    - results list of log entries as <div> cards
    - optional filters: area, level, operation_id
- Web server:
  - API endpoints mirroring CLI search/tail functionality:
    - `GET /api/search?q=&area=&level=&operation_id=&since=...`
    - `GET /api/tail?operation_id=&since=&limit=...`
  - Serve static UI under `/ui/`.
- Enforce feature parity: anything the UI does must be possible in CLI; implement shared query functions and call them from both.

Testing requirements
- Use pytest.
- Unit tests:
  - context manager sets/clears operation_id and area, nesting works.
  - handler picks up context, formats fields, and calls indexing function.
  - config/env parsing.
- CLI tests:
  - Use Typer/Click testing utilities to invoke commands.
  - Validate help output and argument handling.
- Integration tests (marked, optional in CI):
  - Spin up OpenSearch via docker (or skip if env not present).
  - Index a few logs; confirm search finds them; confirm scrub deletes DEBUG after setting timestamps.
- Web tests:
  - Start server in test mode and query API endpoints.
  - Confirm `/ui/` assets served.

Implementation notes
- Keep functions small and testable.
- Centralize OpenSearch queries in `devlogs/opensearch/queries.py`.
- Use structured logging internally for devlogs itself (but avoid recursion into the same handler).
- Provide sensible defaults and clear error messages.

Finish by producing:
- Working code for all modules and scripts.
- README with exact commands:
  - start OpenSearch
  - init indices
  - example Python usage showing:
    - adding OpenSearch handler at DEBUG
    - console handler at WARNING
    - setting operation context around a request
  - tail/search examples
  - run web UI

Now implement the full repository.

