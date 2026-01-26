# How to Integrate devlogs (v2.0)

Quick guide for adding devlogs to your Python project.

## Quick Start

### 1. Install
```bash
pip install devlogs
```

### 2. Start OpenSearch
```bash
docker-compose up -d opensearch  # Or use existing OpenSearch instance
```

### 3. Configure (create `.env`)
```bash
DEVLOGS_OPENSEARCH_HOST=localhost
DEVLOGS_OPENSEARCH_PORT=9200
DEVLOGS_OPENSEARCH_USER=admin
DEVLOGS_OPENSEARCH_PASS=YourPassword123!
DEVLOGS_INDEX=devlogs-myproject
```

### 4. Initialize
```bash
devlogs init
```

### 5. Integrate into Your Code

**Basic setup with DevlogsHandler:**
```python
import logging
from devlogs.handler import DevlogsHandler
from devlogs.opensearch.client import get_opensearch_client
from devlogs.config import load_config
from devlogs.build_info import resolve_build_info

# Resolve build info at startup (reads .build.json or env vars)
build_info = resolve_build_info(write_if_missing=True)

# Setup handler with required application and component
config = load_config()
client = get_opensearch_client()
handler = DevlogsHandler(
    application="my-app",      # Required: your application name
    component="api",           # Required: component within the app
    opensearch_client=client,
    index_name=config.index,
    environment="production",  # Optional
    version=build_info.build_id,  # Optional
)

logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.DEBUG)

# Logs automatically include application, component, level, and message
logging.info("Application started")
```

**Use operations to group related logs:**
```python
from devlogs.context import operation
import logging

logger = logging.getLogger(__name__)

# All logs in this block share the same operation_id
with operation(area="api"):
    logger.info("Request received")
    logger.debug("Processing data")
    logger.info("Request completed")
```

## Common Patterns

### Adding Custom Fields to Logs

Use the `features` extra to attach custom data (stored as `fields` in the record):
```python
import logging

logger = logging.getLogger(__name__)

# Custom fields attached to the log
logger.info("User login", extra={
    "features": {
        "user_id": "user-123",
        "login_method": "oauth",
    }
})
```

### Adding Build Info to All Logs

Use a logging adapter to automatically include build info in every log:
```python
import logging
from devlogs.build_info import resolve_build_info

build_info = resolve_build_info()

class BuildInfoAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.get('extra', {})
        features = extra.get('features', {})
        features.update({
            'build_id': self.extra['build_id'],
            'branch': self.extra['branch'],
        })
        extra['features'] = features
        kwargs['extra'] = extra
        return msg, kwargs

logger = BuildInfoAdapter(
    logging.getLogger(__name__),
    {'build_id': build_info.build_id, 'branch': build_info.branch}
)

logger.info("This log includes build_id automatically")
```

### Web Framework (Flask/FastAPI)
```python
from devlogs.context import operation
import uuid

@app.before_request
def before_request():
    g.operation_ctx = operation(operation_id=str(uuid.uuid4()), area="api")
    g.operation_ctx.__enter__()

@app.after_request
def after_request(response):
    if hasattr(g, 'operation_ctx'):
        g.operation_ctx.__exit__(None, None, None)
    return response
```

### Background Job
```python
from devlogs.context import operation

def my_job():
    with operation(area="scheduler"):
        logger.info("Job started")
        # do work
        logger.info("Job completed")
```

### CLI Script
```python
from devlogs.context import operation

with operation(area="cli"):
    logger.info("Script running")
    # your code
```

## View Logs

**CLI:**
```bash
devlogs tail --follow              # Tail all logs
devlogs tail --area api --follow   # Filter by area
devlogs search --q "error"         # Search logs
```

**Web UI:**
```bash
uvicorn devlogs.web.server:app --port 8088
# Open http://localhost:8088/ui/
```

## Test It

```bash
devlogs demo --duration 10 --count 50
devlogs tail --follow
```

## Key Concepts

- **application**: Required identifier for your application (e.g., `my-web-app`)
- **component**: Required identifier for the component (e.g., `api`, `worker`)
- **area**: Logical grouping (api, database, scheduler, etc.)
- **operation_id**: Auto-generated UUID linking related logs
- **operation() context**: Groups logs from a single request/job/transaction
- **build_id**: Stable identifier linking logs to a specific build/deployment

## Record Schema (v2.0)

The DevlogsHandler produces records with this structure:

```json
{
  "application": "my-app",
  "component": "api",
  "timestamp": "2024-01-15T10:30:00.123Z",
  "message": "User logged in",
  "level": "info",
  "area": "auth",
  "operation_id": "abc-123",
  "environment": "production",
  "version": "1.2.3",
  "fields": {"user_id": "123"},
  "source": {
    "logger": "myapp.auth",
    "pathname": "/app/auth.py",
    "lineno": 42,
    "funcName": "login"
  },
  "process": {
    "id": 12345,
    "thread": 140234567890
  }
}
```

See [HOWTO-DEVLOGS-FORMAT.md](HOWTO-DEVLOGS-FORMAT.md) for full schema documentation.

## Build Info in CI

Generate `.build.json` during your CI build:

**GitHub Actions:**
```yaml
- name: Generate build info
  run: |
    cat > .build.json << EOF
    {
      "build_id": "${{ github.ref_name }}-$(date -u +%Y%m%dT%H%M%SZ)",
      "branch": "${{ github.ref_name }}",
      "timestamp_utc": "$(date -u +%Y%m%dT%H%M%SZ)"
    }
    EOF
```

**Or use Python:**
```bash
python -c "from devlogs.build_info import generate_build_info_file; generate_build_info_file(allow_git=True)"
```

See [docs/build-info.md](docs/build-info.md) for full documentation.

## Migration from v1.x

If upgrading from devlogs v1.x, see [MIGRATION-V2.md](MIGRATION-V2.md) for:
- Handler parameter changes
- Schema field mapping
- OpenSearch query updates

## Best Practices

1. Set meaningful `application` and `component` values
2. Use consistent area names matching your architecture
3. Wrap related operations in `operation()` contexts
4. Log at appropriate levels (DEBUG, INFO, WARNING, ERROR)
5. Never log sensitive data (passwords, tokens, PII)
6. Add console handler as backup if OpenSearch goes down

## Troubleshooting

- **Can't connect**: Check OpenSearch is running (`curl http://localhost:9200`)
- **No logs**: Run `devlogs init` and verify handler is added
- **Auth error**: Check credentials in `.env` or use `devlogs diagnose`
- **Special characters in password**: Use `devlogs mkurl` to generate a properly URL-encoded connection string

### Using --url for Quick Testing

Test connection without modifying `.env`:

```bash
devlogs --url 'https://admin:pass@host:9200/index' diagnose
```

### Diagnosing Issues

Run diagnostics to check your setup:

```bash
devlogs diagnose
```

See [HOWTO-CLI.md](HOWTO-CLI.md) for complete CLI reference.
