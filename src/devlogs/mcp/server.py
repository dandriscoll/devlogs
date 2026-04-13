"""MCP server for devlogs - allows AI assistants to search and analyze logs."""

import asyncio
import json
import os
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

from ..config import load_config
from ..opensearch.client import (
    AuthenticationError,
    ConnectionFailedError,
    DevlogsDisabledError,
    IndexNotFoundError,
    QueryError,
    get_opensearch_client,
)
from ..opensearch.queries import (
    get_operation_summary,
    get_operation_logs,
    get_last_errors,
    get_error_context,
    list_applications,
    list_areas,
    list_error_signatures,
    list_operations,
    list_recent_operations,
    normalize_log_entries,
    search_logs_page,
    tail_logs,
)


def _create_client_and_index():
    """Create OpenSearch client and get index name and application filter from config."""
    try:
        client = get_opensearch_client()
        cfg = load_config()
        return client, cfg.index, cfg.application
    except DevlogsDisabledError as e:
        raise RuntimeError(str(e))
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


def _get_loki_url() -> str | None:
    """Return Loki URL from LOKI_URL env var or auto-detected from DEVLOGS_URL."""
    url = os.environ.get("LOKI_URL")
    if url:
        return url
    cfg = load_config()
    if cfg.is_loki:
        return cfg.loki_url
    return None


def _get_loki_token() -> str | None:
    """Return Loki auth token from config, if available."""
    cfg = load_config()
    return cfg.loki_token


class _Backend:
    """Resolved backend that query tools use."""
    __slots__ = ("mode", "url", "index", "application", "client")

    def __init__(self, *, mode, url, index=None, application=None, client=None):
        self.mode = mode
        self.url = url
        self.index = index
        self.application = application
        self.client = client


def _resolve_backend() -> _Backend:
    """Resolve the query backend using the same code paths as the query tools.

    Returns a _Backend with mode="loki" or mode="opensearch".
    Raises RuntimeError if the backend cannot be initialised.
    """
    loki_url = _get_loki_url()
    if loki_url:
        cfg = load_config()
        return _Backend(mode="loki", url=loki_url, application=cfg.application)
    client, index, application = _create_client_and_index()
    return _Backend(
        mode="opensearch",
        url=client.base_url,
        index=index,
        application=application,
        client=client,
    )


def _handle_loki_search(arguments: dict) -> list[types.TextContent]:
    """Handle search_logs when LOKI_URL is configured."""
    from ..loki.queries import search as loki_search

    loki_url = _get_loki_url()
    app = arguments.get("application") or load_config().application
    if not app:
        return _error_response(
            "application is required for Loki backend (set via argument or DEVLOGS_URL)",
            "ValidationError",
        )

    try:
        entries = loki_search(
            loki_url=loki_url,
            app=app,
            level=arguments.get("level"),
            component=arguments.get("component"),
            area=arguments.get("area"),
            start=arguments.get("since"),
            end=arguments.get("until"),
            limit=_coerce_limit(arguments.get("limit"), 50, 100),
            filter_text=arguments.get("query"),
            token=_get_loki_token(),
        )
        return _json_response(
            data={"entries": entries},
            meta={"count": len(entries)},
        )
    except Exception as e:
        return _error_response(f"Loki search error: {e}", "SearchError")


def _handle_loki_tail(arguments: dict) -> list[types.TextContent]:
    """Handle tail_logs when LOKI_URL is configured."""
    from ..loki.queries import tail as loki_tail

    loki_url = _get_loki_url()
    app = arguments.get("application") or load_config().application
    if not app:
        return _error_response(
            "application is required for Loki backend (set via argument or DEVLOGS_URL)",
            "ValidationError",
        )

    try:
        entries = loki_tail(
            loki_url=loki_url,
            app=app,
            level=arguments.get("level"),
            component=arguments.get("component"),
            since=arguments.get("since", "10m"),
            limit=_coerce_limit(arguments.get("limit"), 20, 100),
            token=_get_loki_token(),
        )
        return _json_response(
            data={"entries": entries},
            meta={"count": len(entries)},
        )
    except Exception as e:
        return _error_response(f"Loki tail error: {e}", "TailError")


