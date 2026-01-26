# Devlogs Collector Deployment Guide

This guide explains how to deploy the devlogs collector service for a coding agent or automated deployment system.

## Overview

The devlogs collector is a FastAPI-based HTTP service that receives log records from applications and either:
- **Ingest mode**: Writes directly to OpenSearch
- **Forward mode**: Proxies to an upstream collector

## Quick Reference

```bash
# Install
pip install devlogs

# Run collector
devlogs-collector serve --host 0.0.0.0 --port 8080

# Check configuration
devlogs-collector check
```

## Deployment Options

### Option 1: Docker (Recommended for Production)

#### Build the Image

```bash
docker build -f Dockerfile.collector -t devlogs-collector .
```

#### Run in Ingest Mode (Direct to OpenSearch)

```bash
docker run -d \
  --name devlogs-collector \
  -p 8080:8080 \
  -e DEVLOGS_OPENSEARCH_URL=https://admin:password@opensearch:9200/devlogs \
  devlogs-collector
```

#### Run in Forward Mode (Proxy to Upstream)

```bash
docker run -d \
  --name devlogs-collector \
  -p 8080:8080 \
  -e DEVLOGS_FORWARD_URL=https://central-collector.example.com \
  devlogs-collector
```

#### Docker Compose Example

```yaml
# docker-compose.yaml
version: '3.8'

services:
  collector:
    build:
      context: .
      dockerfile: Dockerfile.collector
    ports:
      - "8080:8080"
    environment:
      # Ingest mode configuration
      DEVLOGS_OPENSEARCH_URL: https://admin:password@opensearch:9200/devlogs
      # Or forward mode:
      # DEVLOGS_FORWARD_URL: https://upstream-collector:8080

      # Optional: Authentication
      DEVLOGS_AUTH_MODE: allow_anonymous

      # Optional: Performance tuning
      DEVLOGS_COLLECTOR_WORKERS: 4
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped

  opensearch:
    image: opensearchproject/opensearch:2.11.0
    environment:
      - discovery.type=single-node
      - OPENSEARCH_INITIAL_ADMIN_PASSWORD=MyStr0ngP@ss!
    ports:
      - "9200:9200"
    volumes:
      - opensearch-data:/usr/share/opensearch/data

volumes:
  opensearch-data:
```

### Option 2: Bare Metal / Systemd

#### Install Dependencies

```bash
# Create virtual environment
python3 -m venv /opt/devlogs-collector
source /opt/devlogs-collector/bin/activate

# Install devlogs package
pip install devlogs

# Or install from source
pip install -e /path/to/devlogs
```

#### Create Environment File

```bash
# /etc/devlogs/collector.env

# Mode: Set ONE of these

# Ingest mode (direct to OpenSearch)
DEVLOGS_OPENSEARCH_URL=https://admin:password@localhost:9200/devlogs

# OR Forward mode (proxy to upstream)
# DEVLOGS_FORWARD_URL=https://central-collector.example.com

# Server binding
DEVLOGS_COLLECTOR_HOST=0.0.0.0
DEVLOGS_COLLECTOR_PORT=8080
DEVLOGS_COLLECTOR_WORKERS=4
DEVLOGS_COLLECTOR_LOG_LEVEL=info

# Authentication (optional)
DEVLOGS_AUTH_MODE=allow_anonymous
```

#### Create Systemd Service

```ini
# /etc/systemd/system/devlogs-collector.service

[Unit]
Description=Devlogs Collector Service
After=network.target

[Service]
Type=simple
User=devlogs
Group=devlogs
EnvironmentFile=/etc/devlogs/collector.env
ExecStart=/opt/devlogs-collector/bin/devlogs-collector serve \
    --host ${DEVLOGS_COLLECTOR_HOST:-0.0.0.0} \
    --port ${DEVLOGS_COLLECTOR_PORT:-8080} \
    --workers ${DEVLOGS_COLLECTOR_WORKERS:-4} \
    --log-level ${DEVLOGS_COLLECTOR_LOG_LEVEL:-info}
Restart=always
RestartSec=5

# Security hardening
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
```

#### Enable and Start

```bash
# Create service user
sudo useradd -r -s /sbin/nologin devlogs

# Create config directory
sudo mkdir -p /etc/devlogs
sudo chown devlogs:devlogs /etc/devlogs

# Reload systemd and start
sudo systemctl daemon-reload
sudo systemctl enable devlogs-collector
sudo systemctl start devlogs-collector

# Check status
sudo systemctl status devlogs-collector
```

### Option 3: Direct Python Execution

For development or simple deployments:

```bash
# Set environment variables
export DEVLOGS_OPENSEARCH_URL=https://admin:password@localhost:9200/devlogs

# Run directly
devlogs-collector serve --host 0.0.0.0 --port 8080

# Or with uvicorn directly
uvicorn devlogs.collector.server:app --host 0.0.0.0 --port 8080 --workers 4
```

## Configuration Reference

### Required: Mode Selection

Set exactly ONE of these to determine operating mode:

