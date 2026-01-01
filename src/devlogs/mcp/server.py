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
from ..opensearch.queries import (
    get_operation_summary,
    list_areas,
    list_operations,
    normalize_log_entries,
    search_logs,
    tail_logs,
)


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
        return client, cfg.index
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
            types.Tool(
                name="list_operations",
                description="List recent operations with summary stats. Use this to discover operations without knowing their IDs.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "area": {
                            "type": "string",
                            "description": "Filter by application area",
                        },
                        "since": {
                            "type": "string",
                            "description": "ISO timestamp to filter operations after this time",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of operations to return (default: 20)",
                            "default": 20,
                        },
                        "with_errors_only": {
                            "type": "boolean",
                            "description": "Only show operations that had errors",
                            "default": False,
                        },
                    },
                },
            ),
            types.Tool(
                name="list_areas",
                description="List all application areas with activity counts. Use this to discover what subsystems exist in the application.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "since": {
                            "type": "string",
                            "description": "ISO timestamp to filter activity after this time",
                        },
                        "min_operations": {
                            "type": "integer",
                            "description": "Minimum number of operations an area must have to be included",
                            "default": 1,
                        },
                    },
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
                # Use aggregation-based summary
                summary = get_operation_summary(client, index, operation_id)

                if not summary:
                    return [types.TextContent(
                        type="text",
                        text=f"No logs found for operation {operation_id}",
                    )]

                # Format summary
                summary_lines = [
                    f"Operation Summary: {operation_id}",
                    f"Start time: {summary.get('start_time', 'unknown')}",
                    f"End time: {summary.get('end_time', 'unknown')}",
                    f"Total entries: {summary.get('total_entries', 0)}",
                    f"Error count: {summary.get('error_count', 0)}",
                    "",
                    "Log levels:",
                ]
                for level, count in sorted(summary.get("counts_by_level", {}).items()):
                    summary_lines.append(f"  {level}: {count}")

                summary_lines.append("")
                summary_lines.append("Sample logs (first 10):")
                summary_lines.append("")

                # Format sample logs
                for log in summary.get("sample_logs", []):
                    summary_lines.append(_format_log_entry(log))

                return [types.TextContent(type="text", text="\n".join(summary_lines))]

            except IndexNotFoundError as e:
                return [types.TextContent(type="text", text=f"Error: {e}")]
            except Exception as e:
                return [types.TextContent(type="text", text=f"Summary error: {e}")]

        elif name == "list_operations":
            area = arguments.get("area")
            since = arguments.get("since")
            limit = arguments.get("limit", 20)
            with_errors_only = arguments.get("with_errors_only", False)

            try:
                operations = list_operations(
                    client=client,
                    index=index,
                    area=area,
                    since=since,
                    limit=limit,
                    with_errors_only=with_errors_only,
                )

                if not operations:
                    return [types.TextContent(
                        type="text",
                        text="No operations found matching the criteria.",
                    )]

                # Format operations list
                lines = [f"Found {len(operations)} operations:\n"]
                for op in operations:
                    duration = ""
                    if op.get("duration_ms") is not None:
                        duration_sec = op["duration_ms"] / 1000.0
                        duration = f" ({duration_sec:.2f}s)"

                    error_info = ""
                    if op.get("error_count", 0) > 0:
                        error_info = f" [ERRORS: {op['error_count']}]"

                    lines.append(
                        f"- {op['operation_id'][:16]} | {op.get('area', 'unknown')} | "
                        f"{op['total_logs']} logs{duration}{error_info}"
                    )
                    lines.append(f"  {op.get('start_time', 'unknown')} to {op.get('end_time', 'unknown')}")

                return [types.TextContent(type="text", text="\n".join(lines))]

            except IndexNotFoundError as e:
                return [types.TextContent(type="text", text=f"Error: {e}")]
            except Exception as e:
                return [types.TextContent(type="text", text=f"List operations error: {e}")]

        elif name == "list_areas":
            since = arguments.get("since")
            min_operations = arguments.get("min_operations", 1)

            try:
                areas = list_areas(
                    client=client,
                    index=index,
                    since=since,
                    min_operations=min_operations,
                )

                if not areas:
                    return [types.TextContent(
                        type="text",
                        text="No areas found matching the criteria.",
                    )]

                # Format areas list
                lines = [f"Found {len(areas)} application areas:\n"]
                for area_info in areas:
                    error_info = ""
                    if area_info.get("error_count", 0) > 0:
                        error_info = f" [ERRORS: {area_info['error_count']}]"

                    lines.append(
                        f"- {area_info['area']}: {area_info['operation_count']} operations, "
                        f"{area_info['log_count']} logs{error_info}"
                    )
                    lines.append(f"  Last activity: {area_info.get('last_activity', 'unknown')}")

                return [types.TextContent(type="text", text="\n".join(lines))]

            except IndexNotFoundError as e:
                return [types.TextContent(type="text", text=f"Error: {e}")]
            except Exception as e:
                return [types.TextContent(type="text", text=f"List areas error: {e}")]

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
