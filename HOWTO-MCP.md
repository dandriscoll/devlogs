# How to Use devlogs with MCP (Model Context Protocol)

The devlogs MCP server allows AI assistants like Claude Code, GitHub Copilot, and Codex to search and analyze your application logs directly.

## Prerequisites

1. **OpenSearch running** with devlogs configured
2. **devlogs installed**: `pip install -e /path/to/devlogs`
3. **Logs indexed**: Your application should be sending logs to devlogs

## Setup

### 1. Configure .env

Create a `.env` file with your OpenSearch credentials:

```bash
DEVLOGS_OPENSEARCH_HOST=localhost
DEVLOGS_OPENSEARCH_PORT=9200
DEVLOGS_OPENSEARCH_USER=admin
DEVLOGS_OPENSEARCH_PASS=YourPassword123!
DEVLOGS_INDEX_LOGS=devlogs-0001
```

You can have multiple `.env` files for different environments (e.g., `production.env`, `staging.env`).

### 2. Configure Your AI Assistant

Add the MCP server configuration to your AI assistant's settings. The AI assistant will automatically start and manage the MCP server process.

#### Claude Code

Add to your MCP server configuration:

```json
{
  "mcpServers": {
    "devlogs": {
      "command": "python",
      "args": ["-m", "devlogs.mcp.server"],
      "cwd": "/path/to/your/project",
      "env": {
        "DOTENV_PATH": "/path/to/your/.env"
      }
    }
  }
}
```

Or with inline credentials:

```json
{
  "mcpServers": {
    "devlogs": {
      "command": "python",
      "args": ["-m", "devlogs.mcp.server"],
      "env": {
        "DEVLOGS_OPENSEARCH_HOST": "localhost",
        "DEVLOGS_OPENSEARCH_PORT": "9200",
        "DEVLOGS_OPENSEARCH_USER": "admin",
        "DEVLOGS_OPENSEARCH_PASS": "YourPassword123!",
        "DEVLOGS_INDEX_LOGS": "devlogs-0001"
      }
    }
  }
}
```

#### GitHub Copilot

If using VS Code with MCP support, add to `.vscode/settings.json`:

```json
{
  "mcp.servers": {
    "devlogs": {
      "command": "python",
      "args": ["-m", "devlogs.mcp.server"],
      "cwd": "${workspaceFolder}",
      "env": {
        "DOTENV_PATH": "${workspaceFolder}/.env"
      }
    }
  }
}
```

#### Codex / OpenAI API

Configure the MCP server in your integration's settings using the same format:

```json
{
  "devlogs": {
    "command": "python",
    "args": ["-m", "devlogs.mcp.server"],
    "env": {
      "DOTENV_PATH": "/path/to/your/.env"
    }
  }
}
```

The integration will start and manage the server process automatically.

## Usage

Once configured, ask your AI assistant to query your logs:

```
Search my devlogs for errors in the last hour
```

```
Show me logs from the 'api' area for operation abc-123
```

```
Find all WARNING and ERROR logs in the database area
```

## Available MCP Tools

- **`search_logs`**: Search logs with filters (query, area, operation_id, level, since, limit)
- **`tail_logs`**: Get the most recent logs (operation_id, area, level, limit)
- **`get_operation_summary`**: Get a summary of all logs for a specific operation

## Next Steps

- Read [HOWTO.md](HOWTO.md) for general devlogs integration
- Read [README.md](README.md) for project overview
- Run `devlogs demo` to generate sample logs for testing