def _handle_loki_get_log_stats(arguments: dict) -> list[types.TextContent]:
    """Handle get_log_stats using Loki count_over_time."""
    from ..loki.queries import count_over_time as loki_count_over_time

    loki_url = _get_loki_url()
    app = arguments.get("application") or load_config().application
    if not app:
        return _error_response(
            "application is required for Loki backend (set via argument or DEVLOGS_URL)",
            "ValidationError",
        )

    try:
        stats = loki_count_over_time(
            loki_url=loki_url,
            app=app,
            interval=arguments.get("interval", "5m"),
            group_by=arguments.get("group_by"),
            start=arguments.get("since"),
            end=arguments.get("until"),
            token=_get_loki_token(),
        )
        return _json_response(
            data={"stats": stats},
            meta={"count": len(stats)},
        )
    except Exception as e:
        return _error_response(f"Loki stats error: {e}", "StatsError")


def _require_loki_application(arguments: dict, tool_name: str) -> tuple[str | None, list[types.TextContent] | None]:
    """Resolve the application filter for a Loki tool that requires one.

    Returns (application, None) on success, or (None, error_response) if missing.
    """
    app = arguments.get("application") or load_config().application
    if not app:
        return None, _error_response(
            f"application is required for Loki backend on {tool_name} (set via argument or DEVLOGS_URL)",
            "ValidationError",
        )
    return app, None


def _handle_loki_list_applications(arguments: dict) -> list[types.TextContent]:
    from ..loki.queries import list_applications as loki_list_applications

    loki_url = _get_loki_url()
    try:
        apps = loki_list_applications(
            loki_url=loki_url,
            since=arguments.get("since"),
            token=_get_loki_token(),
        )
        return _json_response(
            data={"applications": apps},
            meta={"count": len(apps)},
        )
    except Exception as e:
        return _error_response(f"Loki list_applications error: {e}", "ListApplicationsError")


def _handle_loki_list_areas(arguments: dict) -> list[types.TextContent]:
    from ..loki.queries import list_areas as loki_list_areas

    loki_url = _get_loki_url()
    app = arguments.get("application") or load_config().application
    try:
        areas = loki_list_areas(
            loki_url=loki_url,
            application=app,
            since=arguments.get("since"),
            token=_get_loki_token(),
        )
        return _json_response(
            data={"areas": areas},
            meta={"count": len(areas)},
        )
    except Exception as e:
        return _error_response(f"Loki list_areas error: {e}", "ListAreasError")


def _handle_loki_list_operations(arguments: dict) -> list[types.TextContent]:
    from ..loki.queries import list_operations as loki_list_operations

    loki_url = _get_loki_url()
    app = arguments.get("application") or load_config().application
    try:
        ops = loki_list_operations(
            loki_url=loki_url,
            application=app,
            area=arguments.get("area"),
            component=arguments.get("component"),
            since=arguments.get("since"),
            limit=_coerce_limit(arguments.get("limit"), 20, 100),
            token=_get_loki_token(),
        )
        return _json_response(
            data={"operations": ops},
            meta={"count": len(ops)},
        )
    except Exception as e:
        return _error_response(f"Loki list_operations error: {e}", "ListOperationsError")


def _handle_loki_list_recent_operations(arguments: dict) -> list[types.TextContent]:
    from ..loki.queries import list_recent_operations as loki_list_recent_operations

    loki_url = _get_loki_url()
    app, err = _require_loki_application(arguments, "list_recent_operations")
    if err is not None:
        return err
    try:
        ops = loki_list_recent_operations(
            loki_url=loki_url,
            application=app,
            area=arguments.get("area"),
            component=arguments.get("component"),
            since=arguments.get("since"),
            until=arguments.get("until"),
            limit=_coerce_limit(arguments.get("limit"), 20, 100),
            order_by=arguments.get("order_by", "last_activity"),
            with_errors_only=bool(arguments.get("with_errors_only", False)),
            token=_get_loki_token(),
        )
        return _json_response(
            data={"operations": ops},
            meta={"count": len(ops)},
        )
    except Exception as e:
        return _error_response(f"Loki list_recent_operations error: {e}", "ListRecentOperationsError")


