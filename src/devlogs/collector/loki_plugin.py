# Loki output plugin for the devlogs collector
#
# Activated by setting DEVLOGS_FORWARD_URL=loki://host:3100 (or lokis:// for TLS).
# Converts validated DevlogsRecord objects into Loki stream push payloads.
#
# Label strategy (low-cardinality only):
#   application, component, level, area, environment
#
# Everything else (message, operation_id, fields, etc.) is stored as a JSON
# log line and accessible via Loki's | json pipeline.

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import urlparse

from .errors import PluginError
from .plugins import OutputPlugin, register_plugin
from .schema import DevlogsRecord

# Labels promoted to Loki stream labels (kept low-cardinality)
_LOKI_LABEL_FIELDS = ("application", "component", "level", "area", "environment")


def _record_to_ns(record: DevlogsRecord) -> int:
    """Convert record timestamp to Unix nanoseconds for Loki."""
    ts_str = record.timestamp or record.collected_ts
    if not ts_str:
        return int(time.time() * 1e9)
    try:
        # fromisoformat() doesn't accept 'Z' suffix in Python < 3.11
        ts_clean = ts_str
        if ts_clean.endswith("Z"):
            ts_clean = ts_clean[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1e9)
    except Exception:
        return int(time.time() * 1e9)


def _build_log_line(record: DevlogsRecord) -> str:
    """Serialize the log record as a JSON log line for Loki storage."""
    payload: Dict[str, Any] = {}
    if record.message is not None:
        payload["message"] = record.message
    if record.operation_id is not None:
        payload["operation_id"] = record.operation_id
    payload["timestamp"] = record.timestamp
    if record.collected_ts is not None:
        payload["collected_ts"] = record.collected_ts
    if record.version is not None:
        payload["version"] = record.version
    if record.fields:
        payload["fields"] = record.fields
    return json.dumps(payload, ensure_ascii=False)


def _stream_key(record: DevlogsRecord) -> tuple:
    """Return a hashable key representing this record's Loki stream labels."""
    labels = []
    if record.application:
        labels.append(("application", record.application))
    if record.component:
        labels.append(("component", record.component))
    if record.level:
        labels.append(("level", record.level.lower()))
    if record.area:
        labels.append(("area", record.area))
    if record.environment:
        labels.append(("environment", record.environment))
    return tuple(labels)


class LokiOutputPlugin(OutputPlugin):
    """Pushes log records to Grafana Loki via the HTTP push API.

    URL schemes:
        loki://host:port   — plain HTTP
        lokis://host:port  — HTTPS
    """

    name = "loki"
    schemes = ["loki", "lokis"]

    def __init__(self, url: str, cfg: Any):
        parsed = urlparse(url)
        scheme = "https" if parsed.scheme == "lokis" else "http"
        host = parsed.hostname or "localhost"
        port = parsed.port or 3100
        base = f"{scheme}://{host}:{port}"
        self._push_url = f"{base}/loki/api/v1/push"
        self._ready_url = f"{base}/ready"
        self._display_url = url  # original url for display_info

    def send(self, records: List[DevlogsRecord]) -> Dict[str, Any]:
        """Push records to Loki, grouped into streams by label combination."""
        streams: Dict[tuple, list] = {}
        for record in records:
            key = _stream_key(record)
            if key not in streams:
                streams[key] = []
            ns = _record_to_ns(record)
            line = _build_log_line(record)
            streams[key].append([str(ns), line])

        payload = {
            "streams": [
                {"stream": dict(key), "values": values}
                for key, values in streams.items()
            ]
        }

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._push_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    # Loki returns 204 No Content on success
                    if resp.status in (200, 204):
                        return {"ingested": len(records)}
                    raise PluginError(
                        "UNEXPECTED_STATUS",
                        f"Loki push returned unexpected status {resp.status}",
                    )
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                try:
                    detail = e.read().decode("utf-8", errors="replace")[:300]
                except Exception:
                    detail = ""
                raise PluginError(
                    "HTTP_ERROR",
                    f"Loki push failed with HTTP {e.code}: {detail}",
                )
            except urllib.error.URLError as e:
                if attempt < 2:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise PluginError(
                    "SEND_FAILED",
                    f"Failed to connect to Loki: {e.reason}",
                )
            except PluginError:
                raise
            except Exception as e:
                if attempt < 2:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise PluginError("SEND_FAILED", f"Loki send failed: {e}")

        raise PluginError("SEND_FAILED", "Failed to push to Loki after retries")

    def check(self) -> str:
        """Verify Loki is reachable via its /ready endpoint."""
        try:
            req = urllib.request.Request(self._ready_url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return f"Loki: OK ({self._push_url})"
                return f"Loki: /ready returned {resp.status}"
        except Exception as e:
            raise Exception(f"Loki not reachable at {self._ready_url}: {e}")

    def display_info(self) -> str:
        return f"Loki: {self._display_url}"


# Self-register when this module is imported
register_plugin(LokiOutputPlugin)
