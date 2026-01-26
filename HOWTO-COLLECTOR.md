# Devlogs Collector

The devlogs collector is an HTTP service that receives log records in the devlogs format and either forwards them to an upstream collector or ingests them directly into OpenSearch.

## Quick Start

### Running Locally

```bash
# Ingest mode: write directly to OpenSearch
DEVLOGS_OPENSEARCH_HOST=localhost DEVLOGS_INDEX=devlogs-myapp devlogs-collector serve

# Forward mode: proxy to upstream
DEVLOGS_FORWARD_URL=https://central-collector.example.com devlogs-collector serve
```

### Running with Docker

```bash
# Build the image
docker build -f Dockerfile.collector -t devlogs-collector .

# Run in ingest mode
docker run -p 8080:8080 \
  -e DEVLOGS_OPENSEARCH_URL=https://admin:pass@opensearch:9200/devlogs \
  devlogs-collector

# Run in forward mode
docker run -p 8080:8080 \
  -e DEVLOGS_FORWARD_URL=https://central-collector.example.com \
  devlogs-collector
```

## Operating Modes

The collector has two mutually exclusive operating modes:

### Forward Mode

When `DEVLOGS_FORWARD_URL` is set, the collector operates as a proxy:

- Forwards incoming requests to the configured upstream URL
- Preserves the request payload as-is (no parsing/validation)
- Forwards relevant headers (Content-Type, Authorization, X-Request-ID)
- Returns 202 Accepted if upstream returns 2xx
- Returns structured error if upstream fails

Use forward mode for:
- Edge collectors that aggregate before sending to a central collector
- Adding a local buffer/queue in front of a remote collector
- Multi-region deployments with regional collectors

### Ingest Mode

When OpenSearch admin connection is configured (and no forward URL), the collector ingests directly:

- Parses and validates the JSON payload
- Validates required schema fields (application, component, emitted_ts)
- Resolves identity from auth token (anonymous, verified, or passthrough)
- Enriches records with collector metadata (collected_ts, client_ip, identity)
- Routes records to appropriate index based on application (if configured)
- Writes to the configured OpenSearch index

Use ingest mode for:
- Direct integration with OpenSearch
- Single-tier deployments
- Development/testing

## API Reference

### POST /v1/logs

Submit log records for ingestion.

**Request:**
- Content-Type: `application/json`
- Body: Single record or batch

**Single Record:**
```json
{
  "application": "my-app",
  "component": "api-server",
  "emitted_ts": "2024-01-15T10:30:00.000Z",
  "environment": "production",
  "version": "1.2.3",
  "fields": {
    "message": "Request processed",
    "level": "info",
    "user_id": "123",
    "duration_ms": 45
  }
}
```

**Batch:**
```json
{
  "records": [
    {"application": "my-app", "component": "api", "emitted_ts": "..."},
    {"application": "my-app", "component": "worker", "emitted_ts": "..."}
  ]
}
```

**Response (Success):**
- Status: 202 Accepted
```json
{
  "status": "accepted",
  "ingested": 2
}
```

**Response (Error):**
- Status: 4xx/5xx
```json
{
  "code": "VALIDATION_FAILED",
  "subcode": "MISSING_FIELD",
  "message": "Missing required field: application"
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "mode": "ingest"
}
```

## Configuration

### Environment Variables

**Core Configuration:**

| Variable | Description | Default |
|----------|-------------|---------|
| `DEVLOGS_URL` | Collector base URL (informational, for clients) | - |
| `DEVLOGS_FORWARD_URL` | Upstream URL for forward mode | - |
| `DEVLOGS_OPENSEARCH_HOST` | OpenSearch host for ingest mode | localhost |
| `DEVLOGS_OPENSEARCH_PORT` | OpenSearch port | 9200 |
| `DEVLOGS_OPENSEARCH_USER` | OpenSearch username | admin |
| `DEVLOGS_OPENSEARCH_PASS` | OpenSearch password | admin |
| `DEVLOGS_OPENSEARCH_URL` | Full OpenSearch URL (overrides individual settings) | - |
| `DEVLOGS_INDEX` | Default target index name | devlogs-0001 |

