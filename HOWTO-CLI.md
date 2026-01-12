# Devlogs CLI Reference

Complete reference for all devlogs command-line options and commands.

## Installation

**Python package:**
```bash
pip install devlogs
```

**Standalone binary** (no Python required):
```bash
# Download from GitHub releases or build yourself
./build-standalone.sh
# Binary: dist/devlogs-linux
```

## Global Options

These options can be used with any command:

| Option | Description |
|--------|-------------|
| `--env PATH` | Path to .env file to load |
| `--url URL` | OpenSearch URL (e.g., `https://user:pass@host:port/index`) |
| `--help` | Show help and exit |

### Using `--url`

The `--url` option provides a convenient way to specify all OpenSearch connection details in a single URL:

```bash
# URL format: scheme://user:password@host:port/index
devlogs --url 'https://admin:mypass@opensearch.example.com:9200/devlogs-prod' tail

# Special characters in passwords must be URL-encoded
# Use the mkurl command to help construct properly encoded URLs
devlogs --url 'https://admin:pass%21word@host:9200/index' diagnose
```

### Using `--env`

Load configuration from a specific .env file:

```bash
devlogs --env /path/to/custom.env tail
devlogs --env ~/.devlogs-prod.env search --q "error"
```

---

## Commands

### `init`

Initialize OpenSearch indices and templates. Safe to run multiple times (idempotent).

```bash
devlogs init
```

Run this after setting up your `.env` file or before first use.

---

### `mkurl`

Interactively create an OpenSearch URL and show equivalent `.env` formats.

```bash
devlogs mkurl
```

This command helps you:
- Parse an existing URL to see it in different formats
- Build a new URL by entering components one by one
- Properly URL-encode special characters in credentials

**Output formats:**
1. Bare URL (for `--url` flag)
2. Single `.env` variable (`DEVLOGS_OPENSEARCH_URL=...`)
3. Individual `.env` variables

**Example session:**
```
$ devlogs mkurl
OpenSearch URL Builder
==================================================

How would you like to provide the connection details?
  [1] Paste an existing URL
  [2] Enter components one by one

Choice [2]: 2

Scheme (http/https) [https]: https
Host [localhost]: opensearch.example.com
Port [443]: 9200
Username (leave empty for none) []: admin
Password (leave empty for none) []: ********
Index name (leave empty for default) []: devlogs-prod

==================================================
OUTPUT FORMATS
==================================================

1. Bare URL (for --url flag):
--------------------------------------------------
https://admin:Secret%21Pass@opensearch.example.com:9200/devlogs-prod

2. Single .env variable:
--------------------------------------------------
DEVLOGS_OPENSEARCH_URL=https://admin:Secret%21Pass@opensearch.example.com:9200/devlogs-prod

3. Individual .env variables:
--------------------------------------------------
DEVLOGS_OPENSEARCH_HOST=opensearch.example.com
DEVLOGS_OPENSEARCH_PORT=9200
DEVLOGS_OPENSEARCH_USER=admin
DEVLOGS_OPENSEARCH_PASS=Secret!Pass
DEVLOGS_INDEX=devlogs-prod
```

---

### `diagnose`

Diagnose common setup issues. Checks configuration, OpenSearch connectivity, index existence, and MCP setup.

```bash
devlogs diagnose
```

**Example output:**
```
Devlogs diagnostics:
[OK] .env: /project/.env (auto-discovered)
[OK] OpenSearch: connected to localhost:9200
[OK] Index: devlogs-myproject exists
[OK] Logs: found 1234 entries
[OK] MCP (Claude): devlogs configured in /project/.mcp.json
[WARN] MCP (Copilot): /project/.vscode/mcp.json not found
```

---

### `tail`

Tail logs, optionally filtering by area, operation, or level.

```bash
devlogs tail [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-o, --operation TEXT` | Filter by operation ID |
| `--area TEXT` | Filter by area (e.g., `api`, `database`) |
| `--level TEXT` | Filter by level (e.g., `ERROR`, `WARNING`) |
| `--since TEXT` | Show logs since time (e.g., `1h`, `30m`, ISO timestamp) |
| `--limit INTEGER` | Number of entries to show (default: 20) |
| `-f, --follow` | Continuously follow new logs |
| `-v, --verbose` | Enable verbose output |
| `--utc` | Display timestamps in UTC |

**Examples:**
```bash
# Tail recent logs
devlogs tail

# Follow logs in real-time
devlogs tail -f

# Filter by area
devlogs tail --area api --follow

# Filter by level
devlogs tail --level ERROR --limit 50

# Logs from the last hour
devlogs tail --since 1h

# Combine filters
devlogs tail --area database --level WARNING --since 30m -f
```

---

### `search`

Search logs with a query string.

```bash
devlogs search [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--q TEXT` | Search query |
| `--area TEXT` | Filter by area |
| `--level TEXT` | Filter by level |
| `-o, --operation TEXT` | Filter by operation ID |
| `--since TEXT` | Show logs since time |
| `--limit INTEGER` | Max results (default: 50) |
| `-f, --follow` | Continuously search for new matches |
| `--utc` | Display timestamps in UTC |

