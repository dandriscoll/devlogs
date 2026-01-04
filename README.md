# devlogs

A developer-focused logging library for Python with OpenSearch integration.

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

## Using devlogs in another project

1. **Install devlogs:**
	```sh
	pip install devlogs
	```

2. **Add the diagnostics handler:**
	```python
	import logging
	from devlogs.handler import DiagnosticsHandler
	from devlogs.opensearch.client import get_opensearch_client
	from devlogs.context import operation

	client = get_opensearch_client()
	handler = DiagnosticsHandler(opensearch_client=client, index_name="devlogs-0001")
	logging.getLogger().addHandler(handler)
	logging.getLogger().setLevel(logging.DEBUG)

	with operation(area="web"):
		 logging.info("request started")
	```

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
