# Migration Guide: v1.x to v2.0.0

This guide describes how to migrate from devlogs v1.x to v2.0.0. Version 2.0 introduces a standardized record schema with breaking changes to field names and structure.

## Overview of Changes

### Breaking Changes

1. **Handler Renamed**: `OpenSearchHandler` is now `DevlogsHandler`
2. **Required Parameters**: `application` and `component` are now required parameters
3. **Schema Changes**: Field names and structure have changed (see table below)
4. **Features → Fields**: The `features` attribute is renamed to `fields`

### New Features

1. **Top-Level Log Fields**: `message`, `level`, and `area` are now top-level fields
2. **Source Object**: Logger metadata is now in a nested `source` object
3. **Process Object**: Process/thread info is in a nested `process` object
4. **Identity Support**: Collector adds `identity` object for authentication tracking
5. **Collector Timestamps**: `collected_ts` tracks when records were received

## Schema Changes

### Field Mapping

| v1.x Field | v2.0 Field | Notes |
|------------|------------|-------|
| `timestamp` | `timestamp` | Unchanged |
| `logger_name` | `source.logger` | Moved to nested object |
| `message` | `message` | Now top-level (was via formatter) |
| `level` | `level` | Now top-level string |
| `levelno` | (removed) | Use string `level` instead |
| `pathname` | `source.pathname` | Moved to nested object |
| `lineno` | `source.lineno` | Moved to nested object |
| `funcName` | `source.funcName` | Moved to nested object |
| `area` | `area` | Now top-level (was context-based) |
| `operation_id` | `operation_id` | Unchanged |
| `features` | `fields` | Renamed |
| (new) | `application` | Required - identifies the application |
| (new) | `component` | Required - identifies the component |
| (new) | `environment` | Optional - deployment environment |
| (new) | `version` | Optional - application version |
| (new) | `process.id` | Process ID |
| (new) | `process.thread` | Thread ID |

### Record Structure Comparison

**v1.x Record:**
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "logger_name": "myapp.api",
  "message": "Request processed",
  "level": "info",
  "levelno": 20,
  "pathname": "/app/api.py",
  "lineno": 42,
  "funcName": "handle_request",
  "area": "web",
  "operation_id": "req-123",
  "features": {
    "user_id": "user-456"
  }
}
```

**v2.0 Record:**
```json
{
  "application": "myapp",
  "component": "api",
  "timestamp": "2024-01-15T10:30:00Z",
  "message": "Request processed",
  "level": "info",
  "area": "web",
  "operation_id": "req-123",
  "fields": {
    "user_id": "user-456"
  },
  "source": {
    "logger": "myapp.api",
    "pathname": "/app/api.py",
    "lineno": 42,
    "funcName": "handle_request"
  },
  "process": {
    "id": 12345,
    "thread": 140234567890
  }
}
```

## Code Migration

### Handler Instantiation

**v1.x:**
```python
from devlogs.handler import OpenSearchHandler

handler = OpenSearchHandler(
    opensearch_client=client,
    index_name="logs",
    level=logging.INFO,
)
```

**v2.0:**
```python
from devlogs.handler import DevlogsHandler

handler = DevlogsHandler(
    application="my-app",     # Required
    component="api",          # Required
    opensearch_client=client,
    index_name="logs",
    level=logging.INFO,
    environment="production", # Optional
    version="1.2.3",         # Optional
)
```

**Backward Compatibility**: The `OpenSearchHandler` name still works as an alias:
```python
from devlogs.handler import OpenSearchHandler

# Still works, but application defaults to "unknown"
handler = OpenSearchHandler(
    application="my-app",
    component="api",
)
```

### Using Features/Fields

**v1.x:**
```python
logger.info("User logged in", extra={"features": {"user_id": "123"}})
```

**v2.0:**
```python
# "features" still works (extracted and renamed to "fields")
logger.info("User logged in", extra={"features": {"user_id": "123"}})
```

### DiagnosticsHandler

**v1.x:**
```python
from devlogs.handler import DiagnosticsHandler

handler = DiagnosticsHandler(
    opensearch_client=client,
    index_name="diagnostics",
)
```

**v2.0:**
```python
from devlogs.handler import DiagnosticsHandler

