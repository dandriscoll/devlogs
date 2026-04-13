# LogQL query module for devlogs
#
# Provides search, tail, and aggregation operations against a Grafana Loki
# instance via its HTTP API.
#
# Label strategy mirrors the collector's Loki plugin:
#   Indexed labels: application, component, level, area, environment
#   Log line payload: message, operation_id, timestamp, fields, version

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

_LABEL_NAME_RE = re.compile(r'^[a-z_][a-z0-9_]*$')
_DURATION_RE = re.compile(r'^[0-9]+(ms|s|m|h|d|w)$')


def _validate_label_name(name: str) -> str:
    """Ensure a label name contains only safe characters."""
    if not _LABEL_NAME_RE.match(name):
        raise ValueError(f"Invalid label name for group_by: {name!r}")
    return name


def _validate_duration(interval: str) -> str:
    """Ensure a duration string matches the Loki duration format."""
    if not _DURATION_RE.match(interval):
        raise ValueError(
            f"Invalid interval {interval!r}. Must match [0-9]+(ms|s|m|h|d|w), e.g. '5m', '1h'."
        )
    return interval


# ---------------------------------------------------------------------------
# LogQL builder helpers
# ---------------------------------------------------------------------------

def build_stream_selector(labels: Dict[str, str]) -> str:
    """Build a Loki stream selector from a label dict.

    Returns e.g. {application="my-app", level="error"}
    Returns {} when labels is empty (matches all streams).
    """
    if not labels:
        return "{}"
    parts = ", ".join(
        f'{k}="{_escape_label_value(v)}"'
        for k, v in sorted(labels.items())
    )
    return "{" + parts + "}"


def build_log_pipeline(filter_text: Optional[str], use_json: bool = True) -> str:
    """Build a Loki log pipeline expression.

    Returns e.g. | json | message =~ "timeout"
    """
    parts = []
    if use_json:
        parts.append("| json")
    if filter_text:
        escaped = filter_text.replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'|= "{escaped}"')
    return " ".join(parts)


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _to_ns(dt: datetime) -> int:
    """Convert datetime to Unix nanoseconds (Loki's time format)."""
    return int(dt.timestamp() * 1e9)


