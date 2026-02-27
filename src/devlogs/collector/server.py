# Collector HTTP server
#
# Provides the HTTP API for log ingestion with support for:
# - Forward mode: proxy to upstream collector
# - Ingest mode: write directly to OpenSearch

import json
import logging
import platform
from contextlib import asynccontextmanager
from typing import Optional

logger = logging.getLogger("devlogs.collector")

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from ..config import load_config
from ..opensearch.client import get_opensearch_client, OpenSearchError
from .schema import (
    DevlogsRecord,
    validate_record,
    normalize_records,
    enrich_record,
    get_current_timestamp,
)
from .errors import (
    CollectorError,
    ValidationError,
    PluginError,
    ConfigurationError,
    error_response,
)
from .auth import (
    extract_token,
    parse_token_map_kv,
    parse_forward_index_map_kv,
    resolve_identity,
    AuthError,
)
from .forwarder import forward_request
from .ingestor import ingest_records
from .plugins import get_plugin_for_url
from ..version import __version__

# Register built-in output plugins by importing them (side-effect: register_plugin is called)
try:
    from . import loki_plugin as _loki_plugin  # noqa: F401
except ImportError:
    pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Emit a startup trace to the index so operators can see when the collector started."""
    cfg = load_config()
    mode = cfg.get_collector_mode()

    if mode == "ingest":
        try:
            client = get_opensearch_client()
            doc = DevlogsRecord(
                application="devlogs-collector",
                component="lifecycle",
                timestamp=get_current_timestamp(),
                message="Collector started",
                level="info",
                area="startup",
                version=__version__,
                fields={
                    "mode": mode,
                    "host": platform.node(),
                    "opensearch_host": cfg.opensearch_host,
                    "index": cfg.index,
                },
            )
            doc.collected_ts = get_current_timestamp()
            doc.client_ip = "127.0.0.1"
            doc._identity = {"mode": "internal"}
            client.index(index=cfg.index, body=doc.to_dict())
        except Exception:
            # Startup trace is best-effort; don't block the server
            pass

    yield

    # Emit shutdown trace
    if mode == "ingest":
        try:
            client = get_opensearch_client()
            doc = DevlogsRecord(
                application="devlogs-collector",
                component="lifecycle",
                timestamp=get_current_timestamp(),
                message="Collector stopped",
                level="info",
                area="shutdown",
                version=__version__,
                fields={
                    "mode": mode,
                    "host": platform.node(),
                },
            )
            doc.collected_ts = get_current_timestamp()
            doc.client_ip = "127.0.0.1"
            doc._identity = {"mode": "internal"}
            client.index(index=cfg.index, body=doc.to_dict())
        except Exception:
            pass


# Create FastAPI app for collector
app = FastAPI(
    title="Devlogs Collector",
    description="HTTP log collector for the devlogs format",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Devlogs-Token", "X-Request-ID"],
    max_age=86400,
)


def get_client_ip(request: Request) -> str:
    """Extract client IP from request.

    Returns a bare IPv4 or IPv6 address string (e.g. "192.168.1.5", "::1").
    No port, no brackets, no CIDR suffix.

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
    client_ip = get_client_ip(request)
    logger.warning("%s %d %s: %s", client_ip, exc.status_code, exc.subcode, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )



@app.post("/")
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
    client_ip = get_client_ip(request)
    logger.info("%s POST / (%d bytes)", client_ip, len(body))

    if mode == "forward":
        try:
            plugin = get_plugin_for_url(cfg.forward_url, cfg)
        except Exception as e:
            raise PluginError(
                "INIT_FAILED",
                f"Failed to initialize plugin for {cfg.forward_url}: {e}",
            )
        if plugin:
            return await _handle_plugin_mode(request, cfg, body, plugin)
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

    client_ip = get_client_ip(request)

    # If upstream returned 2xx, return 202
    if 200 <= status < 300:
        logger.info("%s 202 forwarded", client_ip)
        return Response(
            status_code=202,
            content=json.dumps({"status": "accepted", "forwarded": True}),
            media_type="application/json",
        )
    else:
        # This shouldn't happen - HTTPError should have been raised
        logger.warning("%s %d forward failed", client_ip, status)
        return JSONResponse(
            status_code=status,
            content=response_body,
        )


def _validate_and_enrich_records(request: Request, cfg, body: bytes):
    """Parse, validate, and enrich records from request body.

    Shared by ingest mode and plugin mode. Handles JSON parsing,
    schema validation, token extraction, identity resolution, and
    record enrichment.

    Returns:
        List of enriched DevlogsRecord objects
    """
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

    # Extract token (precedence: Bearer header → X-Devlogs-Token → URL userinfo → ?token=)
    authorization = request.headers.get("Authorization")
    x_devlogs_token = request.headers.get("X-Devlogs-Token")
    url_userinfo = request.url.username if hasattr(request.url, 'username') else None
    url_query_token = request.query_params.get("token")
    token, _token_source = extract_token(
        authorization, x_devlogs_token, url_userinfo, url_query_token
    )

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

    return enriched_records


async def _handle_ingest_mode(request: Request, cfg, body: bytes) -> Response:
    """Handle request in ingest mode."""
    enriched_records = _validate_and_enrich_records(request, cfg, body)

    # Get OpenSearch client and ingest
    try:
        client = get_opensearch_client()
    except OpenSearchError as e:
        raise ConfigurationError(f"Failed to connect to OpenSearch: {e}")

    # Parse index routing map
    index_map = parse_forward_index_map_kv(cfg.forward_index_map_kv)

    result = ingest_records(client, cfg.index, enriched_records, index_map)
    client_ip = get_client_ip(request)
    logger.info("%s 202 ingested %d record(s)", client_ip, result["ingested"])

    return Response(
        status_code=202,
        content=json.dumps({
            "status": "accepted",
            "ingested": result["ingested"],
        }),
        media_type="application/json",
    )


async def _handle_plugin_mode(request: Request, cfg, body: bytes, plugin) -> Response:
    """Handle request in plugin mode.

    Validates and enriches records like ingest mode, then delegates
    to the output plugin for delivery.
    """
    enriched_records = _validate_and_enrich_records(request, cfg, body)

    try:
        result = plugin.send(enriched_records)
    except PluginError:
        raise
    except Exception as e:
        raise PluginError(
            "UNEXPECTED_ERROR",
            f"Plugin '{plugin.name}' failed: {e}",
        )

    if not isinstance(result, dict):
        result = {}

    ingested = result.get("ingested", len(enriched_records))
    client_ip = get_client_ip(request)
    logger.info("%s 202 plugin '%s' ingested %d record(s)", client_ip, plugin.name, ingested)

    return Response(
        status_code=202,
        content=json.dumps({
            "status": "accepted",
            "ingested": ingested,
        }),
        media_type="application/json",
    )


def create_app():
    """Factory function for creating the collector app.

    Useful for ASGI servers and testing.
    """
    return app