**Authentication:**

| Variable | Description | Default |
|----------|-------------|---------|
| `DEVLOGS_AUTH_MODE` | Auth mode: `allow_anonymous`, `require_token_passthrough`, `require_token_verified` | allow_anonymous |
| `DEVLOGS_TOKEN_MAP_KV` | Token-to-identity mapping (KV format, see below) | - |

**Index Routing:**

| Variable | Description | Default |
|----------|-------------|---------|
| `DEVLOGS_FORWARD_INDEX_MAP_KV` | Per-application index routing (KV format) | - |
| `DEVLOGS_FORWARD_INTERNAL_INDEX` | Index for internal forwarder logs | - |

**Server Binding:**

| Variable | Description | Default |
|----------|-------------|---------|
| `DEVLOGS_COLLECTOR_HOST` | Host to bind to | 0.0.0.0 |
| `DEVLOGS_COLLECTOR_PORT` | Port to listen on | 8080 |
| `DEVLOGS_COLLECTOR_WORKERS` | Number of worker processes | 1 |
| `DEVLOGS_COLLECTOR_LOG_LEVEL` | Log level | info |

**Limits (Future Provisions):**

| Variable | Description | Default |
|----------|-------------|---------|
| `DEVLOGS_COLLECTOR_RATE_LIMIT` | Max requests/second (0 = unlimited) | 0 |
| `DEVLOGS_COLLECTOR_MAX_PAYLOAD_SIZE` | Max payload bytes (0 = unlimited) | 0 |

### Mode Selection Logic

1. If `DEVLOGS_FORWARD_URL` is set → Forward mode
2. Else if `DEVLOGS_OPENSEARCH_*` is configured → Ingest mode
3. Else → Error (returns 503)

## Authentication

The collector supports three authentication modes via `DEVLOGS_AUTH_MODE`:

### allow_anonymous (default)

Token is optional. If a valid token is provided and found in the token map, the identity is resolved to verified mode. Otherwise, identity is anonymous.

### require_token_passthrough

Token must be present (any value accepted). The token is not verified against the token map. If the payload includes an `identity` object, it's preserved as-is (passthrough mode). Otherwise, identity is anonymous.

Use this mode when an upstream system (API gateway, load balancer) has already validated the token and you want to preserve the identity from the payload.

### require_token_verified

Token must be present, properly formed (`dl1_<kid>_<secret>` format), and found in the token map. Returns 400 error if token is missing, malformed, or not recognized.

### Token Format

Tokens follow the format: `dl1_<kid>_<secret>`
- `dl1_` prefix (required)
- `kid`: 6-24 alphanumeric + underscore/hyphen characters
- `secret`: 32-64 alphanumeric + underscore/hyphen characters

Example: `dl1_myservice_1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p`

### Auth Headers

The collector extracts tokens from headers in this order of precedence:
1. `Authorization: Devlogs1 <token>` (devlogs-specific)
2. `Authorization: Bearer <token>` (standard OAuth)
3. `X-Devlogs-Token: <token>` (fallback header)

### Token-to-Identity Mapping

Configure `DEVLOGS_TOKEN_MAP_KV` to map tokens to identities:

```bash
# Format: <token>=<id>[,<name>][,<type>][,<tags>];<token>=...
# Tags format: k1:v1|k2:v2

DEVLOGS_TOKEN_MAP_KV="dl1_svc1_abc123...=service-1,My Service,service,team:backend|env:prod"
```

Percent-encoding required for reserved characters: `%; = , | :`

### Identity Object

Every ingested record includes an `identity` object with one of these modes:

**Anonymous:**
```json
{"identity": {"mode": "anonymous"}}
```

**Verified (from token map):**
```json
{
  "identity": {
    "mode": "verified",
    "id": "service-1",
    "name": "My Service",
    "type": "service",
    "tags": {"team": "backend", "env": "prod"}
  }
}
```

**Passthrough (from payload):**
```json
{
  "identity": {
    "mode": "passthrough",
    "custom_id": "abc",
    "role": "admin"
  }
}
```

## Index Routing

Configure per-application index routing with `DEVLOGS_FORWARD_INDEX_MAP_KV`:

