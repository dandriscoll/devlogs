# devlogs

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
> 1. Install `devlogs` (`pip install devlogs` or add it to `requirements.txt`/`pyproject.toml`).
> 2. Add `DEVLOGS_OPENSEARCH_HOST`, `DEVLOGS_OPENSEARCH_PORT`, `DEVLOGS_OPENSEARCH_USER`, `DEVLOGS_OPENSEARCH_PASS`, and `DEVLOGS_INDEX` to the project `.env` file (or equivalent config). Defaults are `localhost`, `9200`, `admin`, and `devlogs-<projectname>`.
> 3. Add devlogs hooks immediately at the beginning of the application (main entrypoint/startup module) to attach the handler:
>    - `from devlogs.handler import OpenSearchHandler`
>    - `handler = OpenSearchHandler(level=logging.INFO)`
>    - `logging.getLogger().addHandler(handler)`
>    - `logging.getLogger().setLevel(logging.INFO)`
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

## Jenkins Integration

Stream Jenkins build logs to OpenSearch in near real-time.

### Quick Start (Jenkinsfile)

```groovy
pipeline {
    agent any
    stages {
        stage('Build') {
            steps {
                sh 'devlogs jenkins attach --background'
                // Your build steps here
                sh 'make build'
            }
        }
    }
    post {
        always {
            sh 'devlogs jenkins stop || true'
        }
    }
}
```

### Agent Snippet

Add this to your Jenkins agent setup to automatically configure devlogs:

```groovy
// In your Jenkinsfile or shared library
def setupDevlogs() {
    // Install devlogs if not already installed
    sh 'pip install devlogs || true'

    // Start streaming logs in background
    sh 'devlogs jenkins attach --background'
}

def teardownDevlogs() {
    // Stop streaming and flush remaining logs
    sh 'devlogs jenkins stop || true'
}

// Usage in pipeline:
pipeline {
    agent any
    stages {
        stage('Setup') {
            steps {
                setupDevlogs()
            }
        }
        stage('Build') {
            steps {
                sh 'make build'
            }
        }
    }
    post {
        always {
            teardownDevlogs()
        }
    }
}
```

### Commands

- `devlogs jenkins attach [--background]` - Stream logs to OpenSearch
- `devlogs jenkins stop` - Stop a background attach process
- `devlogs jenkins snapshot` - One-time log capture (no streaming)
- `devlogs jenkins status` - Show status of attach process

### Environment Variables

**Required (auto-set by Jenkins):**
- `BUILD_URL` - Canonical URL of the build

**Optional - Jenkins Authentication:**
- `JENKINS_USER` - Username for Jenkins API
- `JENKINS_TOKEN` - API token for Jenkins API

**Optional - Build Metadata (auto-set by Jenkins):**
- `JOB_NAME` - Name of the job
- `BUILD_NUMBER` - Build number
- `BUILD_TAG` - Used as run_id for log correlation
- `BRANCH_NAME` - Branch name (for multibranch pipelines)
- `GIT_COMMIT` - Git commit SHA

### Security

If your Jenkins requires authentication for console log access:

1. Create an API token in Jenkins (User > Configure > API Token)
2. Set `JENKINS_USER` and `JENKINS_TOKEN` in your build environment
3. Store credentials securely using Jenkins Credentials plugin

```groovy
withCredentials([usernamePassword(
    credentialsId: 'devlogs-jenkins',
    usernameVariable: 'JENKINS_USER',
    passwordVariable: 'JENKINS_TOKEN'
)]) {
    sh 'devlogs jenkins attach --background'
}
```

## Configuration

Environment variables:
- OpenSearch connection: `DEVLOGS_OPENSEARCH_HOST`, `DEVLOGS_OPENSEARCH_PORT`, `DEVLOGS_OPENSEARCH_USER`, `DEVLOGS_OPENSEARCH_PASS`
- OpenSearch URL shortcut: `DEVLOGS_OPENSEARCH_URL` (e.g., `https://user:pass@host:9200`)
- SSL/TLS: `DEVLOGS_OPENSEARCH_VERIFY_CERTS`, `DEVLOGS_OPENSEARCH_CA_CERT`
- Index: `DEVLOGS_INDEX`
- Retention (supports duration strings like `24h`, `7d`): `DEVLOGS_RETENTION_DEBUG`, `DEVLOGS_RETENTION_INFO`, `DEVLOGS_RETENTION_WARNING`

See [.env.example](.env.example) for a complete configuration template.

## Project Structure

- `src/devlogs/` - Python library, CLI, MCP server, and web UI
- `devlogs` - Shell wrapper for local development
- `tests/` - Pytest-based tests

## See Also

- `PROMPT.md` for full requirements