def _handle_loki_list_recent_errors(arguments: dict) -> list[types.TextContent]:
    from ..loki.queries import list_error_signatures as loki_list_error_signatures

    loki_url = _get_loki_url()
    app, err = _require_loki_application(arguments, "list_recent_errors")
    if err is not None:
        return err
    try:
        signatures = loki_list_error_signatures(
            loki_url=loki_url,
            field=arguments.get("field") or "exception",
            application=app,
            area=arguments.get("area"),
            component=arguments.get("component"),
            since=arguments.get("since"),
            until=arguments.get("until"),
            limit=_coerce_limit(arguments.get("limit"), 20, 100),
            min_count=_coerce_nonnegative_int(arguments.get("min_count"), 1),
            include_missing=bool(arguments.get("include_missing", False)),
            token=_get_loki_token(),
        )
        return _json_response(
            data={"signatures": signatures},
            meta={"count": len(signatures)},
        )
    except Exception as e:
        return _error_response(f"Loki list_recent_errors error: {e}", "ListRecentErrorsError")


def _handle_loki_get_last_error(arguments: dict) -> list[types.TextContent]:
    from ..loki.queries import get_last_errors as loki_get_last_errors

    loki_url = _get_loki_url()
    app, err = _require_loki_application(arguments, "get_last_error")
    if err is not None:
        return err
    try:
        entries = loki_get_last_errors(
            loki_url=loki_url,
            application=app,
            query=arguments.get("query"),
            area=arguments.get("area"),
            operation_id=arguments.get("operation_id"),
            since=arguments.get("since"),
            until=arguments.get("until"),
            limit=_coerce_limit(arguments.get("limit"), 1, 100),
            component=arguments.get("component"),
            token=_get_loki_token(),
        )
        return _json_response(
            data={"entries": entries},
            meta={"count": len(entries)},
        )
    except Exception as e:
        return _error_response(f"Loki get_last_error error: {e}", "GetLastErrorError")


def _handle_loki_get_operation_summary(arguments: dict) -> list[types.TextContent]:
    from ..loki.queries import get_operation_summary as loki_get_operation_summary

    operation_id = arguments.get("operation_id")
    if not operation_id:
        return _error_response("operation_id is required", "ValidationError")

    loki_url = _get_loki_url()
    app, err = _require_loki_application(arguments, "get_operation_summary")
    if err is not None:
        return err
    try:
        summary = loki_get_operation_summary(
            loki_url=loki_url,
            operation_id=operation_id,
            application=app,
            component=arguments.get("component"),
            since=arguments.get("since"),
            until=arguments.get("until"),
            token=_get_loki_token(),
        )
        if not summary:
            return _json_response(
                data={"operation_id": operation_id, "found": False},
                meta={"count": 0},
            )
        summary["found"] = True
        return _json_response(data=summary)
    except Exception as e:
        return _error_response(f"Loki get_operation_summary error: {e}", "SummaryError")


def _handle_loki_get_operation_logs(arguments: dict) -> list[types.TextContent]:
    from ..loki.queries import get_operation_logs as loki_get_operation_logs

    operation_id = arguments.get("operation_id")
    if not operation_id:
        return _error_response("operation_id is required", "ValidationError")

    loki_url = _get_loki_url()
    app, err = _require_loki_application(arguments, "get_operation_logs")
    if err is not None:
        return err
    try:
        limit = _coerce_limit(arguments.get("limit"), 50, 100)
        entries = loki_get_operation_logs(
            loki_url=loki_url,
            operation_id=operation_id,
            query=arguments.get("query"),
            level=arguments.get("level"),
            since=arguments.get("since"),
            until=arguments.get("until"),
            limit=limit,
            application=app,
            component=arguments.get("component"),
            token=_get_loki_token(),
        )
        return _json_response(
            data={"operation_id": operation_id, "entries": entries},
            meta={"count": len(entries), "next_cursor": None},
        )
    except Exception as e:
        return _error_response(f"Loki get_operation_logs error: {e}", "OperationLogsError")


