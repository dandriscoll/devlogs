# Devlogs proxy server
#
# Routes external traffic to internal services:
#   POST /ingest/*  →  Collector (token-in-URL auth, unchanged)
#   GET  /query/*   →  Loki :3100 (Bearer token auth)
#   GET  /grafana/* →  Grafana :3000 (Bearer token auth)
#
# Environment variables:
#   COLLECTOR_URL     — Collector base URL (default: http://localhost:8081)
#   LOKI_URL          — Loki base URL     (default: http://localhost:3100)
#   GRAFANA_URL       — Grafana base URL  (default: http://localhost:3000)
#   LOKI_ADMIN_TOKEN  — Bearer token for /query and /grafana routes
#   PORT              — Port to listen on (default: 8080)
#
# Run:
#   python -m devlogs.proxy.server

import hmac
import logging
import os
import posixpath

try:
    from aiohttp import web, ClientSession, ClientTimeout
except ImportError as e:
    raise ImportError("aiohttp is required: pip install devlogs[proxy]") from e

logger = logging.getLogger("devlogs.proxy")

COLLECTOR_URL = os.environ.get("COLLECTOR_URL", "http://localhost:8081").rstrip("/")
LOKI_URL = os.environ.get("LOKI_URL", "http://localhost:3100").rstrip("/")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://localhost:3000").rstrip("/")
LOKI_ADMIN_TOKEN = os.environ.get("LOKI_ADMIN_TOKEN", "")
PORT = int(os.environ.get("PORT", "8080"))

_SKIP_HEADERS = frozenset({
    "host", "content-length", "transfer-encoding",
    "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto",
    "forwarded", "x-real-ip", "x-original-url", "x-rewrite-url",
})

_SKIP_RESPONSE_HEADERS = frozenset({
    "content-length", "transfer-encoding", "connection", "content-type",
})


def _proxy_headers(request: web.Request) -> dict:
    return {k: v for k, v in request.headers.items() if k.lower() not in _SKIP_HEADERS}


def _build_target(base: str, strip_prefix: str, request: web.Request) -> str:
    path = request.path.removeprefix(strip_prefix) or "/"
    path = posixpath.normpath(path)
    if not path.startswith("/"):
        path = "/" + path
    url = f"{base}{path}"
    if request.query_string:
        url += f"?{request.query_string}"
    return url


def _check_admin_token(request: web.Request) -> bool:
    if not LOKI_ADMIN_TOKEN:
        return False
    return hmac.compare_digest(
        request.headers.get("Authorization", ""),
        f"Bearer {LOKI_ADMIN_TOKEN}",
    )


async def handle_ingest(request: web.Request) -> web.Response:
    """Forward /ingest/* to Collector. Token in URL is passed through; Collector validates it."""
    target = _build_target(COLLECTOR_URL, "/ingest", request)
    body = await request.read()

    async with request.app["session"].request(
        method=request.method,
        url=target,
        headers=_proxy_headers(request),
        data=body,
        allow_redirects=False,
    ) as resp:
        resp_body = await resp.read()
        log_url = target.split("?")[0]
        logger.info("%s /ingest → %s %d", request.method, log_url, resp.status)
        content_type = resp.content_type or "application/octet-stream"
        return web.Response(status=resp.status, body=resp_body, content_type=content_type)


async def handle_query(request: web.Request) -> web.Response:
    """Validate Bearer token, strip /query prefix, forward to Loki."""
    if not _check_admin_token(request):
        return web.Response(status=401, text="Unauthorized")

    target = _build_target(LOKI_URL, "/query", request)
    body = await request.read()

    async with request.app["session"].request(
        method=request.method,
        url=target,
        headers=_proxy_headers(request),
        data=body,
        allow_redirects=False,
    ) as resp:
        resp_body = await resp.read()
        logger.info("%s /query → %s %d", request.method, target, resp.status)
        content_type = resp.content_type or "application/octet-stream"
        return web.Response(status=resp.status, body=resp_body, content_type=content_type)


async def handle_grafana(request: web.Request) -> web.Response:
    """Validate Bearer token, forward to Grafana preserving /grafana prefix (serve_from_sub_path)."""
    if not _check_admin_token(request):
        return web.Response(status=401, text="Unauthorized")

    target = _build_target(GRAFANA_URL, "", request)
    # Strip Authorization so Grafana uses its own session mechanism
    headers = {k: v for k, v in _proxy_headers(request).items() if k.lower() != "authorization"}
    body = await request.read()

    async with request.app["session"].request(
        method=request.method,
        url=target,
        headers=headers,
        data=body,
        allow_redirects=False,
    ) as resp:
        resp_body = await resp.read()
        logger.info("%s /grafana → %s %d", request.method, target, resp.status)
        resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in _SKIP_RESPONSE_HEADERS}
        content_type = resp.content_type or "application/octet-stream"
        return web.Response(status=resp.status, body=resp_body, content_type=content_type, headers=resp_headers)


async def on_startup(app: web.Application) -> None:
    timeout = ClientTimeout(total=30)
    app["session"] = ClientSession(timeout=timeout)


async def on_cleanup(app: web.Application) -> None:
    await app["session"].close()


def create_app() -> web.Application:
    app = web.Application(client_max_size=1024 * 1024)  # 1 MB
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    app.router.add_route("*", "/ingest", handle_ingest)
    app.router.add_route("*", "/ingest/{path_info:.*}", handle_ingest)
    app.router.add_route("*", "/query", handle_query)
    app.router.add_route("*", "/query/{path_info:.*}", handle_query)
    app.router.add_route("*", "/grafana", handle_grafana)
    app.router.add_route("*", "/grafana/{path_info:.*}", handle_grafana)

    return app


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    if not LOKI_ADMIN_TOKEN:
        logger.warning("LOKI_ADMIN_TOKEN is not set — /query and /grafana routes will reject all requests")

    app = create_app()
    web.run_app(app, host="0.0.0.0", port=PORT)