```bash
# Format: <application>=<index>;<application>=...
DEVLOGS_FORWARD_INDEX_MAP_KV="app1=devlogs-app1;app2=devlogs-app2;jenkins=devlogs-ci"
```

Records from unmapped applications use `DEVLOGS_INDEX` as the default target.

## CLI Commands

### serve

Start the collector HTTP server.

```bash
devlogs-collector serve [OPTIONS]

Options:
  -h, --host TEXT       Host to bind to [default: 0.0.0.0]
  -p, --port INTEGER    Port to listen on [default: 8080]
  -w, --workers INTEGER Number of worker processes [default: 1]
  --reload              Enable auto-reload for development
  --log-level TEXT      Log level [default: info]
```

### check

Validate configuration and test connectivity.

```bash
devlogs-collector check
```

## Deployment

### Docker Compose

```yaml
version: '3.8'
services:
  collector:
    build:
      context: .
      dockerfile: Dockerfile.collector
    ports:
      - "8080:8080"
    environment:
      - DEVLOGS_OPENSEARCH_URL=https://admin:pass@opensearch:9200/devlogs
    depends_on:
      - opensearch
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  opensearch:
    image: opensearchproject/opensearch:latest
    # ... opensearch config
```

### Azure Container Apps (Documentation)

Deploy the collector to Azure Container Apps:

1. Build and push the container image:
   ```bash
   az acr build --registry myregistry --image devlogs-collector:latest -f Dockerfile.collector .
   ```

2. Create the Container App:
   ```bash
   az containerapp create \
     --name devlogs-collector \
     --resource-group mygroup \
     --environment myenv \
     --image myregistry.azurecr.io/devlogs-collector:latest \
     --target-port 8080 \
     --ingress external \
     --env-vars \
       DEVLOGS_OPENSEARCH_URL=secretref:opensearch-url \
     --secrets opensearch-url=<your-url>
   ```

3. Configure scaling:
   ```bash
   az containerapp update \
     --name devlogs-collector \
     --min-replicas 1 \
     --max-replicas 10 \
     --scale-rule-name http-rule \
     --scale-rule-type http \
     --scale-rule-http-concurrency 100
   ```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: devlogs-collector
spec:
  replicas: 3
  selector:
    matchLabels:
      app: devlogs-collector
  template:
    metadata:
      labels:
        app: devlogs-collector
    spec:
      containers:
      - name: collector
        image: devlogs-collector:latest
        ports:
        - containerPort: 8080
        env:
        - name: DEVLOGS_OPENSEARCH_URL
          valueFrom:
            secretKeyRef:
              name: devlogs-secrets
              key: opensearch-url
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: devlogs-collector
spec:
  selector:
    app: devlogs-collector
  ports:
  - port: 80
    targetPort: 8080
  type: LoadBalancer
```

## Python Client

Use the devlogs client to send logs from your Python application:

```python
from devlogs.devlogs_client import create_client

# Create a client
client = create_client(
    collector_url="http://localhost:8080",
    application="my-app",
    component="api-server",
    environment="production",
    version="1.2.3",
)

# Emit a single log
client.emit(
    message="Request processed",
    level="info",
    fields={"user_id": "123", "duration_ms": 45}
)

# Emit a batch
client.emit_batch([
    {"message": "Event 1", "level": "info"},
    {"message": "Event 2", "level": "warning", "fields": {"error": "timeout"}},
])
```

## Troubleshooting

### Collector returns 503 NOT_CONFIGURED

Neither forward URL nor OpenSearch connection is configured. Set either:
- `DEVLOGS_FORWARD_URL` for forward mode, or
- `DEVLOGS_OPENSEARCH_HOST` (or `DEVLOGS_OPENSEARCH_URL`) for ingest mode

### Validation errors

Ensure your payload includes the required fields:
- `application` (string)
- `component` (string)
- `emitted_ts` (ISO 8601 timestamp)

### Forward errors

Check that the upstream URL is reachable and accepting connections. Use `devlogs-collector check` to test connectivity.

### OpenSearch connection errors

Verify OpenSearch credentials and network connectivity. Use `devlogs diagnose` to check the connection.
