# Collector Output Plugins

The collector supports output plugins that allow log records to be delivered to backends beyond the built-in OpenSearch ingestor. Plugins receive validated, enriched `DevlogsRecord` objects and handle delivery to their target system.

## How It Works

The collector has three operating paths:

| DEVLOGS_FORWARD_URL | OpenSearch configured | Behavior |
|---|---|---|
| `http://` or `https://` | (ignored) | **Forward mode** -- raw-proxies the request body to the upstream URL |
| Plugin scheme (e.g. `loki://`) | (ignored) | **Plugin mode** -- validates, enriches, then calls plugin.send() |
| (not set) | yes | **Ingest mode** -- validates, enriches, writes to OpenSearch |
| (not set) | no | Error (503) |

In plugin mode, the collector performs the full ingest pipeline (JSON parsing, schema validation, token-based identity resolution, record enrichment with `collected_ts`, `client_ip`, and `identity`) and then passes the enriched records to the plugin for delivery.

## Using a Plugin

Install or define the plugin, then set `DEVLOGS_FORWARD_URL` to a URL with the plugin's scheme:

```bash
# Example: Loki plugin (hypothetical)
DEVLOGS_FORWARD_URL=loki://loki-host:3100 devlogs-collector serve
```

The collector auto-detects the URL scheme and dispatches to the registered plugin.

## Writing a Plugin

### 1. Subclass OutputPlugin

```python
from devlogs.collector.plugins import OutputPlugin, register_plugin
from devlogs.collector.errors import PluginError


class LokiPlugin(OutputPlugin):
    """Output plugin for Grafana Loki."""

    name = "loki"
    schemes = ["loki", "lokis"]

    def __init__(self, url, cfg):
        self.url = url
        self.cfg = cfg
        # Parse the URL, set up HTTP client, etc.
        # "loki://" maps to http, "lokis://" maps to https
        if url.startswith("lokis://"):
            self.push_url = "https://" + url[len("lokis://"):] + "/loki/api/v1/push"
        else:
            self.push_url = "http://" + url[len("loki://"):] + "/loki/api/v1/push"

    def send(self, records):
        """Push records to Loki."""
        import json
        import urllib.request
        import urllib.error

        # Convert devlogs records to Loki streams format
        streams = {}
        for record in records:
            labels = f'{{application="{record.application}", component="{record.component}"}}'
            if labels not in streams:
                streams[labels] = []
            doc = record.to_dict()
            streams[labels].append([
                str(int(_ts_to_epoch_ns(record.timestamp))),
                json.dumps(doc),
            ])

        payload = {
            "streams": [
                {"stream": _parse_labels(k), "values": v}
                for k, v in streams.items()
            ]
        }

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.push_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.cfg.opensearch_timeout) as resp:
                pass
        except urllib.error.HTTPError as e:
            raise PluginError(
                "LOKI_ERROR",
                f"Loki push failed ({e.code}): {e.read().decode('utf-8', errors='replace')}",
            )
        except urllib.error.URLError as e:
            raise PluginError(
                "CONNECTION_FAILED",
                f"Failed to connect to Loki: {e.reason}",
            )

        return {"ingested": len(records)}

    def check(self):
        """Check that Loki is reachable."""
        import urllib.request
        import urllib.error

        ready_url = self.push_url.replace("/loki/api/v1/push", "/ready")
        req = urllib.request.Request(ready_url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return f"Loki: OK ({resp.status})"
        except Exception as e:
            raise ConnectionError(f"Loki not reachable: {e}")

    def display_info(self):
        return f"Loki: {self.push_url}"


# Register the plugin so the collector can find it
register_plugin(LokiPlugin)
```

### 2. Register the Plugin

Call `register_plugin(YourPlugin)` at module load time. The collector looks up plugins by URL scheme when `DEVLOGS_FORWARD_URL` is set.

Registration happens automatically when the module containing the plugin is imported. To make your plugin discoverable, either:

- Place it in a module that gets imported during collector startup, or
- Add it to your project's entry points (for pip-installable plugins)

### 3. Plugin Interface Reference

Every plugin must implement these four methods:

#### `__init__(self, url: str, cfg: DevlogsConfig)`

Called each time the collector processes a request. Receives the full URL from `DEVLOGS_FORWARD_URL` and the collector config object.

- Parse the URL to extract host, port, path, credentials
- Set up any HTTP clients or connections

#### `send(self, records: List[DevlogsRecord]) -> Dict[str, Any]`

Deliver records to the backend. Each record is a `DevlogsRecord` dataclass with these fields already populated:

| Field | Type | Description |
|---|---|---|
| `application` | str | Application name (required) |
| `component` | str | Component name (required) |
| `timestamp` | str | ISO 8601 source timestamp (required) |
| `message` | str or None | Log message |
| `level` | str or None | Log level |
| `area` | str or None | Functional area |
| `operation_id` | str or None | Operation/transaction ID |
| `environment` | str or None | Deployment environment |
| `version` | str or None | Application version |
| `fields` | dict or None | Custom application data |
| `collected_ts` | str | Collector receive timestamp (set by collector) |
| `client_ip` | str | Submitting client IP (set by collector) |
| `identity` | dict | Resolved identity (set by collector) |

Use `record.to_dict()` to get a flat dictionary representation.