**Examples:**
```bash
# Search for errors
devlogs search --q "error"

# Search in specific area
devlogs search --q "timeout" --area api

# Search with level filter
devlogs search --q "connection" --level ERROR

# Follow search results
devlogs search --q "failed" --follow
```

---

### `last-error`

Show the most recent error or critical log entries.

```bash
devlogs last-error [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--q TEXT` | Additional search query |
| `--area TEXT` | Filter by area |
| `-o, --operation TEXT` | Filter by operation ID |
| `--since TEXT` | Show errors since time |
| `--until TEXT` | Show errors until time |
| `--limit INTEGER` | Number of errors (default: 1) |
| `--utc` | Display timestamps in UTC |

**Examples:**
```bash
# Show most recent error
devlogs last-error

# Show last 5 errors
devlogs last-error --limit 5

# Errors in specific area
devlogs last-error --area api --limit 10
```

---

### `cleanup`

Clean up old logs based on retention policy.

```bash
devlogs cleanup [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--dry-run` | Show what would be deleted without deleting |
| `--stats` | Show retention statistics only |

**Retention tiers:**
- DEBUG logs: Deleted after `DEVLOGS_RETENTION_DEBUG` (default: 6h)
- INFO logs: Deleted after `DEVLOGS_RETENTION_INFO` (default: 7d)
- WARNING/ERROR/CRITICAL: Deleted after `DEVLOGS_RETENTION_WARNING` (default: 30d)

**Examples:**
```bash
# Preview cleanup
devlogs cleanup --dry-run

# View statistics
devlogs cleanup --stats

# Run cleanup
devlogs cleanup
```

---

### `clean`

Delete the devlogs index and all templates. **Destructive operation.**

```bash
devlogs clean [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-f, --force` | Skip confirmation prompt |

**Examples:**
```bash
# With confirmation
devlogs clean

# Skip confirmation
devlogs clean --force
```

---

### `delete`

Delete a specific OpenSearch index.

```bash
devlogs delete [INDEX] [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `INDEX` | Index name (defaults to configured index) |

| Option | Description |
|--------|-------------|
| `-f, --force` | Skip confirmation prompt |

**Examples:**
```bash
# Delete configured index
devlogs delete

# Delete specific index
devlogs delete devlogs-old-project

