# Migration Guide

This guide covers required user actions when upgrading devlogs.

---

## From v2.0.x

### Environment Variable Change

Replace `DEVLOGS_OPENSEARCH_URL` with `DEVLOGS_URL`:

```bash
# Before
DEVLOGS_OPENSEARCH_URL=https://admin:password@host:9200/devlogs-prod

# After
DEVLOGS_URL=opensearchs://admin:password@host:9200/devlogs-prod
```

`DEVLOGS_OPENSEARCH_URL` still works but `DEVLOGS_URL` is now the standard.

### New URL Schemes

Use the new `opensearchs://` (TLS) and `opensearch://` (non-TLS) schemes for OpenSearch URLs:

```bash
# TLS (recommended)
opensearchs://admin:password@host:9200/index

# Non-TLS (local dev)
opensearch://admin:password@localhost:9200/index
```

The old `https://user:pass@host` format still works but shows a deprecation warning.

### Application Filter in URLs

To filter logs by application, add a second path segment:

```bash
# Index only
opensearchs://admin:password@host:9200/devlogs-prod

# Index + application filter
opensearchs://admin:password@host:9200/devlogs-prod/myapp
```

### Collector URL Path

If you were manually appending `/v1/logs` to collector URLs, remove it:

```bash
# Before
http://token@collector:8080/v1/logs

# After
http://token@collector:8080
```

### Jenkins Integration

The `jenkins attach` and `jenkins stop` CLI commands have been removed. Use the **Devlogs Jenkins Plugin** for real-time log streaming during builds.

The `jenkins snapshot` command remains for one-time log capture.

---

## From v1.x

### Handler Class Renamed

Change your import and add required parameters:

```python
# Before
from devlogs.handler import OpenSearchHandler

handler = OpenSearchHandler(
    opensearch_client=client,
    index_name="logs",
)

# After
from devlogs.handler import DevlogsHandler

handler = DevlogsHandler(
    application="my-app",     # Required
    component="api",          # Required
    opensearch_client=client,
    index_name="logs",
)
```

### Schema Field Changes

Update queries and dashboards for renamed/moved fields:

| v1.x Field | v2.0 Field |
|------------|------------|
| `logger_name` | `source.logger` |
| `pathname` | `source.pathname` |
| `lineno` | `source.lineno` |
| `funcName` | `source.funcName` |
| `levelno` | (removed) |
| `features` | `fields` |

New required fields: `application`, `component`

### OpenSearch Query Updates

```json
// Before
{"match": {"logger_name": "myapp.api"}}
{"term": {"levelno": 40}}

// After
{"match": {"source.logger": "myapp.api"}}
{"term": {"level": "error"}}
```

### DevlogsClient Changes

```python
# Before
client.emit(fields={"message": "Hello", "level": "info"})

# After
client.emit(message="Hello", level="info", area="web")
```

---

## Checklist

### From v2.0.x
- [ ] Replace `DEVLOGS_OPENSEARCH_URL` with `DEVLOGS_URL` in environment
- [ ] Update URLs to use `opensearchs://` or `opensearch://` scheme
- [ ] Remove `/v1/logs` suffix from any manual collector URLs
- [ ] If using Jenkins CLI streaming, switch to Jenkins Plugin

### From v1.x
- [ ] Add `application` and `component` parameters to handlers
- [ ] Update imports from `OpenSearchHandler` to `DevlogsHandler`
- [ ] Update OpenSearch queries for nested `source.*` fields
- [ ] Update dashboards and visualizations for new field names