**Must return** a dict with at least `{"ingested": <count>}`.

**On failure**, raise `PluginError(subcode, message)`. The collector translates this into a structured HTTP error response with code `PLUGIN_FAILED`.

#### `check(self) -> str`

Test connectivity to the backend. Called by `devlogs-collector check`.

- Return a human-readable status string on success (e.g., `"Loki: OK"`)
- Raise an exception on failure

#### `display_info(self) -> str`

Return a one-line description for CLI output (e.g., `"Loki: http://loki:3100/loki/api/v1/push"`).

### 4. Error Handling

Use `PluginError` from `devlogs.collector.errors` for backend failures:

```python
from devlogs.collector.errors import PluginError

# Basic error (returns HTTP 502)
raise PluginError("CONNECTION_FAILED", "Cannot reach backend")

# Error with custom HTTP status
raise PluginError("RATE_LIMITED", "Backend rate limited", status_code=429)
```

The collector wraps `PluginError` into a structured JSON response:

```json
{
  "code": "PLUGIN_FAILED",
  "subcode": "CONNECTION_FAILED",
  "message": "Cannot reach backend"
}
```

## Class Attributes

| Attribute | Type | Description |
|---|---|---|
| `name` | str | Human-readable plugin name (used in CLI output) |
| `schemes` | list[str] | URL schemes this plugin handles (without `://`) |

A plugin can handle multiple schemes (e.g., `["loki", "lokis"]` for plain and TLS variants).

## Testing Plugins

Use `DevlogsRecord` directly to unit-test your plugin's `send()` method:

```python
from devlogs.collector.schema import DevlogsRecord

record = DevlogsRecord(
    application="test-app",
    component="api",
    timestamp="2024-01-15T10:30:00Z",
    message="Test message",
    level="info",
)
record.collected_ts = "2024-01-15T10:30:01Z"
record.client_ip = "127.0.0.1"
record.identity = {"mode": "anonymous"}

plugin = LokiPlugin("loki://localhost:3100", mock_config)
result = plugin.send([record])
assert result["ingested"] == 1
```

For integration tests with the collector server, see `tests/test_collector_plugins.py` for examples of how to register a test plugin and exercise the full HTTP -> validate -> enrich -> plugin.send() pipeline.

## Client-Side Plugins

Plugin URLs also work directly in `DevlogsHandler` and `DevlogsClient`, allowing applications to send logs to plugin backends without going through the collector.

When the URL scheme matches a registered plugin, records are converted to `DevlogsRecord` objects and delivered via `plugin.send()` instead of HTTP POST.

### DevlogsHandler

```python
from devlogs.handler import DevlogsHandler

handler = DevlogsHandler(
    application="my-app",
    component="api",
    collector_url="loki://loki-host:3100",
)
```

The handler detects the `loki://` scheme, resolves the registered plugin, and calls `plugin.send()` on each emit. Non-schema fields from the log record (logger name, pathname, line number, process, thread) are packed into the `fields` dict on the `DevlogsRecord`.

### DevlogsClient

```python
from devlogs.devlogs_client import DevlogsClient

client = DevlogsClient(
    collector_url="loki://loki-host:3100",
    application="my-app",
    component="api",
)
client.emit(message="Hello", level="info")
```

Both `emit()` and `emit_batch()` route through the plugin when a plugin URL is configured.

### MCP Server

The MCP server exposes an `emit_log` tool that writes logs through the same plugin routing. When `DEVLOGS_URL` points to a plugin scheme, the tool creates a `DevlogsClient` internally and routes through `plugin.send()`:

```json
{
  "name": "emit_log",
  "arguments": {
    "message": "Deployment complete",
    "level": "info",
    "collector_url": "loki://loki-host:3100"
  }
}
```

The `collector_url` argument is optional — if omitted, the tool uses the configured `DEVLOGS_URL`.

### CLI Diagnose

The `devlogs diagnose` command detects plugin mode and checks plugin connectivity:

```
$ DEVLOGS_URL=loki://loki-host:3100 devlogs diagnose
[OK] Mode: plugin (loki)
[OK] Plugin: Loki: OK (200)
[WARN] OpenSearch: Devlogs is disabled
```

When in collector/plugin mode, OpenSearch errors are reported as warnings instead of errors, since OpenSearch is not required.

### Notes

- Client-side plugin delivery skips collector-side enrichment (no `collected_ts`, `client_ip`, or `identity` fields).
- If no plugin is registered for the URL scheme, the URL is treated as a regular HTTP endpoint.
- Plugin resolution happens once during initialization, not on every emit.

## Configuration Summary

Plugins are activated by setting `DEVLOGS_FORWARD_URL` to a URL whose scheme matches a registered plugin. All other collector configuration (authentication, rate limits, payload size limits) applies normally.

| Variable | Effect in Plugin Mode |
|---|---|
| `DEVLOGS_FORWARD_URL` | Selects the plugin by URL scheme |
| `DEVLOGS_AUTH_MODE` | Authentication still enforced before plugin.send() |
| `DEVLOGS_TOKEN_MAP_KV` | Token-to-identity mapping still applied |
| `DEVLOGS_COLLECTOR_MAX_PAYLOAD_SIZE` | Payload size limits still enforced |
| `DEVLOGS_INDEX` | Not used (plugin determines its own routing) |