# Force delete
devlogs delete devlogs-test --force
```

---

### `demo`

Generate demo logs to test your setup.

```bash
devlogs demo [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-t, --duration INTEGER` | Duration in seconds (default: 10) |
| `-n, --count INTEGER` | Number of log entries (default: 50) |

**Example:**
```bash
# Generate demo logs while tailing
devlogs demo --duration 30 --count 100 &
devlogs tail --follow
```

---

### `serve`

Start the web UI server.

```bash
devlogs serve [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-p, --port INTEGER` | Port to serve on (default: 8888) |
| `-h, --host TEXT` | Host to bind to (default: 127.0.0.1) |
| `-r, --reload` | Enable auto-reload for development |

**Examples:**
```bash
# Start on default port
devlogs serve
# Open http://localhost:8888/ui/

# Custom port and host
devlogs serve --port 9000 --host 0.0.0.0

# Development mode with auto-reload
devlogs serve --reload
```

---

### `initmcp`

Write MCP (Model Context Protocol) configuration for AI coding agents.

```bash
devlogs initmcp AGENT
```

| Argument | Description |
|----------|-------------|
| `AGENT` | Target agent: `copilot`, `claude`, `codex`, or `all` |

**Config file locations:**
- Claude: `.mcp.json`
- Copilot (VS Code): `.vscode/mcp.json`
- Codex: `~/.codex/config.toml`

**Examples:**
```bash
# Set up for Claude
devlogs initmcp claude

# Set up for all supported agents
devlogs initmcp all
```

---

## Jenkins Commands

Stream Jenkins build logs to OpenSearch. See [HOWTO-JENKINS.md](HOWTO-JENKINS.md) for full setup guide.

### `jenkins attach`

Attach to a Jenkins build and stream logs to OpenSearch.

```bash
devlogs jenkins attach [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--build-url TEXT` | Jenkins build URL (auto-detected from `BUILD_URL`) |
| `--url TEXT` | OpenSearch URL (e.g., `https://user:pass@host:port/index`) |
| `-b, --background` | Run in background mode |
| `--no-resume` | Don't resume from last indexed offset |
| `-v, --verbose` | Enable verbose output |

**Examples:**
```bash
# Attach in foreground (for testing)
devlogs jenkins attach

# Attach in background (for Jenkinsfile)
devlogs jenkins attach --background

# Explicit build URL
devlogs jenkins attach --build-url https://jenkins.example.com/job/my-job/123/
```

### `jenkins stop`

Stop a running background attach process.

```bash
devlogs jenkins stop
```

### `jenkins status`

Show the status of the current attach process.

```bash
devlogs jenkins status
```

### `jenkins snapshot`

Take a one-time snapshot of Jenkins build logs (no streaming).

```bash
devlogs jenkins snapshot [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--build-url TEXT` | Jenkins build URL |
| `--url TEXT` | OpenSearch URL (e.g., `https://user:pass@host:port/index`) |
| `-v, --verbose` | Enable verbose output |

**Example:**
```bash
devlogs jenkins snapshot --build-url https://jenkins.example.com/job/my-job/123/
```

---

## Environment Variables

### OpenSearch Connection

| Variable | Description | Default |
|----------|-------------|---------|
| `DEVLOGS_OPENSEARCH_HOST` | OpenSearch hostname | `localhost` |
| `DEVLOGS_OPENSEARCH_PORT` | OpenSearch port | `9200` |
| `DEVLOGS_OPENSEARCH_USER` | Username | `admin` |
| `DEVLOGS_OPENSEARCH_PASS` | Password | `admin` |
| `DEVLOGS_OPENSEARCH_URL` | Full URL (overrides individual settings) | - |
| `DEVLOGS_OPENSEARCH_VERIFY_CERTS` | Verify SSL certificates | `true` |
| `DEVLOGS_OPENSEARCH_CA_CERT` | Path to CA certificate | - |
| `DEVLOGS_OPENSEARCH_TIMEOUT` | Connection timeout (seconds) | `30` |

### Index and Retention

| Variable | Description | Default |
|----------|-------------|---------|
| `DEVLOGS_INDEX` | Index name | `devlogs-0001` |
| `DEVLOGS_RETENTION_DEBUG` | DEBUG log retention | `6h` |
| `DEVLOGS_RETENTION_INFO` | INFO log retention | `7d` |
| `DEVLOGS_RETENTION_WARNING` | WARNING+ log retention | `30d` |

### Jenkins Integration

| Variable | Description |
|----------|-------------|
| `BUILD_URL` | Jenkins build URL (auto-set by Jenkins) |
| `JENKINS_USER` | Jenkins API username |
| `JENKINS_TOKEN` | Jenkins API token |
| `JOB_NAME`, `BUILD_NUMBER`, `BUILD_TAG` | Build metadata (auto-set) |
| `BRANCH_NAME`, `GIT_COMMIT` | Git metadata (auto-set) |

#### Obtaining a Jenkins API Token

If your Jenkins instance requires authentication, you'll need to create an API token:

1. Log into the Jenkins web UI
2. Click your username in the top right corner
3. Click **Configure** (or go to `/user/<username>/configure`)
4. Under **API Token**, click **Add new Token**
5. Give it a name (e.g., "devlogs") and click **Generate**
6. Copy the token immediately (it won't be shown again)

Then set the environment variables:

```bash
export JENKINS_USER=your-username
export JENKINS_TOKEN=your-api-token
```

Or in Docker Compose:

```yaml
services:
  your-service:
    environment:
      - JENKINS_USER=your-username
      - JENKINS_TOKEN=your-api-token
```

---

## Standalone Binary

The standalone binary (`devlogs-linux`) includes all dependencies and doesn't require Python. It's useful for:

- Jenkins pipelines (no Python installation needed)
- CI/CD environments
- Quick debugging on servers

### Building the Binary

```bash
./build-standalone.sh
# Output: dist/devlogs-linux
```

### Using the Binary

```bash
# All commands work the same as the Python version
./dist/devlogs-linux --help
./dist/devlogs-linux --url 'https://admin:pass@host:9200/index' tail
./dist/devlogs-linux jenkins attach --background
```

### Distributing the Binary

Host the binary somewhere accessible (GitHub releases, S3, internal server) and download it in your CI/CD pipelines:

```bash
curl -sL $DEVLOGS_BINARY_URL -o /tmp/devlogs && chmod +x /tmp/devlogs
/tmp/devlogs jenkins attach --background
```

---

## Common Workflows

### First-Time Setup

```bash
# 1. Configure connection
cp .env.example .env
# Edit .env with your OpenSearch details

# 2. Initialize indices
devlogs init

# 3. Verify setup
devlogs diagnose

# 4. Set up MCP for your AI agent
devlogs initmcp claude
```

### Daily Development

```bash
# Follow logs while developing
devlogs tail -f

# Search for specific issues
devlogs search --q "database connection"

# Check recent errors
devlogs last-error --limit 5
```

### Troubleshooting Connection Issues

```bash
# Create/verify URL format
devlogs mkurl

# Diagnose setup
devlogs diagnose

# Test with explicit URL
devlogs --url 'https://user:pass@host:9200/index' diagnose
```

### CI/CD Integration

```groovy
// Jenkinsfile
pipeline {
    environment {
        DEVLOGS_OPENSEARCH_URL = credentials('devlogs-url')
    }
    stages {
        stage('Build') {
            steps {
                sh 'devlogs jenkins attach --background'
                sh 'make build'
            }
        }
    }
    post {
        always { sh 'devlogs jenkins stop || true' }
    }
}
```