| Variable | Description |
|----------|-------------|
| `DEVLOGS_OPENSEARCH_URL` | OpenSearch connection URL for ingest mode |
| `DEVLOGS_FORWARD_URL` | Upstream collector URL for forward mode |

### OpenSearch Connection (Ingest Mode)

URL format: `https://user:password@host:port/index`

Or use individual variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEVLOGS_OPENSEARCH_HOST` | `localhost` | OpenSearch hostname |
| `DEVLOGS_OPENSEARCH_PORT` | `9200` | OpenSearch port |
| `DEVLOGS_OPENSEARCH_USER` | `admin` | Username |
| `DEVLOGS_OPENSEARCH_PASS` | `admin` | Password |
| `DEVLOGS_INDEX` | `devlogs-0001` | Target index name |
| `DEVLOGS_OPENSEARCH_VERIFY_CERTS` | `true` | Verify TLS certificates |
| `DEVLOGS_OPENSEARCH_CA_CERT` | | Path to CA certificate |
| `DEVLOGS_OPENSEARCH_TIMEOUT` | `30` | Request timeout in seconds |

### Server Binding

| Variable | Default | Description |
|----------|---------|-------------|
| `DEVLOGS_COLLECTOR_HOST` | `0.0.0.0` | Bind address |
| `DEVLOGS_COLLECTOR_PORT` | `8080` | Listen port |
| `DEVLOGS_COLLECTOR_WORKERS` | `1` | Number of worker processes |
| `DEVLOGS_COLLECTOR_LOG_LEVEL` | `info` | Log level (debug/info/warning/error) |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `DEVLOGS_AUTH_MODE` | `allow_anonymous` | Auth mode (see below) |
| `DEVLOGS_TOKEN_MAP_KV` | | Token-to-identity mapping |

Auth modes:
- `allow_anonymous` - Accept all requests (default)
- `require_token_passthrough` - Require token, pass identity from payload
- `require_token_verified` - Require token, verify against token map

### Limits (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `DEVLOGS_COLLECTOR_RATE_LIMIT` | `0` | Requests per second (0 = unlimited) |
| `DEVLOGS_COLLECTOR_MAX_PAYLOAD_SIZE` | `0` | Max payload bytes (0 = unlimited) |

## API Endpoints

### POST /v1/logs

Ingest log records.

**Single record:**
```json
{
  "application": "myapp",
  "component": "api",
  "timestamp": "2026-01-25T12:00:00.000Z",
  "message": "Request processed",
  "level": "info"
}
```

**Batch:**
```json
{
  "records": [
    {"application": "myapp", "component": "api", "timestamp": "...", "message": "..."},
    {"application": "myapp", "component": "api", "timestamp": "...", "message": "..."}
  ]
}
```

**Response:** `202 Accepted`
```json
{
  "status": "accepted",
  "ingested": 2
}
```

### GET /health

Health check endpoint.

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "mode": "ingest"
}
```

## Health Checks and Monitoring

### HTTP Health Check

```bash
curl -f http://localhost:8080/health
```

### Configuration Check

```bash
devlogs-collector check
```

This verifies:
- Environment configuration is valid
- OpenSearch/upstream connectivity works
- Target index exists (ingest mode)

### Kubernetes Probes

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
```

## Sending Logs to the Collector

### From Python Applications

```python
from devlogs import DevlogsHandler
import logging

handler = DevlogsHandler(
    url="http://collector:8080",
    application="myapp",
    component="api"
)
logging.getLogger().addHandler(handler)
```

### From Jenkins

```groovy
devlogs(url: 'http://collector:8080', application: 'myapp') {
    sh 'make build'
}
```

### From curl (Testing)

```bash
curl -X POST http://localhost:8080/v1/logs \
  -H "Content-Type: application/json" \
  -d '{
    "application": "test",
    "component": "manual",
    "timestamp": "2026-01-25T12:00:00.000Z",
    "message": "Test log entry",
    "level": "info"
  }'
```

## Troubleshooting

### Check Configuration

```bash
devlogs-collector check
```

### View Logs

```bash
# Systemd
journalctl -u devlogs-collector -f

# Docker
docker logs -f devlogs-collector
```

### Common Issues

1. **"Collector not configured"**: Set either `DEVLOGS_OPENSEARCH_URL` or `DEVLOGS_FORWARD_URL`

2. **"Connection refused to OpenSearch"**: Verify OpenSearch is running and accessible

3. **"Index not found"**: Run `devlogs init` to create the index with proper mappings

4. **"Authentication failed"**: Check OpenSearch credentials in URL or environment

## Production Checklist

- [ ] Set appropriate number of workers (`DEVLOGS_COLLECTOR_WORKERS`)
- [ ] Configure TLS if collector is exposed externally
- [ ] Set up log rotation for collector logs
- [ ] Configure health check monitoring
- [ ] Set resource limits (CPU/memory) in container orchestration
- [ ] Consider rate limiting for public endpoints
- [ ] Enable authentication if accepting logs from untrusted sources
