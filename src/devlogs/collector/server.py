# Collector HTTP server
#
# Provides the HTTP API for log ingestion with support for:
# - Forward mode: proxy to upstream collector
# - Ingest mode: write directly to OpenSearch

import json
from typing import Optional

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse

from ..config import load_config
from ..opensearch.client import get_opensearch_client, OpenSearchError
from .schema import (
    DevlogsRecord,
    validate_record,
    normalize_records,
    enrich_record,
)
from .errors import (
    CollectorError,
    ValidationError,
    ConfigurationError,
    error_response,
)
from .auth import (
    extract_token_from_headers,
    parse_token_map_kv,
    parse_forward_index_map_kv,
    resolve_identity,
    AuthError,
)
from .forwarder import forward_request
from .ingestor import ingest_records

# Create FastAPI app for collector
app = FastAPI(
    title="Devlogs Collector",
    description="HTTP log collector for the devlogs format",
    version="1.0.0",
)


def get_client_ip(request: Request) -> str:
    """Extract client IP from request.

    Checks X-Forwarded-For header first (for proxied requests),
    then falls back to direct client connection.
    """
    # Check X-Forwarded-For header (from reverse proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first (leftmost) IP in the chain
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header (alternative proxy header)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fall back to direct client
    if request.client:
        return request.client.host

    return "unknown"


@app.exception_handler(CollectorError)
async def collector_error_handler(request: Request, exc: CollectorError):
    """Handle CollectorError exceptions with structured response."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


@app.get("/health")
async def health():
    """Health check endpoint."""
    cfg = load_config()
    mode = cfg.get_collector_mode()
    return {
        "status": "healthy",
        "mode": mode,
    }


@app.post("/v1/logs")
async def ingest_logs(request: Request):
    """Ingest log records.

    Accepts:
    - Single record: {"application": "...", "component": "...", "emitted_ts": "...", ...}
    - Batch: {"records": [...]}

    Returns 202 Accepted on success.
    """
    cfg = load_config()

    # Check Content-Type
    content_type = request.headers.get("Content-Type", "")
    if not content_type.startswith("application/json"):
        raise ValidationError(
            "INVALID_CONTENT_TYPE",
            f"Content-Type must be application/json, got: {content_type}"
        )

    # Read raw body
    try:
        body = await request.body()
    except Exception as e:
        raise ValidationError("READ_ERROR", f"Failed to read request body: {e}")

    # Check payload size limits (future provision - currently unlimited)
    if cfg.collector_max_payload_size > 0:
        if len(body) > cfg.collector_max_payload_size:
            raise ValidationError(
                "PAYLOAD_TOO_LARGE",
                f"Payload size {len(body)} exceeds limit {cfg.collector_max_payload_size}"
            )

    # Determine operating mode
    mode = cfg.get_collector_mode()

    if mode == "forward":
        return await _handle_forward_mode(request, cfg, body)
    elif mode == "ingest":
        return await _handle_ingest_mode(request, cfg, body)
    else:
        raise ConfigurationError(
            "Collector not configured. Set either DEVLOGS_FORWARD_URL or "
            "DEVLOGS_OPENSEARCH_* environment variables."
        )


async def _handle_forward_mode(request: Request, cfg, body: bytes) -> Response:
    """Handle request in forward mode."""
    auth_header = request.headers.get(cfg.auth_header)
    request_id = request.headers.get("X-Request-ID")
    content_type = request.headers.get("Content-Type", "application/json")

    status, response_body = forward_request(
        forward_url=cfg.forward_url,
        body=body,
        content_type=content_type,
        auth_header=auth_header,
        request_id=request_id,
        timeout=cfg.opensearch_timeout,
    )

    # If upstream returned 2xx, return 202
    if 200 <= status < 300:
        return Response(
            status_code=202,
            content=json.dumps({"status": "accepted", "forwarded": True}),
            media_type="application/json",
        )
    else:
        # This shouldn't happen - HTTPError should have been raised
        return JSONResponse(
            status_code=status,
            content=response_body,
        )


async def _handle_ingest_mode(request: Request, cfg, body: bytes) -> Response:
    """Handle request in ingest mode."""
    # Parse JSON payload
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise ValidationError("INVALID_JSON", f"Failed to parse JSON: {e}")

    # Normalize to record list
    raw_records = normalize_records(payload)

    # Validate each record
    validated_records = []
    payload_identities = []
    for i, raw in enumerate(raw_records):
        try:
            record = validate_record(raw)
            validated_records.append(record)
            # Preserve payload identity for passthrough mode
            payload_identities.append(raw.get("identity") if isinstance(raw, dict) else None)
        except ValidationError as e:
            # Include record index in error message for batches
            if len(raw_records) > 1:
                raise ValidationError(
                    e.subcode,
                    f"Record {i}: {e.message}"
                )
            raise

    # Get client info
    client_ip = get_client_ip(request)

    # Extract token from headers (precedence: Devlogs1 → Bearer → X-Devlogs-Token)
    authorization = request.headers.get("Authorization")
    x_devlogs_token = request.headers.get("X-Devlogs-Token")
    token, _token_source = extract_token_from_headers(authorization, x_devlogs_token)

    # Parse token map from config
    token_map = parse_token_map_kv(cfg.token_map_kv)

    # Resolve identity for each record
    enriched_records = []
    for i, record in enumerate(validated_records):
        try:
            identity = resolve_identity(
                auth_mode=cfg.auth_mode,
                token=token,
                token_map=token_map,
                payload_identity=payload_identities[i],
            )
            enriched_records.append(enrich_record(record, client_ip, identity))
        except AuthError as e:
            raise ValidationError(e.code, e.message)

    # Get OpenSearch client and ingest
    try:
        client = get_opensearch_client()
    except OpenSearchError as e:
        raise ConfigurationError(f"Failed to connect to OpenSearch: {e}")

    # Parse index routing map
    index_map = parse_forward_index_map_kv(cfg.forward_index_map_kv)

    result = ingest_records(client, cfg.index, enriched_records, index_map)

    return Response(
        status_code=202,
        content=json.dumps({
            "status": "accepted",
            "ingested": result["ingested"],
        }),
        media_type="application/json",
    )


def create_app():
    """Factory function for creating the collector app.

    Useful for ASGI servers and testing.
    """
    return app
