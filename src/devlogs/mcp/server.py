"""MCP server for devlogs - allows AI assistants to search and analyze logs."""

import asyncio
import json
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

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
    get_operation_logs,
    get_error_context,
    list_areas,
    list_error_signatures,
    list_operations,
    list_recent_operations,
    normalize_log_entries,
    search_logs_page,
    tail_logs,
)


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


def _coerce_limit(value: Any, default: int, max_value: int) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return default
    if limit <= 0:
        return default
    return min(limit, max_value)


def _coerce_nonnegative_int(value: Any, default: int) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return default
    if count < 0:
        return default
    return count


def _coerce_cursor(value: Any) -> list | None:
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, list):
            return parsed
    return None


def _normalize_entries(docs: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    entries = normalize_log_entries(docs, limit=limit)
    results = []
    for doc, entry in zip(docs, entries):
        item = dict(entry)
        if doc.get("id"):
            item["id"] = doc["id"]
        if doc.get("sort") is not None:
            item["sort"] = doc["sort"]
        results.append(item)
    return results


def _json_response(data: Any = None, error: dict | None = None, meta: dict | None = None) -> list[types.TextContent]:
    payload: dict[str, Any] = {"ok": error is None}
    if error is not None:
        payload["error"] = error
    if data is not None:
        payload["data"] = data
    if meta is not None:
        payload["meta"] = meta
    return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=True))]


def _error_response(message: str, error_type: str = "Error") -> list[types.TextContent]:
    return _json_response(error={"type": error_type, "message": message})


