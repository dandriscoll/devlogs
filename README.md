# devlogs

<p align="center">
  <img src="devlogs.png" alt="devlogs logo" width="200">
</p>

A developer-focused logging library for Python based on OpenSearch.

## Step 1: Get OpenSearch running

If you don't have OpenSearch running and you want to stand one up:
1. Install Docker (and Docker Compose) for your OS.
2. Copy `docker-compose.example.yaml` to `docker-compose.yaml`.
3. Change the OpenSearch password in the copied file.
4. Start OpenSearch:
	```sh
	docker compose up -d
	```

## Step 2: Copy/paste these instructions into your coding agent

> Please do the following in this project:
> 1. Install `devlogs` as a dev dependency (`pip install devlogs` or add it to `requirements-dev.txt`/`pyproject.toml` optional dependencies).
> 2. Add `DEVLOGS_OPENSEARCH_HOST`, `DEVLOGS_OPENSEARCH_PORT`, `DEVLOGS_OPENSEARCH_USER`, `DEVLOGS_OPENSEARCH_PASS`, and `DEVLOGS_INDEX` to the project `.env` file (or equivalent config). Defaults are `localhost`, `9200`, `admin`, and `devlogs-<projectname>`.
> 3. Add devlogs hooks at the beginning of the application (main entrypoint/startup module), wrapped in an environment check so it only runs in development:
>    ```python
>    import os
>    import logging
>    if os.getenv("ENVIRONMENT") != "production":
>        from devlogs.handler import DevlogsHandler
>        from devlogs.build_info import resolve_build_info
>
>        # Resolve build info (reads .build.json or generates)
>        build_info = resolve_build_info(write_if_missing=True)
>
>        handler = DevlogsHandler(
>            application="my-app",  # Required: your app name
>            component="api",       # Required: component name
>            level=logging.INFO,
>            version=build_info.build_id,
>        )
>        logging.getLogger().addHandler(handler)
>        logging.getLogger().setLevel(logging.INFO)
>
>        # Log startup
>        logging.info("App started")
>    ```
> 4. Run `devlogs init` (inside the virtualenv if one is set up) and verify the index is healthy.
> 5. Ask the user if they want MCP set up; if yes, state which agent you are (`copilot`, `claude`, or `codex`) and run `devlogs initmcp <agent>`.

## Step 3: Use devlogs

1. Run `devlogs initmcp <agent>` to set up the MCP server.
2. Then run `devlogs tail` to see the last logs, or `devlogs tail -f` to follow along
3. Finally, ask your agent to query devlogs for errors. Watch it solve problems on its own!

## If you want to install it by hand

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

4. **Use in Python code (development only):**
	```python
	import os
	import logging

	# Only enable devlogs in development
	if os.getenv("ENVIRONMENT") != "production":
	    from devlogs.handler import DevlogsHandler
	    from devlogs.build_info import resolve_build_info

	    # Get build info (reads .build.json or generates)
	    build_info = resolve_build_info(write_if_missing=True)

	    handler = DevlogsHandler(
	        application="my-app",
	        component="default",
	        level=logging.DEBUG,
	        version=build_info.build_id,
	    )
	    logging.getLogger().addHandler(handler)
	    logging.getLogger().setLevel(logging.DEBUG)

	    logging.info("Hello from devlogs!")
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

- **DevlogsHandler** - Standard `logging.Handler` for OpenSearch with v2.0 schema
- **HTTP Collector Service** for centralized log ingestion
- **Devlogs Record Format v2.0** - Standardized schema with `application`, `component`, top-level `message`/`level`/`area`
- Context manager for operation_id/area
- Structured custom fields on log entries (`extra={"features": {...}}` stored as `fields`)
- CLI and Linux shell wrapper
- Minimal embeddable web UI
- Robust tests (pytest)

> **Note:** Version 2.0.0 introduces breaking changes. See [MIGRATION-V2.md](MIGRATION-V2.md) for upgrade instructions.

## HTTP Collector

The devlogs collector is a standalone HTTP service for centralized log ingestion. It supports two modes:

- **Forward mode**: Proxy requests to an upstream collector
- **Ingest mode**: Write directly to OpenSearch

### Quick Start

```bash
# Start collector in ingest mode
DEVLOGS_OPENSEARCH_HOST=localhost DEVLOGS_INDEX=devlogs-myapp devlogs-collector serve

# Start collector in forward mode
DEVLOGS_FORWARD_URL=https://central-collector.example.com devlogs-collector serve
```

### Using the Python Client

```python
from devlogs.devlogs_client import create_client

client = create_client(
    collector_url="http://localhost:8080",
    application="my-app",
    component="api-server",
)

