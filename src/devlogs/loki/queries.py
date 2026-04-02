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
    params: Dict[str, str] = {}
    now = datetime.now(timezone.utc)
    if since:
        start_dt = _parse_time_param(since) or (now - timedelta(hours=24))
        params["start"] = str(_to_ns(start_dt))
        params["end"] = str(_to_ns(now))

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
    params: Dict[str, str] = {}
    now = datetime.now(timezone.utc)
    if since:
        start_dt = _parse_time_param(since) or (now - timedelta(hours=24))
        params["start"] = str(_to_ns(start_dt))
        params["end"] = str(_to_ns(now))
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
