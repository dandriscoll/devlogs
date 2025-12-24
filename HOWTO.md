# How to Integrate devlogs

Quick guide for adding devlogs to your Python project.

## Quick Start

### 1. Install
```bash
pip install -e /path/to/devlogs
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
DEVLOGS_INDEX_LOGS=devlogs-myproject
```

### 4. Initialize
```bash
devlogs init
```

### 5. Integrate into Your Code

**Basic setup:**
```python
import logging
from devlogs.handler import DiagnosticsHandler
from devlogs.opensearch.client import get_opensearch_client
from devlogs.config import load_config

# Setup handler
config = load_config()
client = get_opensearch_client()
handler = DiagnosticsHandler(opensearch_client=client, index_name=config.index_logs)

logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.DEBUG)
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

- **area**: Logical grouping (api, database, scheduler, etc.)
- **operation_id**: Auto-generated UUID linking related logs
- **operation() context**: Groups logs from a single request/job/transaction

## Best Practices

1. Use meaningful area names matching your architecture
2. Wrap related operations in `operation()` contexts
3. Log at appropriate levels (DEBUG, INFO, WARNING, ERROR)
4. Never log sensitive data (passwords, tokens, PII)
5. Add console handler as backup if OpenSearch goes down

## Troubleshooting

- **Can't connect**: Check OpenSearch is running (`curl http://localhost:9200`)
- **No logs**: Run `devlogs init` and verify handler is added
- **Auth error**: Check credentials in `.env`
