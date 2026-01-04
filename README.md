# devlogs

A developer-focused logging library for Python with OpenSearch integration.

## Agent Instructions (Copy/Paste)

> Please do the following in this project:
> 1. Install `devlogs` (`pip install devlogs` or add it to `requirements.txt`/`pyproject.toml`).
> 2. Add `DEVLOGS_OPENSEARCH_HOST`, `DEVLOGS_OPENSEARCH_PORT`, `DEVLOGS_OPENSEARCH_USER`, `DEVLOGS_OPENSEARCH_PASS`, and `DEVLOGS_INDEX` to the project `.env` file (or equivalent config). Defaults are `localhost`, `9200`, `admin`, and `devlogs-<projectname>`.
> 3. Add devlogs hooks immediately at the beginning of the application (main entrypoint/startup module) to attach the handler:
>    - `from devlogs.handler import OpenSearchHandler`
>    - `handler = OpenSearchHandler(level=logging.INFO)`
>    - `logging.getLogger().addHandler(handler)`
>    - `logging.getLogger().setLevel(logging.INFO)`
> 4. Run `devlogs init` (inside the virtualenv if one is set up) and verify the index is healthy.
> 5. Ask the user if they want MCP set up; if yes, state which agent you are (`copilot`, `claude`, or `codex`) and run `devlogs initmcp <agent>`.

## OpenSearch Setup (Docker)

If you don't already have OpenSearch running locally:
1. Install Docker (and Docker Compose) for your OS.
2. Copy `docker-compose.example.yaml` to `docker-compose.yaml`.
3. Change the OpenSearch password in the copied file.
4. Start OpenSearch:
	```sh
	docker compose up -d
	```

## Quickstart

1. **Install devlogs:**
	```sh
	pip install devlogs
	```

2. **Start OpenSearch:**
	```sh
	docker-compose up -d opensearch
	```
	Or point `DEVLOGS_OPENSEARCH_*` at an existing cluster.

3. **Initialize indices/templates:**
	```sh
	devlogs init
	```

4. **Use in Python code:**
	```python
	import logging
	from devlogs.handler import OpenSearchHandler
	from devlogs.context import operation

	handler = OpenSearchHandler(level=logging.DEBUG)
	logging.getLogger().addHandler(handler)
	logging.getLogger().setLevel(logging.DEBUG)

	with operation(area="web"):
		 logging.info("Hello from devlogs!", extra={"features": {"user": "alice", "plan": "pro"}})
	```

5. **Tail logs from CLI:**
	```sh
	devlogs tail --area web --follow
	```

6. **Search logs from CLI:**
	```sh
	devlogs search --q "error" --area web
	```

7. **Run the web UI:**
	```sh
	uvicorn devlogs.web.server:app --port 8088
	# Then open http://localhost:8088/ui/
	```

## MCP Agent Setup

If you want MCP set up, identify your agent type and run the matching command from your project root:

```sh
devlogs initmcp copilot
devlogs initmcp claude
devlogs initmcp codex
devlogs initmcp all
```

This writes MCP config files in the standard locations:
- Claude: `.mcp.json`
- Copilot (VS Code): `.vscode/mcp.json`
- Codex: `~/.codex/config.toml`

## Features

- Standard `logging.Handler` for OpenSearch
- Context manager for operation_id/area
- Structured feature pairs on log entries (`extra={"features": {...}}`)
- CLI and Linux shell wrapper
- Minimal embeddable web UI
- Robust tests (pytest)

## Configuration

Environment variables:
- OpenSearch connection: `DEVLOGS_OPENSEARCH_HOST`, `DEVLOGS_OPENSEARCH_PORT`, `DEVLOGS_OPENSEARCH_USER`, `DEVLOGS_OPENSEARCH_PASS`
- Index: `DEVLOGS_INDEX`
- Retention (supports duration strings like `24h`, `7d`): `DEVLOGS_RETENTION_DEBUG`, `DEVLOGS_RETENTION_INFO`, `DEVLOGS_RETENTION_WARNING`

See [.env.example](.env.example) for a complete configuration template.

## Project Structure

- `src/devlogs/` - Python library, CLI, MCP server, and web UI
- `devlogs` - Shell wrapper for local development
- `tests/` - Pytest-based tests

## See Also

- `PROMPT.md` for full requirements