handler = DiagnosticsHandler(
    application="diagnostics",  # Optional, defaults to "diagnostics"
    component="default",        # Optional, defaults to "default"
    opensearch_client=client,
    index_name="diagnostics",
)
```

## DevlogsClient Migration

The `DevlogsClient` has been updated to use the v2.0 schema.

**v1.x:**
```python
from devlogs.devlogs_client import DevlogsClient

client = DevlogsClient(
    collector_url="http://localhost:8080",
    application="my-app",
    component="api",
)

# Message in fields
client.emit(fields={"message": "Hello", "level": "info"})
```

**v2.0:**
```python
from devlogs.devlogs_client import DevlogsClient

client = DevlogsClient(
    collector_url="http://localhost:8080",
    application="my-app",
    component="api",
    environment="production",  # Optional
    version="1.2.3",          # Optional
)

# Message at top level
client.emit(message="Hello", level="info", area="web")
```

## OpenSearch Index Migration

If you have existing data in OpenSearch, you'll need to update queries to use the new field names.

### Query Updates

**v1.x Query:**
```json
{
  "query": {
    "bool": {
      "must": [
        {"match": {"logger_name": "myapp.api"}},
        {"term": {"levelno": 40}}
      ]
    }
  }
}
```

**v2.0 Query:**
```json
{
  "query": {
    "bool": {
      "must": [
        {"match": {"source.logger": "myapp.api"}},
        {"term": {"level": "error"}}
      ]
    }
  }
}
```

### Index Template Update

Update your OpenSearch index template to include the new fields:

```json
{
  "mappings": {
    "properties": {
      "application": {"type": "keyword"},
      "component": {"type": "keyword"},
      "timestamp": {"type": "date"},
      "message": {"type": "text"},
      "level": {"type": "keyword"},
      "area": {"type": "keyword"},
      "environment": {"type": "keyword"},
      "version": {"type": "keyword"},
      "operation_id": {"type": "keyword"},
      "fields": {"type": "object", "dynamic": true},
      "source": {
        "properties": {
          "logger": {"type": "keyword"},
          "pathname": {"type": "keyword"},
          "lineno": {"type": "integer"},
          "funcName": {"type": "keyword"}
        }
      },
      "process": {
        "properties": {
          "id": {"type": "integer"},
          "thread": {"type": "long"}
        }
      },
      "collected_ts": {"type": "date"},
      "client_ip": {"type": "ip"},
      "identity": {
        "properties": {
          "mode": {"type": "keyword"},
          "id": {"type": "keyword"},
          "name": {"type": "keyword"},
          "type": {"type": "keyword"}
        }
      }
    }
  }
}
```

## Data Migration Script

If you need to migrate existing data, here's an example reindex script:

```python
from opensearchpy import OpenSearch

client = OpenSearch(...)

# Reindex with field transformation
body = {
    "source": {"index": "logs-v1"},
    "dest": {"index": "logs-v2"},
    "script": {
        "source": """
            // Rename fields
            ctx._source.source = [:];
            ctx._source.source.logger = ctx._source.remove('logger_name');
            ctx._source.source.pathname = ctx._source.remove('pathname');
            ctx._source.source.lineno = ctx._source.remove('lineno');
            ctx._source.source.funcName = ctx._source.remove('funcName');

            // Remove levelno
            ctx._source.remove('levelno');

            // Rename features to fields
            if (ctx._source.containsKey('features')) {
                ctx._source.fields = ctx._source.remove('features');
            }

            // Set defaults for new required fields
            if (!ctx._source.containsKey('application')) {
                ctx._source.application = 'unknown';
            }
            if (!ctx._source.containsKey('component')) {
                ctx._source.component = 'default';
            }
        """
    }
}

client.reindex(body=body)
```

## Checklist

- [ ] Update handler instantiation with `application` and `component`
- [ ] Update import from `OpenSearchHandler` to `DevlogsHandler` (optional but recommended)
- [ ] Review any code that reads `levelno` - use string `level` instead
- [ ] Update OpenSearch queries for nested `source.*` fields
- [ ] Update any dashboards or visualizations
- [ ] Consider migrating historical data if field consistency is important
- [ ] Test in staging before production deployment

## Need Help?

If you encounter issues during migration, please open an issue on GitHub with:
- Your current devlogs version
- The error message or unexpected behavior
- Relevant code snippets
