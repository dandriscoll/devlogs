# devlogs

A developer-focused logging library for Python with OpenSearch integration.

## Quickstart

1. **Start OpenSearch:**
	```sh
	./scripts/opensearch_up.sh
	```
	Or with Docker Compose:
	```sh
	docker-compose up -d opensearch
	```

2. **Initialize indices/templates:**
	```sh
	./scripts/opensearch_init.sh
	```

3. **Use in Python code:**
	```python
	import logging
	from devlogs.handler import OpenSearchHandler
	from devlogs.context import operation

	handler = OpenSearchHandler(level=logging.DEBUG)
	logging.getLogger().addHandler(handler)
	logging.getLogger().setLevel(logging.DEBUG)

	with operation(area="web"):
		 logging.info("Hello from devlogs!")
	```

4. **Tail logs from CLI:**
	```sh
	PYTHONPATH=src python -m devlogs.cli tail --area web --follow
	# or
	./devlogs tail --area web --follow
	```

	Optional install (enables `devlogs` without the wrapper):
	```sh
	pip install -e .
	devlogs tail --area web --follow
	```

5. **Search logs from CLI:**
	```sh
	python -m devlogs.cli search --q "error" --area web
	```

6. **Run the web UI:**
	```sh
	uvicorn devlogs.web.server:app --port 8088
	# Then open http://localhost:8088/ui/
	```

## Using devlogs in another project

1. **Install devlogs from this repo:**
	```sh
	pip install -e /path/to/devlogs
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
- CLI and Linux shell wrapper
- Minimal embeddable web UI
- Robust tests (pytest)

## Configuration

Environment variables:
- `DEVLOGS_OPENSEARCH_HOST`, `DEVLOGS_OPENSEARCH_PORT`, `DEVLOGS_OPENSEARCH_USER`, `DEVLOGS_OPENSEARCH_PASS`
- `DEVLOGS_INDEX_LOGS`, `DEVLOGS_RETENTION_DEBUG_HOURS`, `DEVLOGS_AREA_DEFAULT`

## Project Structure

- `devlogs/` - Python library
- `scripts/` - Shell scripts for OpenSearch and CLI
- `tests/` - Pytest-based tests

## See Also

- `PROMPT.md` for full requirements
