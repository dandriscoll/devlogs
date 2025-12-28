"""MCP server for devlogs - allows AI assistants to search and analyze logs."""

import asyncio
import os
from typing import Any, Optional

import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server

from ..config import load_config
from ..opensearch.client import (
    AuthenticationError,
    ConnectionFailedError,
    IndexNotFoundError,
    QueryError,
    get_opensearch_client,
)
from ..opensearch.queries import normalize_log_entries, search_logs, tail_logs


def _format_log_entry(entry: dict[str, Any]) -> str:
    """Format a log entry for display."""
    timestamp = entry.get("timestamp", "")
    level = entry.get("level", "")
    logger = entry.get("logger_name", "")
    message = entry.get("message", "")
    area = entry.get("area", "")
    operation_id = entry.get("operation_id", "")

    parts = []
    if timestamp:
        parts.append(f"[{timestamp}]")
    if level:
        parts.append(f"{level}")
    if area:
        parts.append(f"({area})")
    if operation_id:
        parts.append(f"op:{operation_id[:8]}")
    if logger:
        parts.append(f"{logger}:")
    if message:
        parts.append(message)

    result = " ".join(parts)

    # Add exception info if present
    exception = entry.get("exception")
    if exception:
        result += f"\n{exception}"

    return result


def _create_client_and_index():
    """Create OpenSearch client and get index name from config."""
    try:
        client = get_opensearch_client()
        cfg = load_config()
        return client, cfg.index_logs
    except ConnectionFailedError as e:
        raise RuntimeError(f"OpenSearch connection failed: {e}")
    except AuthenticationError as e:
        raise RuntimeError(f"OpenSearch authentication failed: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to initialize devlogs: {e}")


async def main():
    """Run the MCP server."""
    server = Server("devlogs")

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        """List available MCP tools."""
        return [
            types.Tool(
                name="search_logs",
                description="Search log entries with filters. Use this to find specific logs by keyword, area, operation ID, log level, or time range.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Text search query to match against log messages, logger names, and features",
                        },
                        "area": {
                            "type": "string",
                            "description": "Filter by application area (e.g., 'api', 'database', 'auth')",
                        },
                        "operation_id": {
                            "type": "string",
                            "description": "Filter by specific operation ID to see all logs for that operation",
                        },
                        "level": {
                            "type": "string",
                            "description": "Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
                        },
                        "since": {
                            "type": "string",
                            "description": "ISO timestamp to filter logs after this time (e.g., '2025-01-01T00:00:00Z')",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of log entries to return (default: 50, max: 100)",
                            "default": 50,
                        },
                    },
                },
            ),
            types.Tool(
                name="tail_logs",
                description="Get the most recent logs, optionally filtered. Use this to see what's happening right now in your application.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "operation_id": {
                            "type": "string",
                            "description": "Filter by specific operation ID",
                        },
                        "area": {
                            "type": "string",
                            "description": "Filter by application area",
                        },
                        "level": {
                            "type": "string",
                            "description": "Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of log entries to return (default: 20, max: 100)",
                            "default": 20,
                        },
                    },
                },
            ),
            types.Tool(
                name="get_operation_summary",
                description="Get a summary of all logs for a specific operation ID. Use this to understand the complete lifecycle of an operation.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "operation_id": {
                            "type": "string",
                            "description": "The operation ID to summarize",
                        },
                    },
                    "required": ["operation_id"],
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """Handle tool calls."""
        if arguments is None:
            arguments = {}

        try:
            client, index = _create_client_and_index()
        except RuntimeError as e:
            return [types.TextContent(type="text", text=f"Error: {e}")]

        if name == "search_logs":
            query = arguments.get("query")
            area = arguments.get("area")
            operation_id = arguments.get("operation_id")
            level = arguments.get("level")
            since = arguments.get("since")
            limit = min(arguments.get("limit", 50), 100)

            try:
                docs = search_logs(
                    client=client,
                    index=index,
                    query=query,
                    area=area,
                    operation_id=operation_id,
                    level=level,
                    since=since,
                    limit=limit,
                )
                entries = normalize_log_entries(docs, limit=limit)

                if not entries:
                    return [types.TextContent(
                        type="text",
                        text="No logs found matching the search criteria.",
                    )]

                formatted = "\n".join(_format_log_entry(entry) for entry in entries)
                summary = f"Found {len(entries)} log entries:\n\n{formatted}"

                return [types.TextContent(type="text", text=summary)]

            except IndexNotFoundError as e:
                return [types.TextContent(type="text", text=f"Error: {e}")]
            except QueryError as e:
                return [types.TextContent(type="text", text=f"Error: {e}")]
            except Exception as e:
                return [types.TextContent(type="text", text=f"Search error: {e}")]

        elif name == "tail_logs":
            operation_id = arguments.get("operation_id")
            area = arguments.get("area")
            level = arguments.get("level")
            limit = min(arguments.get("limit", 20), 100)

            try:
                docs, _ = tail_logs(
                    client=client,
                    index=index,
                    operation_id=operation_id,
                    area=area,
                    level=level,
                    limit=limit,
                )
                entries = normalize_log_entries(docs, limit=limit)

                if not entries:
                    return [types.TextContent(
                        type="text",
                        text="No recent logs found.",
                    )]

                formatted = "\n".join(_format_log_entry(entry) for entry in entries)
                summary = f"Most recent {len(entries)} log entries:\n\n{formatted}"

                return [types.TextContent(type="text", text=summary)]

            except IndexNotFoundError as e:
                return [types.TextContent(type="text", text=f"Error: {e}")]
            except QueryError as e:
                return [types.TextContent(type="text", text=f"Error: {e}")]
            except Exception as e:
                return [types.TextContent(type="text", text=f"Tail error: {e}")]

        elif name == "get_operation_summary":
            operation_id = arguments.get("operation_id")
            if not operation_id:
                return [types.TextContent(
                    type="text",
                    text="Error: operation_id is required",
                )]

            try:
                # Get all logs for this operation
                docs = search_logs(
                    client=client,
                    index=index,
                    operation_id=operation_id,
                    limit=100,
                )
                entries = normalize_log_entries(docs, limit=100)

                if not entries:
                    return [types.TextContent(
                        type="text",
                        text=f"No logs found for operation {operation_id}",
                    )]

                # Build summary
                levels = {}
                for entry in entries:
                    level = entry.get("level", "UNKNOWN")
                    levels[level] = levels.get(level, 0) + 1

                first_timestamp = entries[0].get("timestamp", "unknown")
                last_timestamp = entries[-1].get("timestamp", "unknown")
                area = entries[0].get("area", "unknown")

                summary_lines = [
                    f"Operation Summary: {operation_id}",
                    f"Area: {area}",
                    f"First log: {first_timestamp}",
                    f"Last log: {last_timestamp}",
                    f"Total entries: {len(entries)}",
                    "",
                    "Log levels:",
                ]
                for level, count in sorted(levels.items()):
                    summary_lines.append(f"  {level}: {count}")

                summary_lines.append("")
                summary_lines.append("All logs:")
                summary_lines.append("")

                formatted = "\n".join(_format_log_entry(entry) for entry in entries)
                summary = "\n".join(summary_lines) + formatted

                return [types.TextContent(type="text", text=summary)]

            except IndexNotFoundError as e:
                return [types.TextContent(type="text", text=f"Error: {e}")]
            except Exception as e:
                return [types.TextContent(type="text", text=f"Summary error: {e}")]

        else:
            raise ValueError(f"Unknown tool: {name}")

    # Run the server using stdio transport
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