async def main():
    """Run the MCP server."""
    server = Server("devlogs")

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        """List available MCP tools."""
        return [
            types.Tool(
                name="search_logs",
                description="Search log entries with filters. Supports pagination via cursor.",
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
                        "until": {
                            "type": "string",
                            "description": "ISO timestamp to filter logs before this time (e.g., '2025-01-01T00:00:00Z')",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of log entries to return (default: 50, max: 100)",
                            "default": 50,
                        },
                        "cursor": {
                            "type": "array",
                            "items": {"type": ["string", "number"]},
                            "description": "Cursor from a previous response for pagination",
                        },
                    },
                },
            ),
            types.Tool(
                name="tail_logs",
                description="Get the most recent logs, optionally filtered. Supports pagination via cursor.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Text search query to match against log messages, logger names, and features",
                        },
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
                        "since": {
                            "type": "string",
                            "description": "ISO timestamp to filter logs after this time (e.g., '2025-01-01T00:00:00Z')",
                        },
                        "until": {
                            "type": "string",
                            "description": "ISO timestamp to filter logs before this time (e.g., '2025-01-01T00:00:00Z')",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of log entries to return (default: 20, max: 100)",
                            "default": 20,
                        },
                        "cursor": {
                            "type": "array",
                            "items": {"type": ["string", "number"]},
                            "description": "Cursor from a previous response for pagination",
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
                name="get_operation_logs",
                description="Get logs for an operation in chronological order. Supports pagination via cursor.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "operation_id": {
                            "type": "string",
                            "description": "The operation ID to fetch logs for",
                        },
                        "query": {
                            "type": "string",
                            "description": "Text search query to match against log messages, logger names, and features",
                        },
                        "level": {
                            "type": "string",
                            "description": "Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
                        },
                        "since": {
                            "type": "string",
                            "description": "ISO timestamp to filter logs after this time (e.g., '2025-01-01T00:00:00Z')",
                        },
                        "until": {
                            "type": "string",
                            "description": "ISO timestamp to filter logs before this time (e.g., '2025-01-01T00:00:00Z')",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of log entries to return (default: 50, max: 100)",
                            "default": 50,
                        },
                        "cursor": {
                            "type": "array",
                            "items": {"type": ["string", "number"]},
                            "description": "Cursor from a previous response for pagination",
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
                name="list_recent_operations",
                description="List recent operations ordered by last activity or error count. Includes last error sample when available.",
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
                        "until": {
                            "type": "string",
                            "description": "ISO timestamp to filter operations before this time",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of operations to return (default: 20)",
                            "default": 20,
                        },
                        "order_by": {
                            "type": "string",
                            "description": "Order by 'last_activity' or 'error_count'",
                            "default": "last_activity",
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
            types.Tool(
                name="list_recent_errors",
                description="Aggregate error signatures (exception/message) with counts and samples.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "field": {
                            "type": "string",
                            "description": "Signature field to aggregate by (e.g., 'exception' or 'message')",
                        },
                        "area": {
                            "type": "string",
                            "description": "Filter by application area",
                        },
                        "since": {
                            "type": "string",
                            "description": "ISO timestamp to filter logs after this time",
                        },
                        "until": {
                            "type": "string",
                            "description": "ISO timestamp to filter logs before this time",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of signatures to return (default: 20, max: 100)",
                            "default": 20,
                        },
                        "min_count": {
                            "type": "integer",
                            "description": "Minimum number of occurrences to include",
                            "default": 1,
                        },
                        "include_missing": {
                            "type": "boolean",
                            "description": "Include logs missing the signature field",
                            "default": False,
                        },
                    },
                },
            ),
            types.Tool(
                name="get_error_context",
                description="Fetch logs around an anchor timestamp for diagnosis.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "anchor_timestamp": {
                            "type": "string",
                            "description": "ISO timestamp to center the context around",
                        },
                        "operation_id": {
                            "type": "string",
                            "description": "Filter by specific operation ID",
                        },
                        "area": {
                            "type": "string",
                            "description": "Filter by application area",
                        },
                        "query": {
                            "type": "string",
                            "description": "Text search query to match against log messages, logger names, and features",
                        },
                        "level": {
                            "type": "string",
                            "description": "Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
                        },
                        "before": {
                            "type": "integer",
                            "description": "Number of entries before the anchor (default: 20)",
                            "default": 20,
                        },
                        "after": {
                            "type": "integer",
                            "description": "Number of entries after the anchor (default: 20)",
                            "default": 20,
                        },
                    },
                    "required": ["anchor_timestamp"],
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
            return _error_response(str(e), "InitializationError")

        if name == "search_logs":
            query = arguments.get("query")
            area = arguments.get("area")
            operation_id = arguments.get("operation_id")
            level = arguments.get("level")
            since = arguments.get("since")
            until = arguments.get("until")
            limit = _coerce_limit(arguments.get("limit"), 50, 100)
            cursor = _coerce_cursor(arguments.get("cursor"))

            try:
                docs, next_cursor = search_logs_page(
                    client=client,
                    index=index,
                    query=query,
                    area=area,
                    operation_id=operation_id,
                    level=level,
                    since=since,
                    until=until,
                    limit=limit,
                    cursor=cursor,
                    sort_order="desc",
                )
                entries = _normalize_entries(docs, limit=limit)

                return _json_response(
                    data={"entries": entries},
                    meta={"count": len(entries), "next_cursor": next_cursor},
                )

            except IndexNotFoundError as e:
                return _error_response(str(e), "IndexNotFoundError")
            except QueryError as e:
                return _error_response(str(e), "QueryError")
            except Exception as e:
                return _error_response(f"Search error: {e}", "SearchError")

        elif name == "tail_logs":
            query = arguments.get("query")
            operation_id = arguments.get("operation_id")
            area = arguments.get("area")
            level = arguments.get("level")
            since = arguments.get("since")
            until = arguments.get("until")
            limit = _coerce_limit(arguments.get("limit"), 20, 100)
            cursor = _coerce_cursor(arguments.get("cursor"))

            try:
                docs, next_cursor = tail_logs(
                    client=client,
                    index=index,
                    query=query,
                    operation_id=operation_id,
                    area=area,
                    level=level,
                    since=since,
                    until=until,
                    limit=limit,
                    search_after=cursor,
                )
                entries = _normalize_entries(docs, limit=limit)

                return _json_response(
                    data={"entries": entries},
                    meta={"count": len(entries), "next_cursor": next_cursor},
                )

            except IndexNotFoundError as e:
                return _error_response(str(e), "IndexNotFoundError")
            except QueryError as e:
                return _error_response(str(e), "QueryError")
            except Exception as e:
                return _error_response(f"Tail error: {e}", "TailError")

        elif name == "get_operation_summary":
            operation_id = arguments.get("operation_id")
            if not operation_id:
                return _error_response("operation_id is required", "ValidationError")

            try:
                summary = get_operation_summary(client, index, operation_id)

                if not summary:
                    return _json_response(
                        data={"operation_id": operation_id, "found": False},
                        meta={"count": 0},
                    )

                summary["found"] = True
                return _json_response(data=summary)

            except IndexNotFoundError as e:
                return _error_response(str(e), "IndexNotFoundError")
            except Exception as e:
                return _error_response(f"Summary error: {e}", "SummaryError")

        elif name == "get_operation_logs":
            operation_id = arguments.get("operation_id")
            if not operation_id:
                return _error_response("operation_id is required", "ValidationError")

            query = arguments.get("query")
            level = arguments.get("level")
            since = arguments.get("since")
            until = arguments.get("until")
            limit = _coerce_limit(arguments.get("limit"), 50, 100)
            cursor = _coerce_cursor(arguments.get("cursor"))

            try:
                docs, next_cursor = get_operation_logs(
                    client=client,
                    index=index,
                    operation_id=operation_id,
                    query=query,
                    level=level,
                    since=since,
                    until=until,
                    limit=limit,
                    cursor=cursor,
                )
                entries = _normalize_entries(docs, limit=limit)

                return _json_response(
                    data={"operation_id": operation_id, "entries": entries},
                    meta={"count": len(entries), "next_cursor": next_cursor},
                )
            except IndexNotFoundError as e:
                return _error_response(str(e), "IndexNotFoundError")
            except QueryError as e:
                return _error_response(str(e), "QueryError")
            except Exception as e:
                return _error_response(f"Operation logs error: {e}", "OperationLogsError")

        elif name == "list_operations":
            area = arguments.get("area")
            since = arguments.get("since")
            limit = _coerce_limit(arguments.get("limit"), 20, 100)
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

                return _json_response(
                    data={"operations": operations},
                    meta={"count": len(operations)},
                )

            except IndexNotFoundError as e:
                return _error_response(str(e), "IndexNotFoundError")
            except Exception as e:
                return _error_response(f"List operations error: {e}", "ListOperationsError")

        elif name == "list_recent_operations":
            area = arguments.get("area")
            since = arguments.get("since")
            until = arguments.get("until")
            limit = _coerce_limit(arguments.get("limit"), 20, 100)
            order_by = arguments.get("order_by", "last_activity")
            with_errors_only = arguments.get("with_errors_only", False)

            try:
                operations = list_recent_operations(
                    client=client,
                    index=index,
                    area=area,
                    since=since,
                    until=until,
                    limit=limit,
                    order_by=order_by,
                    with_errors_only=with_errors_only,
                )

                return _json_response(
                    data={"operations": operations},
                    meta={"count": len(operations)},
                )
            except IndexNotFoundError as e:
                return _error_response(str(e), "IndexNotFoundError")
            except Exception as e:
                return _error_response(f"List recent operations error: {e}", "ListRecentOperationsError")

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

                return _json_response(
                    data={"areas": areas},
                    meta={"count": len(areas)},
                )

            except IndexNotFoundError as e:
                return _error_response(str(e), "IndexNotFoundError")
            except Exception as e:
                return _error_response(f"List areas error: {e}", "ListAreasError")

        elif name == "list_recent_errors":
            field = arguments.get("field") or "exception"
            area = arguments.get("area")
            since = arguments.get("since")
            until = arguments.get("until")
            limit = _coerce_limit(arguments.get("limit"), 20, 100)
            min_count = _coerce_nonnegative_int(arguments.get("min_count"), 1)
            include_missing = bool(arguments.get("include_missing", False))

            try:
                signatures = list_error_signatures(
                    client=client,
                    index=index,
                    field=field,
                    area=area,
                    since=since,
                    until=until,
                    limit=limit,
                    min_count=min_count,
                    include_missing=include_missing,
                )
                return _json_response(
                    data={"signatures": signatures},
                    meta={"count": len(signatures)},
                )
            except IndexNotFoundError as e:
                return _error_response(str(e), "IndexNotFoundError")
            except Exception as e:
                return _error_response(f"List recent errors error: {e}", "ListRecentErrorsError")

        elif name == "get_error_context":
            anchor_timestamp = arguments.get("anchor_timestamp")
            if not anchor_timestamp:
                return _error_response("anchor_timestamp is required", "ValidationError")

            operation_id = arguments.get("operation_id")
            area = arguments.get("area")
            query = arguments.get("query")
            level = arguments.get("level")
            before = _coerce_nonnegative_int(arguments.get("before"), 20)
            after = _coerce_nonnegative_int(arguments.get("after"), 20)

            try:
                docs = get_error_context(
                    client=client,
                    index=index,
                    anchor_timestamp=anchor_timestamp,
                    operation_id=operation_id,
                    area=area,
                    query=query,
                    level=level,
                    before=before,
                    after=after,
                )
                entries = _normalize_entries(docs)
                return _json_response(
                    data={"anchor_timestamp": anchor_timestamp, "entries": entries},
                    meta={"count": len(entries), "before": before, "after": after},
                )
            except IndexNotFoundError as e:
                return _error_response(str(e), "IndexNotFoundError")
            except QueryError as e:
                return _error_response(str(e), "QueryError")
            except Exception as e:
                return _error_response(f"Error context error: {e}", "ErrorContextError")

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