client.emit(
    message="Request processed",
    level="info",
    fields={"user_id": "123", "duration_ms": 45}
)
```

### Docker

```bash
docker build -f Dockerfile.collector -t devlogs-collector .
docker run -p 8080:8080 -e DEVLOGS_OPENSEARCH_URL=https://admin:pass@opensearch:9200/devlogs devlogs-collector
```

See [HOWTO-COLLECTOR.md](HOWTO-COLLECTOR.md) for complete collector documentation.

## Jenkins Integration

### Option 1: Jenkins Plugin (Recommended)

Install the Devlogs Jenkins plugin for native integration:

```groovy
pipeline {
    agent any
    stages {
        stage('Build') {
            steps {
                devlogs(url: credentials('devlogs-url')) {
                    sh 'make build'
                }
            }
        }
    }
}
```

See [jenkins-plugin/README.md](jenkins-plugin/README.md) for installation and usage details.

### Option 2: Standalone Binary

Stream Jenkins build logs to OpenSearch using a standalone binary:

```groovy
pipeline {
    agent any
    environment {
        DEVLOGS_OPENSEARCH_URL = credentials('devlogs-opensearch-url')
        DEVLOGS_BINARY_URL = credentials('devlogs-binary-url')
    }
    stages {
        stage('Build') {
            steps {
                sh 'curl -sL $DEVLOGS_BINARY_URL -o /tmp/devlogs && chmod +x /tmp/devlogs'
                sh '/tmp/devlogs jenkins attach --background'
                sh 'make build'
            }
        }
    }
    post {
        always { sh '/tmp/devlogs jenkins stop || true' }
    }
}
```

Build the binary with `./build-standalone.sh` and host it somewhere accessible. See [HOWTO-JENKINS.md](HOWTO-JENKINS.md) for setup details.

## Configuration

### Environment Variables

**Collector Configuration:**
- `DEVLOGS_URL` - Collector base URL (where apps send logs)
- `DEVLOGS_FORWARD_URL` - Forward mode: proxy to this upstream URL

**OpenSearch Admin Connection:**
- `DEVLOGS_OPENSEARCH_HOST`, `DEVLOGS_OPENSEARCH_PORT`, `DEVLOGS_OPENSEARCH_USER`, `DEVLOGS_OPENSEARCH_PASS`
- `DEVLOGS_OPENSEARCH_URL` - URL shortcut (e.g., `https://user:pass@host:9200/index`)
- `DEVLOGS_OPENSEARCH_VERIFY_CERTS`, `DEVLOGS_OPENSEARCH_CA_CERT` - SSL/TLS settings

**Index & Retention:**
- `DEVLOGS_INDEX` - Target index name
- `DEVLOGS_RETENTION_DEBUG`, `DEVLOGS_RETENTION_INFO`, `DEVLOGS_RETENTION_WARNING` - Retention policy (e.g., `24h`, `7d`)

**Collector Limits (Future Provisions):**
- `DEVLOGS_COLLECTOR_RATE_LIMIT` - Max requests/second (0 = unlimited)
- `DEVLOGS_COLLECTOR_MAX_PAYLOAD_SIZE` - Max payload bytes (0 = unlimited)

See [.env.example](.env.example) for a complete configuration template.

### CLI Options

Use `--url` to specify connection details without a `.env` file:

```bash
devlogs --url 'https://admin:pass@host:9200/myindex' tail
```

Use `--env` to load from a specific `.env` file:

```bash
devlogs --env /path/to/.env diagnose
```

### URL Builder

Use `devlogs mkurl` to interactively create a properly URL-encoded connection string:

```bash
devlogs mkurl
# Outputs the URL in three formats:
# 1. Bare URL (for --url flag)
# 2. Single DEVLOGS_OPENSEARCH_URL variable
# 3. Individual .env variables
```

This is especially useful for passwords containing special characters like `!`, `@`, `#`, which must be URL-encoded.

See [HOWTO-CLI.md](HOWTO-CLI.md) for complete CLI reference.

## Production Deployment

Devlogs is a development tool. The examples above show how to conditionally enable it using an environment check. You can also make it an optional dependency:

```toml
# pyproject.toml
[project.optional-dependencies]
dev = ["devlogs>=2.0.0"]
```

Install with `pip install ".[dev]"` in development, `pip install .` in production.

## Project Structure

- `src/devlogs/` - Python library, CLI, MCP server, and web UI
- `browser/` - Browser/npm package for frontend logging
- `jenkins-plugin/` - Native Jenkins plugin for log streaming
- `devlogs` - Shell wrapper for local development
- `tests/` - Pytest-based tests
- `dist/` - Built packages and standalone binary

## Publishing

```bash
# Release to all platforms (PyPI, npm, GitHub)
./publish/release.sh

# Bump version and release
./publish/release.sh --bump-patch

# Preview release
./publish/release.sh --dry-run
```

See [publish/RELEASING.md](publish/RELEASING.md) for detailed publishing instructions.

## Build Info Helper

Tag every log entry with a stable build identifier without requiring git at runtime:

```python
from devlogs.build_info import resolve_build_info

bi = resolve_build_info(write_if_missing=True)
# bi.build_id = "main-20260124T153045Z"
# bi.branch = "main"
# bi.source = "file" | "env" | "generated"

# Use with DevlogsHandler
handler = DevlogsHandler(
    application="my-app",
    component="api",
    version=bi.build_id,  # Include build info in handler
)
logging.info("Started")
```

The build info is resolved from (in priority order):
1. Environment variables (`DEVLOGS_BUILD_ID`, `DEVLOGS_BRANCH`)
2. Build info file (`.build.json`)
3. Generated values (branch-timestamp format)

See [docs/build-info.md](docs/build-info.md) for CI integration examples and full API reference.

## See Also

- [MIGRATION-V2.md](MIGRATION-V2.md) - Migration guide from v1.x to v2.0
- [HOWTO-COLLECTOR.md](HOWTO-COLLECTOR.md) - HTTP collector setup and deployment
- [HOWTO-DEVLOGS-FORMAT.md](HOWTO-DEVLOGS-FORMAT.md) - Devlogs record format reference
- [docs/build-info.md](docs/build-info.md) - Build info helper guide
- [HOWTO-CLI.md](HOWTO-CLI.md) - Complete CLI reference
- [HOWTO.md](HOWTO.md) - Integration guide
- [HOWTO-JENKINS.md](HOWTO-JENKINS.md) - Jenkins setup
- [jenkins-plugin/README.md](jenkins-plugin/README.md) - Jenkins plugin documentation
- [HOWTO-MCP.md](HOWTO-MCP.md) - MCP agent setup
- [HOWTO-UI.md](HOWTO-UI.md) - Web UI guide
- [publish/RELEASING.md](publish/RELEASING.md) - Publishing guide
- `PROMPT.md` for full requirements
