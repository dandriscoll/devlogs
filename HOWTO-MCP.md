# How to Use devlogs with MCP (Model Context Protocol)

The devlogs MCP server allows AI assistants like Claude Code, GitHub Copilot, and Codex to search and analyze your application logs directly.

## Prerequisites

1. **OpenSearch running** with devlogs configured
2. **devlogs installed**: `pip install -e /path/to/devlogs`
3. **Logs indexed**: Your application should be sending logs to devlogs

## Setup

### 1. Configure .env

Create a `.env` file in your project with your OpenSearch credentials:

```bash
DEVLOGS_OPENSEARCH_HOST=localhost
DEVLOGS_OPENSEARCH_PORT=9200
DEVLOGS_OPENSEARCH_USER=admin
DEVLOGS_OPENSEARCH_PASS=YourPassword123!
DEVLOGS_INDEX_LOGS=devlogs-0001
```

You can have multiple `.env` files for different environments (e.g., `production.env`, `staging.env`).

### 2. Add MCP Server Configuration

All AI assistants use the same basic configuration format. Add this to the appropriate configuration file for your tool:

```json
{
  "mcpServers": {
    "devlogs": {
      "command": "/path/to/your/project/.venv/bin/python",
      "args": ["-m", "devlogs.mcp.server"],
      "env": {
        "DOTENV_PATH": "/path/to/your/project/.env"
      }
    }
  }
}
```

**Important**: Replace `/path/to/your/project` with the actual path to your project directory.

#### Where to Add This Configuration

**Claude Code** - Project-scoped configuration (recommended):
- Create `.mcp.json` in your project root
- The configuration will be shared with your team via version control
- Claude Code will prompt for approval when first using the server

**Claude Code** - User-scoped configuration (personal):
- Add to `~/.claude.json` under the `mcpServers` field
- Available across all your projects

**GitHub Copilot** - VS Code project settings:
- Add to `.vscode/settings.json` in your project root
- Use `${workspaceFolder}` for paths:
  ```json
  {
    "mcp.servers": {
      "devlogs": {
        "command": "${workspaceFolder}/.venv/bin/python",
        "args": ["-m", "devlogs.mcp.server"],
        "env": {
          "DOTENV_PATH": "${workspaceFolder}/.env"
        }
      }
    }
  }
  ```

**Codex** - TOML configuration:
- Add to `~/.codex/config.toml`:
  ```toml
  [mcp_servers.devlogs]
  command = "/path/to/your/project/.venv/bin/python"
  args = ["-m", "devlogs.mcp.server"]

  [mcp_servers.devlogs.env]
  DOTENV_PATH = "/path/to/your/project/.env"
  ```
- Or use the CLI: `codex mcp add devlogs`

### 3. Restart Your AI Assistant

- **Claude Code**: Restart Claude Code or run `claude mcp list` to verify
- **GitHub Copilot**: Reload VS Code window
- **Codex**: Restart Codex

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

## Alternative: Inline Credentials

Instead of using a `.env` file, you can specify credentials directly in your MCP configuration. This is useful for simple setups but less secure for production use.

Replace the `env` section with inline credentials:

```json
"env": {
  "DEVLOGS_OPENSEARCH_HOST": "localhost",
  "DEVLOGS_OPENSEARCH_PORT": "9200",
  "DEVLOGS_OPENSEARCH_USER": "admin",
  "DEVLOGS_OPENSEARCH_PASS": "YourPassword123!",
  "DEVLOGS_INDEX_LOGS": "devlogs-0001"
}
```

**Security Note**: Avoid committing inline credentials to version control. Use `.env` files and add them to `.gitignore`.

## References

- [Model Context Protocol - OpenAI Codex](https://developers.openai.com/codex/mcp/)
- [Codex MCP Configuration Guide](https://vladimirsiedykh.com/blog/codex-mcp-config-toml-shared-configuration-cli-vscode-setup-2025)