def _parse_time_param(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp or relative duration string to a datetime.

    Accepts:
    - ISO 8601: "2024-01-15T10:30:00Z"
    - Relative: "1h", "30m", "7d"
    - None → returns None
    """
    if not value:
        return None
    from ..time_utils import resolve_relative_time
    resolved = resolve_relative_time(value)
    if resolved is None:
        return None
    try:
        ts = resolved.rstrip("Z")
        return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _loki_get(loki_url: str, path: str, params: Dict[str, str], token: Optional[str] = None) -> Dict[str, Any]:
    """Execute a GET request against the Loki HTTP API."""
    base = loki_url.rstrip("/")
    qs = urllib.parse.urlencode(params)
    url = f"{base}{path}?{qs}"
    req = urllib.request.Request(url, method="GET")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        raise RuntimeError(f"Loki HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Loki connection failed: {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Loki request failed: {e}")


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_log_streams(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse a Loki query_range (streams) response into a list of log dicts."""
    results = []
    for stream in data.get("data", {}).get("result", []):
        stream_labels = stream.get("stream", {})
        for ts_ns, line in stream.get("values", []):
            try:
                log_data: Dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                log_data = {"message": line}
            # Merge stream labels into the record (labels take precedence)
            log_data.update(stream_labels)
            # Add the Loki timestamp (nanoseconds) as a convenience field
            log_data["_loki_ts_ns"] = ts_ns
            results.append(log_data)
    return results


def _parse_metric_matrix(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse a Loki metric query_range (matrix) response."""
    results = []
    for series in data.get("data", {}).get("result", []):
        labels = series.get("metric", {})
        for ts, value in series.get("values", []):
            entry: Dict[str, Any] = {
                "timestamp": datetime.fromtimestamp(float(ts), tz=timezone.utc)
                .strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "value": float(value),
            }
            entry.update(labels)
            results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Public query API
# ---------------------------------------------------------------------------

def search(
    loki_url: str,
    app: str,
    level: Optional[str] = None,
    component: Optional[str] = None,
    area: Optional[str] = None,
    environment: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 100,
    filter_text: Optional[str] = None,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search log entries in a time range.

    Maps to GET /loki/api/v1/query_range with direction=backward.

    Args:
        loki_url: Base URL of the Loki instance (e.g. "http://loki:3100")
        app: Application label to filter by
        level: Log level label filter (e.g. "error")
        component: Component label filter
        area: Area label filter
        environment: Environment label filter
        start: ISO timestamp or relative duration string (e.g. "1h") for range start
        end: ISO timestamp or relative duration for range end
        limit: Maximum number of entries to return
        filter_text: Optional text to match against the message field

    Returns:
        List of log record dicts (stream labels merged with JSON payload)
    """
    now = datetime.now(timezone.utc)
    start_dt = _parse_time_param(start) or (now - timedelta(hours=1))
    end_dt = _parse_time_param(end) or now

    labels: Dict[str, str] = {"application": app}
    if level:
        labels["level"] = level.lower()
    if component:
        labels["component"] = component
    if area:
        labels["area"] = area
    if environment:
        labels["environment"] = environment

    selector = build_stream_selector(labels)
    pipeline = build_log_pipeline(filter_text)
    query = f"{selector} {pipeline}".strip()

    data = _loki_get(loki_url, "/loki/api/v1/query_range", {
        "query": query,
        "start": str(_to_ns(start_dt)),
        "end": str(_to_ns(end_dt)),
        "limit": str(limit),
        "direction": "backward",
    }, token=token)

    entries = _parse_log_streams(data)
    # Sort by Loki timestamp descending (most recent first)
    entries.sort(key=lambda e: e.get("_loki_ts_ns", "0"), reverse=True)
    return entries


def tail(
    loki_url: str,
    app: str,
    level: Optional[str] = None,
    component: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 50,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get the most recent log entries (non-streaming snapshot).

    Uses query_range with a short lookback window. For real-time streaming
    use the WebSocket endpoint /loki/api/v1/tail directly.

    Args:
        loki_url: Base URL of the Loki instance
        app: Application label to filter by
        level: Optional level label filter
        component: Optional component label filter
        since: Lookback window as relative string (default "10m")
        limit: Maximum number of entries to return
    """
    now = datetime.now(timezone.utc)
    start_dt = _parse_time_param(since or "10m") or (now - timedelta(minutes=10))

    labels: Dict[str, str] = {"application": app}
    if level:
        labels["level"] = level.lower()
    if component:
        labels["component"] = component

    selector = build_stream_selector(labels)
    query = f"{selector} | json"

    data = _loki_get(loki_url, "/loki/api/v1/query_range", {
        "query": query,
        "start": str(_to_ns(start_dt)),
        "end": str(_to_ns(now)),
        "limit": str(limit),
        "direction": "backward",
    }, token=token)

    entries = _parse_log_streams(data)
    entries.sort(key=lambda e: e.get("_loki_ts_ns", "0"), reverse=True)
    return entries


def list_applications(
    loki_url: str,
    since: Optional[str] = None,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List all application names that have log data.

    Uses GET /loki/api/v1/label/application/values.

    Args:
        loki_url: Base URL of the Loki instance
        since: Optional time bound (ISO or relative like "24h")
        token: Optional bearer token

    Returns:
        List of dicts with 'application' key, sorted alphabetically.
    """
    now = datetime.now(timezone.utc)
    start_dt = _parse_time_param(since) or (now - timedelta(days=30))
    params: Dict[str, str] = {
        "start": str(_to_ns(start_dt)),
        "end": str(_to_ns(now)),
    }

    data = _loki_get(loki_url, "/loki/api/v1/label/application/values", params, token=token)
    values = data.get("data", [])
    return [{"application": v} for v in sorted(values)]


def list_areas(
    loki_url: str,
    application: Optional[str] = None,
    since: Optional[str] = None,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List all area values, optionally scoped to an application.

    Uses GET /loki/api/v1/label/area/values with an optional match[] selector.

    Args:
        loki_url: Base URL of the Loki instance
        application: Optional application label to scope to
        since: Optional time bound (ISO or relative like "24h")
        token: Optional bearer token

    Returns:
        List of dicts with 'area' key, sorted alphabetically.
    """
    now = datetime.now(timezone.utc)
    start_dt = _parse_time_param(since) or (now - timedelta(days=30))
    params: Dict[str, str] = {
        "start": str(_to_ns(start_dt)),
        "end": str(_to_ns(now)),
    }
    if application:
        selector = build_stream_selector({"application": application})
        params["match[]"] = selector

    data = _loki_get(loki_url, "/loki/api/v1/label/area/values", params, token=token)
    values = data.get("data", [])
    return [{"area": v} for v in sorted(values)]


def list_operations(
    loki_url: str,
    application: Optional[str] = None,
    area: Optional[str] = None,
    component: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 50,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List recent operation IDs by querying log streams.

    Uses a LogQL query with json pipeline to extract distinct operation_id values.
    Falls back to a series query filtered by labels, then reads operation_id from
    the log lines.

    Args:
        loki_url: Base URL of the Loki instance
        application: Optional application label filter
        area: Optional area label filter
        component: Optional component label filter
        since: Lookback window (default "24h")
        limit: Max entries to scan for distinct operation IDs
        token: Optional bearer token

    Returns:
        List of dicts with 'operation_id' key, sorted alphabetically.
    """
    now = datetime.now(timezone.utc)
    start_dt = _parse_time_param(since or "24h") or (now - timedelta(hours=24))

    labels: Dict[str, str] = {}
    if application:
        labels["application"] = application
    if area:
        labels["area"] = area
    if component:
        labels["component"] = component

    selector = build_stream_selector(labels)
    query = f"{selector} | json"

    data = _loki_get(loki_url, "/loki/api/v1/query_range", {
        "query": query,
        "start": str(_to_ns(start_dt)),
        "end": str(_to_ns(now)),
        "limit": str(min(limit * 10, 5000)),  # overscan to find distinct IDs
        "direction": "backward",
    }, token=token)

    entries = _parse_log_streams(data)
    seen = set()
    results = []
    for entry in entries:
        op_id = entry.get("operation_id")
        if op_id and op_id not in seen:
            seen.add(op_id)
            results.append({"operation_id": op_id})
            if len(results) >= limit:
                break

    results.sort(key=lambda e: e["operation_id"])
    return results


def count_over_time(
    loki_url: str,
    app: str,
    interval: str = "5m",
    group_by: Optional[List[str]] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Aggregate log counts over a time interval.

    Maps to GET /loki/api/v1/query_range with a metric query.

    LogQL example:
        sum by (level) (count_over_time({application="my-app"}[5m]))

    Args:
        loki_url: Base URL of the Loki instance
        app: Application label to filter by
        interval: Duration window for count_over_time (e.g. "1m", "5m", "1h")
        group_by: Labels to group by (e.g. ["level", "component"])
        start: Range start as ISO timestamp or relative string
        end: Range end as ISO timestamp or relative string
    """
    now = datetime.now(timezone.utc)
    start_dt = _parse_time_param(start) or (now - timedelta(hours=1))
    end_dt = _parse_time_param(end) or now

    _validate_duration(interval)

    selector = build_stream_selector({"application": app})
    inner = f"count_over_time({selector}[{interval}])"

    if group_by:
        validated_labels = [_validate_label_name(lbl) for lbl in group_by]
        by_clause = ", ".join(validated_labels)
        query = f"sum by ({by_clause}) ({inner})"
    else:
        query = f"sum({inner})"

    data = _loki_get(loki_url, "/loki/api/v1/query_range", {
        "query": query,
        "start": str(_to_ns(start_dt)),
        "end": str(_to_ns(end_dt)),
        "step": interval,
    }, token=token)

    return _parse_metric_matrix(data)


# ---------------------------------------------------------------------------
# Operation- and error-centric queries (MCP dispatch targets)
# ---------------------------------------------------------------------------

# Levels treated as errors for bucketing / filtering. Mirrors the OpenSearch
# queries which use `{"terms": {"level": ["error", "critical"]}}`.
_ERROR_LEVELS = ("error", "critical")


def _ns_to_iso(ts_ns: Any) -> Optional[str]:
    """Convert a Loki nanosecond timestamp (str or int) to an ISO-8601 string."""
    if ts_ns is None:
        return None
    try:
        ns = int(ts_ns)
    except (TypeError, ValueError):
        return None
    seconds = ns / 1e9
    return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _build_base_labels(
    application: Optional[str],
    area: Optional[str],
    component: Optional[str],
    level: Optional[str] = None,
) -> Dict[str, str]:
    labels: Dict[str, str] = {}
    if application:
        labels["application"] = application
    if area:
        labels["area"] = area
    if component:
        labels["component"] = component
    if level:
        labels["level"] = level.lower()
    return labels


def get_last_errors(
    loki_url: str,
    application: Optional[str] = None,
    query: Optional[str] = None,
    area: Optional[str] = None,
    operation_id: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 1,
    component: Optional[str] = None,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch the most recent error/critical log entries.

    Since Loki does not support OR'ing label values in a single stream selector
    efficiently, we issue one query_range per error level and merge.
    """
    now = datetime.now(timezone.utc)
    start_dt = _parse_time_param(since) or (now - timedelta(hours=24))
    end_dt = _parse_time_param(until) or now

    merged: List[Dict[str, Any]] = []
    for level in _ERROR_LEVELS:
        labels = _build_base_labels(application, area, component, level=level)
        selector = build_stream_selector(labels)
        pipeline_parts = ["| json"]
        if operation_id:
            escaped_op = _escape_label_value(operation_id)
            pipeline_parts.append(f'| operation_id="{escaped_op}"')
        if query:
            escaped_q = query.replace("\\", "\\\\").replace('"', '\\"')
            pipeline_parts.append(f'|= "{escaped_q}"')
        logql = f"{selector} {' '.join(pipeline_parts)}".strip()

        data = _loki_get(loki_url, "/loki/api/v1/query_range", {
            "query": logql,
            "start": str(_to_ns(start_dt)),
            "end": str(_to_ns(end_dt)),
            "limit": str(limit),
            "direction": "backward",
        }, token=token)
        merged.extend(_parse_log_streams(data))

    merged.sort(key=lambda e: int(e.get("_loki_ts_ns") or 0), reverse=True)
    return merged[:limit]


def get_operation_logs(
    loki_url: str,
    operation_id: str,
    query: Optional[str] = None,
    level: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 100,
    application: Optional[str] = None,
    component: Optional[str] = None,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch logs for an operation in chronological order."""
    now = datetime.now(timezone.utc)
    start_dt = _parse_time_param(since) or (now - timedelta(hours=24))
    end_dt = _parse_time_param(until) or now

    labels = _build_base_labels(application, None, component, level=level)
    selector = build_stream_selector(labels)
    escaped_op = _escape_label_value(operation_id)
    pipeline_parts = ["| json", f'| operation_id="{escaped_op}"']
    if query:
        escaped_q = query.replace("\\", "\\\\").replace('"', '\\"')
        pipeline_parts.append(f'|= "{escaped_q}"')
    logql = f"{selector} {' '.join(pipeline_parts)}".strip()

    data = _loki_get(loki_url, "/loki/api/v1/query_range", {
        "query": logql,
        "start": str(_to_ns(start_dt)),
        "end": str(_to_ns(end_dt)),
        "limit": str(limit),
        "direction": "forward",
    }, token=token)

    entries = _parse_log_streams(data)
    entries.sort(key=lambda e: int(e.get("_loki_ts_ns") or 0))
    return entries


def get_operation_summary(
    loki_url: str,
    operation_id: str,
    application: Optional[str] = None,
    component: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Summarise an operation's logs by aggregating in Python."""
    entries = get_operation_logs(
        loki_url=loki_url,
        operation_id=operation_id,
        since=since,
        until=until,
        limit=5000,
        application=application,
        component=component,
        token=token,
    )
    if not entries:
        return None

    counts_by_level: Dict[str, int] = {}
    min_ns: Optional[int] = None
    max_ns: Optional[int] = None
    for entry in entries:
        lvl = (entry.get("level") or "").lower()
        if lvl:
            counts_by_level[lvl] = counts_by_level.get(lvl, 0) + 1
        ts_ns_raw = entry.get("_loki_ts_ns")
        try:
            ts_ns = int(ts_ns_raw) if ts_ns_raw is not None else None
        except (TypeError, ValueError):
            ts_ns = None
        if ts_ns is not None:
            if min_ns is None or ts_ns < min_ns:
                min_ns = ts_ns
            if max_ns is None or ts_ns > max_ns:
                max_ns = ts_ns

    error_count = sum(counts_by_level.get(level, 0) for level in _ERROR_LEVELS)
    sample_logs = entries[:10]

    return {
        "operation_id": operation_id,
        "counts_by_level": counts_by_level,
        "error_count": error_count,
        "start_time": _ns_to_iso(min_ns),
        "end_time": _ns_to_iso(max_ns),
        "total_entries": len(entries),
        "sample_logs": sample_logs,
    }


def list_recent_operations(
    loki_url: str,
    application: Optional[str] = None,
    area: Optional[str] = None,
    component: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 20,
    order_by: str = "last_activity",
    with_errors_only: bool = False,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List recent operations grouped from a log scan.

    Aggregates in Python — Loki lacks a server-side group_by on a JSON-payload
    field. Overscans up to 5000 entries to find distinct operations.
    """
    if order_by not in ("last_activity", "error_count"):
        order_by = "last_activity"

    now = datetime.now(timezone.utc)
    start_dt = _parse_time_param(since or "24h") or (now - timedelta(hours=24))
    end_dt = _parse_time_param(until) or now

    labels = _build_base_labels(application, area, component)
    selector = build_stream_selector(labels)
    logql = f"{selector} | json"

    data = _loki_get(loki_url, "/loki/api/v1/query_range", {
        "query": logql,
        "start": str(_to_ns(start_dt)),
        "end": str(_to_ns(end_dt)),
        "limit": str(min(limit * 50, 5000)),
        "direction": "backward",
    }, token=token)

    entries = _parse_log_streams(data)
    grouped: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        op_id = entry.get("operation_id")
        if not op_id:
            continue
        try:
            ts_ns = int(entry.get("_loki_ts_ns") or 0)
        except (TypeError, ValueError):
            ts_ns = 0
        lvl = (entry.get("level") or "").lower()
        bucket = grouped.setdefault(op_id, {
            "operation_id": op_id,
            "area": entry.get("area"),
            "min_ns": ts_ns,
            "max_ns": ts_ns,
            "total_logs": 0,
            "error_count": 0,
            "log_levels": {},
            "last_error_entry": None,
            "last_error_ns": 0,
        })
        bucket["total_logs"] += 1
        if lvl:
            bucket["log_levels"][lvl] = bucket["log_levels"].get(lvl, 0) + 1
        if ts_ns and ts_ns < bucket["min_ns"]:
            bucket["min_ns"] = ts_ns
        if ts_ns > bucket["max_ns"]:
            bucket["max_ns"] = ts_ns
        if lvl in _ERROR_LEVELS:
            bucket["error_count"] += 1
            if ts_ns >= bucket["last_error_ns"]:
                bucket["last_error_ns"] = ts_ns
                bucket["last_error_entry"] = entry

    operations = []
    for bucket in grouped.values():
        duration_ms = None
        if bucket["min_ns"] and bucket["max_ns"]:
            duration_ms = int((bucket["max_ns"] - bucket["min_ns"]) / 1e6)
        operations.append({
            "operation_id": bucket["operation_id"],
            "area": bucket["area"],
            "start_time": _ns_to_iso(bucket["min_ns"]) if bucket["min_ns"] else None,
            "end_time": _ns_to_iso(bucket["max_ns"]) if bucket["max_ns"] else None,
            "duration_ms": duration_ms,
            "total_logs": bucket["total_logs"],
            "error_count": bucket["error_count"],
            "log_levels": bucket["log_levels"],
            "last_activity": _ns_to_iso(bucket["max_ns"]) if bucket["max_ns"] else None,
            "last_error": bucket["last_error_entry"],
        })

    if with_errors_only:
        operations = [op for op in operations if op["error_count"] > 0]

    if order_by == "error_count":
        operations.sort(key=lambda op: (op["error_count"], op["last_activity"] or ""), reverse=True)
    else:
        operations.sort(key=lambda op: op["last_activity"] or "", reverse=True)

    return operations[:limit]


def list_error_signatures(
    loki_url: str,
    field: str = "exception",
    application: Optional[str] = None,
    area: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 20,
    min_count: int = 1,
    include_missing: bool = False,
    component: Optional[str] = None,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List error signatures by grouping error logs by a JSON-payload field."""
    field = field or "exception"

    now = datetime.now(timezone.utc)
    start_dt = _parse_time_param(since or "24h") or (now - timedelta(hours=24))
    end_dt = _parse_time_param(until) or now

    merged: List[Dict[str, Any]] = []
    for level in _ERROR_LEVELS:
        labels = _build_base_labels(application, area, component, level=level)
        selector = build_stream_selector(labels)
        logql = f"{selector} | json"
        data = _loki_get(loki_url, "/loki/api/v1/query_range", {
            "query": logql,
            "start": str(_to_ns(start_dt)),
            "end": str(_to_ns(end_dt)),
            "limit": "5000",
            "direction": "backward",
        }, token=token)
        merged.extend(_parse_log_streams(data))

    grouped: Dict[str, Dict[str, Any]] = {}
    missing: Dict[str, Any] = {"signature": None, "count": 0, "last_seen_ns": 0, "sample": None}
    for entry in merged:
        signature = entry.get(field)
        if not signature:
            if include_missing:
                missing["count"] += 1
                try:
                    ts_ns = int(entry.get("_loki_ts_ns") or 0)
                except (TypeError, ValueError):
                    ts_ns = 0
                if ts_ns >= missing["last_seen_ns"]:
                    missing["last_seen_ns"] = ts_ns
                    missing["sample"] = entry
            continue
        try:
            ts_ns = int(entry.get("_loki_ts_ns") or 0)
        except (TypeError, ValueError):
            ts_ns = 0
        bucket = grouped.setdefault(signature, {
            "signature": signature,
            "count": 0,
            "last_seen_ns": 0,
            "sample": None,
        })
        bucket["count"] += 1
        if ts_ns >= bucket["last_seen_ns"]:
            bucket["last_seen_ns"] = ts_ns
            bucket["sample"] = entry

    signatures = list(grouped.values())
    if include_missing and missing["count"] > 0:
        signatures.append(missing)

    signatures = [s for s in signatures if s["count"] >= min_count]
    signatures.sort(key=lambda s: s["count"], reverse=True)
    signatures = signatures[:limit]

    for s in signatures:
        s["last_seen"] = _ns_to_iso(s.pop("last_seen_ns"))

    return signatures


def get_error_context(
    loki_url: str,
    anchor_timestamp: str,
    operation_id: Optional[str] = None,
    area: Optional[str] = None,
    query: Optional[str] = None,
    level: Optional[str] = None,
    before: int = 20,
    after: int = 20,
    application: Optional[str] = None,
    component: Optional[str] = None,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch logs around an anchor timestamp."""
    anchor_dt = _parse_time_param(anchor_timestamp)
    if anchor_dt is None:
        raise ValueError(f"Invalid anchor_timestamp: {anchor_timestamp!r}")
    anchor_ns = _to_ns(anchor_dt)

    labels = _build_base_labels(application, area, component, level=level)
    selector = build_stream_selector(labels)
    pipeline_parts = ["| json"]
    if operation_id:
        escaped_op = _escape_label_value(operation_id)
        pipeline_parts.append(f'| operation_id="{escaped_op}"')
    if query:
        escaped_q = query.replace("\\", "\\\\").replace('"', '\\"')
        pipeline_parts.append(f'|= "{escaped_q}"')
    logql = f"{selector} {' '.join(pipeline_parts)}".strip()

    before_count = max(int(before or 0), 0)
    after_count = max(int(after or 0), 0)

    before_docs: List[Dict[str, Any]] = []
    if before_count > 0:
        lookback_start = anchor_dt - timedelta(hours=24)
        data = _loki_get(loki_url, "/loki/api/v1/query_range", {
            "query": logql,
            "start": str(_to_ns(lookback_start)),
            "end": str(anchor_ns),
            "limit": str(before_count + 1),
            "direction": "backward",
        }, token=token)
        before_docs = _parse_log_streams(data)
        before_docs.sort(key=lambda e: int(e.get("_loki_ts_ns") or 0))

    after_docs: List[Dict[str, Any]] = []
    if after_count > 0:
        lookahead_end = anchor_dt + timedelta(hours=24)
        data = _loki_get(loki_url, "/loki/api/v1/query_range", {
            "query": logql,
            "start": str(anchor_ns + 1),
            "end": str(_to_ns(lookahead_end)),
            "limit": str(after_count),
            "direction": "forward",
        }, token=token)
        after_docs = _parse_log_streams(data)
        after_docs.sort(key=lambda e: int(e.get("_loki_ts_ns") or 0))

    return before_docs + after_docs