def _handle_loki_get_error_context(arguments: dict) -> list[types.TextContent]:
    from ..loki.queries import get_error_context as loki_get_error_context

    anchor_timestamp = arguments.get("anchor_timestamp")
    if not anchor_timestamp:
        return _error_response("anchor_timestamp is required", "ValidationError")

    loki_url = _get_loki_url()
    app, err = _require_loki_application(arguments, "get_error_context")
    if err is not None:
        return err
    try:
        before = _coerce_nonnegative_int(arguments.get("before"), 20)
        after = _coerce_nonnegative_int(arguments.get("after"), 20)
        entries = loki_get_error_context(
            loki_url=loki_url,
            anchor_timestamp=anchor_timestamp,
            operation_id=arguments.get("operation_id"),
            area=arguments.get("area"),
            query=arguments.get("query"),
            level=arguments.get("level"),
            before=before,
            after=after,
            application=app,
            component=arguments.get("component"),
            token=_get_loki_token(),
        )
        return _json_response(
            data={"anchor_timestamp": anchor_timestamp, "entries": entries},
            meta={"count": len(entries), "before": before, "after": after},
        )
    except Exception as e:
        return _error_response(f"Loki get_error_context error: {e}", "ErrorContextError")


def _handle_emit_log(arguments: dict) -> list[types.TextContent]:
    """Handle the emit_log tool call."""
    from ..devlogs_client import DevlogsClient

    cfg = load_config()
    collector_url = arguments.get("collector_url") or cfg.collector_url
    if not collector_url:
        return _error_response("No collector URL configured (set DEVLOGS_URL or pass collector_url)", "ConfigurationError")

    application = arguments.get("application") or cfg.application or "devlogs-mcp"
    component = arguments.get("component") or "mcp"

    try:
        client = DevlogsClient(
            collector_url=collector_url,
            application=application,
            component=component,
        )
        ok = client.emit(
            message=arguments.get("message"),
            level=arguments.get("level", "info"),
            area=arguments.get("area"),
            fields=arguments.get("fields"),
        )
        if ok:
            return _json_response(data={"emitted": True})
        else:
            return _error_response("Failed to emit log entry", "EmitError")
    except Exception as e:
        return _error_response(f"Emit failed: {e}", "EmitError")


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
                        "component": {
                            "type": "string",
                            "description": "Filter by component name (e.g., 'web', 'worker', 'jenkins')",
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
                            "description": "ISO timestamp or relative duration like '1h' to filter logs after this time",
                        },
                        "until": {
                            "type": "string",
                            "description": "ISO timestamp or relative duration like '1h' to filter logs before this time",
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
                        "application": {
                            "type": "string",
                            "description": "Filter by application name",
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
                        "component": {
                            "type": "string",
                            "description": "Filter by component name",
                        },
                        "level": {
                            "type": "string",
                            "description": "Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
                        },
                        "since": {
                            "type": "string",
                            "description": "ISO timestamp or relative duration like '1h' to filter logs after this time",
                        },
                        "until": {
                            "type": "string",
                            "description": "ISO timestamp or relative duration like '1h' to filter logs before this time",
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
                        "application": {
                            "type": "string",
                            "description": "Filter by application name",
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
                        "component": {
                            "type": "string",
                            "description": "Filter by component name",
                        },
                        "application": {
                            "type": "string",
                            "description": "Filter by application name",
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
                            "description": "ISO timestamp or relative duration like '1h' to filter logs after this time",
                        },
                        "until": {
                            "type": "string",
                            "description": "ISO timestamp or relative duration like '1h' to filter logs before this time",
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
                        "component": {
                            "type": "string",
                            "description": "Filter by component name",
                        },
                        "application": {
                            "type": "string",
                            "description": "Filter by application name",
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
                        "component": {
                            "type": "string",
                            "description": "Filter by component name",
                        },
                        "since": {
                            "type": "string",
                            "description": "ISO timestamp or relative duration like '1h' to filter operations after this time",
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
                        "application": {
                            "type": "string",
                            "description": "Filter by application name",
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
                        "component": {
                            "type": "string",
                            "description": "Filter by component name",
                        },
                        "since": {
                            "type": "string",
                            "description": "ISO timestamp or relative duration like '1h' to filter operations after this time",
                        },
                        "until": {
                            "type": "string",
                            "description": "ISO timestamp or relative duration like '1h' to filter operations before this time",
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
                        "application": {
                            "type": "string",
                            "description": "Filter by application name",
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
                            "description": "ISO timestamp or relative duration like '1h' to filter activity after this time",
                        },
                        "min_operations": {
                            "type": "integer",
                            "description": "Minimum number of operations an area must have to be included",
                            "default": 1,
                        },
                        "component": {
                            "type": "string",
                            "description": "Filter by component name",
                        },
                        "application": {
                            "type": "string",
                            "description": "Filter by application name",
                        },
                    },
                },
            ),
            types.Tool(
                name="list_applications",
                description="List all application names with activity counts. Use this to discover what applications are logging.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "since": {
                            "type": "string",
                            "description": "ISO timestamp or relative duration like '24h' to filter activity after this time",
                        },
                        "component": {
                            "type": "string",
                            "description": "Filter by component name",
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
                        "component": {
                            "type": "string",
                            "description": "Filter by component name",
                        },
                        "since": {
                            "type": "string",
                            "description": "ISO timestamp or relative duration like '1h' to filter logs after this time",
                        },
                        "until": {
                            "type": "string",
                            "description": "ISO timestamp or relative duration like '1h' to filter logs before this time",
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
                        "application": {
                            "type": "string",
                            "description": "Filter by application name",
                        },
                    },
                },
            ),
            types.Tool(
                name="get_last_error",
                description="Get the most recent error/critical log entries. Use limit to return more than one.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Text search query to match against log messages, logger names, and features",
                        },
                        "area": {
                            "type": "string",
                            "description": "Filter by application area",
                        },
                        "component": {
                            "type": "string",
                            "description": "Filter by component name",
                        },
                        "operation_id": {
                            "type": "string",
                            "description": "Filter by specific operation ID",
                        },
                        "since": {
                            "type": "string",
                            "description": "ISO timestamp or relative duration like '1h' to filter logs after this time",
                        },
                        "until": {
                            "type": "string",
                            "description": "ISO timestamp or relative duration like '1h' to filter logs before this time",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of error entries to return (default: 1, max: 100)",
                            "default": 1,
                        },
                        "application": {
                            "type": "string",
                            "description": "Filter by application name",
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
                        "component": {
                            "type": "string",
                            "description": "Filter by component name",
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
                        "application": {
                            "type": "string",
                            "description": "Filter by application name",
                        },
                    },
                    "required": ["anchor_timestamp"],
                },
            ),
            types.Tool(
                name="get_log_stats",
                description="Get log counts aggregated over a time interval. Requires Loki backend (LOKI_URL).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "application": {
                            "type": "string",
                            "description": "Application name to aggregate stats for",
                        },
                        "interval": {
                            "type": "string",
                            "description": "Aggregation interval (e.g. '1m', '5m', '1h')",
                            "default": "5m",
                        },
                        "group_by": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Labels to group by (e.g. ['level', 'component'])",
                        },
                        "since": {
                            "type": "string",
                            "description": "Range start as ISO timestamp or relative duration like '1h'",
                        },
                        "until": {
                            "type": "string",
                            "description": "Range end as ISO timestamp or relative duration",
                        },
                    },
                },
            ),
            types.Tool(
                name="get_devlogs_url",
                description="Get the currently configured devlogs URL (DEVLOGS_URL). Returns the URL, its mode (loki, collector, opensearch), and application filter if set.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="emit_log",
                description="Emit a log entry to the configured devlogs backend (collector, OpenSearch, or plugin).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Log message"},
                        "level": {"type": "string", "description": "Log level (debug, info, warning, error, critical)", "default": "info"},
                        "area": {"type": "string", "description": "Functional area or category"},
                        "application": {"type": "string", "description": "Application name (overrides config)"},
                        "component": {"type": "string", "description": "Component name (overrides config)"},
                        "fields": {"type": "object", "description": "Custom key-value fields"},
                        "collector_url": {"type": "string", "description": "Override collector URL (e.g., loki://host:3100)"},
                    },
                    "required": ["message"],
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

        # get_devlogs_url exercises the same code paths as the query tools
        if name == "get_devlogs_url":
            try:
                backend = _resolve_backend()
                data = {"url": backend.url, "mode": backend.mode, "application": backend.application}
                if backend.index:
                    data["index"] = backend.index
                return _json_response(data=data)
            except RuntimeError as e:
                return _error_response(str(e), "InitializationError")

        # emit_log does not need OpenSearch — handle it before _create_client_and_index()
        if name == "emit_log":
            return _handle_emit_log(arguments)

        try:
            backend = _resolve_backend()
        except RuntimeError as e:
            return _error_response(str(e), "InitializationError")

        # get_log_stats is a Loki-only tool
        if name == "get_log_stats":
            if backend.mode != "loki":
                return _error_response(
                    "get_log_stats requires LOKI_URL to be set", "ConfigurationError"
                )
            return _handle_loki_get_log_stats(arguments)

        # Route query tools to Loki when configured
        if backend.mode == "loki":
            if name == "search_logs":
                return _handle_loki_search(arguments)
            if name == "tail_logs":
                return _handle_loki_tail(arguments)
            if name == "list_applications":
                return _handle_loki_list_applications(arguments)
            if name == "list_areas":
                return _handle_loki_list_areas(arguments)
            if name == "list_operations":
                return _handle_loki_list_operations(arguments)
            if name == "list_recent_operations":
                return _handle_loki_list_recent_operations(arguments)
            if name == "list_recent_errors":
                return _handle_loki_list_recent_errors(arguments)
            if name == "get_last_error":
                return _handle_loki_get_last_error(arguments)
            if name == "get_operation_summary":
                return _handle_loki_get_operation_summary(arguments)
            if name == "get_operation_logs":
                return _handle_loki_get_operation_logs(arguments)
            if name == "get_error_context":
                return _handle_loki_get_error_context(arguments)

        client = backend.client
        index = backend.index
        application = arguments.get("application") or backend.application

        component = arguments.get("component")

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
                    application=application,
                    component=component,
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
                    application=application,
                    component=component,
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
                summary = get_operation_summary(client, index, operation_id, application=application, component=component)

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
                    application=application,
                    component=component,
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
                    application=application,
                    component=component,
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
                    application=application,
                    component=component,
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
                    application=application,
                    component=component,
                )

                return _json_response(
                    data={"areas": areas},
                    meta={"count": len(areas)},
                )

            except IndexNotFoundError as e:
                return _error_response(str(e), "IndexNotFoundError")
            except Exception as e:
                return _error_response(f"List areas error: {e}", "ListAreasError")

        elif name == "list_applications":
            since = arguments.get("since")

            try:
                apps = list_applications(
                    client=client,
                    index=index,
                    since=since,
                    component=component,
                )

                return _json_response(
                    data={"applications": apps},
                    meta={"count": len(apps)},
                )

            except IndexNotFoundError as e:
                return _error_response(str(e), "IndexNotFoundError")
            except Exception as e:
                return _error_response(f"List applications error: {e}", "ListApplicationsError")

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
                    application=application,
                    component=component,
                )
                return _json_response(
                    data={"signatures": signatures},
                    meta={"count": len(signatures)},
                )
            except IndexNotFoundError as e:
                return _error_response(str(e), "IndexNotFoundError")
            except Exception as e:
                return _error_response(f"List recent errors error: {e}", "ListRecentErrorsError")

        elif name == "get_last_error":
            query = arguments.get("query")
            area = arguments.get("area")
            operation_id = arguments.get("operation_id")
            since = arguments.get("since")
            until = arguments.get("until")
            limit = _coerce_limit(arguments.get("limit"), 1, 100)

            try:
                docs = get_last_errors(
                    client=client,
                    index=index,
                    query=query,
                    area=area,
                    operation_id=operation_id,
                    since=since,
                    until=until,
                    limit=limit,
                    application=application,
                    component=component,
                )
                entries = _normalize_entries(docs, limit=limit)
                return _json_response(
                    data={"entries": entries},
                    meta={"count": len(entries)},
                )
            except IndexNotFoundError as e:
                return _error_response(str(e), "IndexNotFoundError")
            except QueryError as e:
                return _error_response(str(e), "QueryError")
            except Exception as e:
                return _error_response(f"Get last error error: {e}", "GetLastErrorError")

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
                    application=application,
                    component=component,
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
