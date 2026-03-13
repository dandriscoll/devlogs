# Tests for the devlogs proxy server
#
# Run: pytest tests/test_proxy_server.py -v
# Requires: pip install devlogs[proxy] pytest-aiohttp

import pytest

aiohttp = pytest.importorskip("aiohttp", reason="requires devlogs[proxy]")
pytest.importorskip("pytest_asyncio", reason="requires pytest-asyncio")

import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from aiohttp import web

import devlogs.proxy.server as proxy_mod

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_response(status: int, body: bytes = b"ok", content_type: str = "application/json"):
    resp = AsyncMock()
    resp.status = status
    resp.content_type = content_type
    resp.read = AsyncMock(return_value=body)
    return resp


def make_mock_session(response):
    """Return a mock ClientSession whose .request() is an async context manager."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.request = MagicMock(return_value=cm)
    session.close = AsyncMock()
    return session


@pytest.fixture
def admin_token(monkeypatch):
    monkeypatch.setattr(proxy_mod, "LOKI_ADMIN_TOKEN", "test-secret")
    return "test-secret"


@pytest.fixture
def collector_url(monkeypatch):
    monkeypatch.setattr(proxy_mod, "COLLECTOR_URL", "http://collector:8081")


@pytest.fixture
def loki_url(monkeypatch):
    monkeypatch.setattr(proxy_mod, "LOKI_URL", "http://loki:3100")


@pytest.fixture
def grafana_url(monkeypatch):
    monkeypatch.setattr(proxy_mod, "GRAFANA_URL", "http://grafana:3000")


@pytest_asyncio.fixture
async def client(aiohttp_client, admin_token, collector_url, loki_url, grafana_url):
    app = proxy_mod.create_app()
    return await aiohttp_client(app)


# ---------------------------------------------------------------------------
# /ingest routing
# ---------------------------------------------------------------------------

class TestIngestRoute:
    async def test_forwards_post_to_collector(self, client):
        mock_resp = make_mock_response(202, b'{"status":"accepted"}')
        client.app["session"] = make_mock_session(mock_resp)

        resp = await client.post(
            "/ingest",
            data=b'{"application":"test","component":"c","message":"hi","level":"info"}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 202

    async def test_strips_ingest_prefix_when_forwarding(self, client):
        mock_resp = make_mock_response(202)
        session = make_mock_session(mock_resp)
        client.app["session"] = session

        await client.post("/ingest", data=b"{}")
        call_kwargs = session.request.call_args
        forwarded_url = call_kwargs[1]["url"] if call_kwargs[1] else call_kwargs[0][1]
        assert forwarded_url.startswith("http://collector:8081")
        assert "/ingest" not in forwarded_url

    async def test_preserves_query_string(self, client):
        mock_resp = make_mock_response(202)
        session = make_mock_session(mock_resp)
        client.app["session"] = session

        await client.post("/ingest?token=abc123", data=b"{}")
        call_kwargs = session.request.call_args
        forwarded_url = call_kwargs[1]["url"] if call_kwargs[1] else call_kwargs[0][1]
        assert "token=abc123" in forwarded_url

    async def test_no_auth_required(self, client):
        """Write side has no proxy-level auth — Collector handles it."""
        mock_resp = make_mock_response(202)
        client.app["session"] = make_mock_session(mock_resp)

        resp = await client.post("/ingest", data=b"{}")
        # Should not be rejected by the proxy (202 or whatever the collector returns)
        assert resp.status != 401

    async def test_forwards_collector_error_status(self, client):
        mock_resp = make_mock_response(401, b'{"code":"UNAUTHORIZED"}')
        client.app["session"] = make_mock_session(mock_resp)

        resp = await client.post("/ingest", data=b"{}")
        assert resp.status == 401

    async def test_nested_path_forwarded(self, client):
        mock_resp = make_mock_response(202)
        session = make_mock_session(mock_resp)
        client.app["session"] = session

        await client.post("/ingest/some/nested/path?token=abc", data=b"{}")
        call_kwargs = session.request.call_args
        forwarded_url = call_kwargs[1]["url"] if call_kwargs[1] else call_kwargs[0][1]
        assert "some/nested/path" in forwarded_url
        assert "token=abc" in forwarded_url


# ---------------------------------------------------------------------------
# /query routing
# ---------------------------------------------------------------------------

class TestQueryRoute:
    async def test_rejects_missing_token(self, client):
        resp = await client.get("/query/loki/api/v1/labels")
        assert resp.status == 401

    async def test_rejects_wrong_token(self, client):
        resp = await client.get(
            "/query/loki/api/v1/labels",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status == 401

    async def test_accepts_correct_token(self, client, admin_token):
        mock_resp = make_mock_response(200, b'{"data":[]}')
        client.app["session"] = make_mock_session(mock_resp)

        resp = await client.get(
            "/query/loki/api/v1/labels",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status == 200

    async def test_strips_query_prefix_when_forwarding(self, client, admin_token):
        mock_resp = make_mock_response(200, b"{}")
        session = make_mock_session(mock_resp)
        client.app["session"] = session

        await client.get(
            "/query/loki/api/v1/labels",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        call_kwargs = session.request.call_args
        forwarded_url = call_kwargs[1]["url"] if call_kwargs[1] else call_kwargs[0][1]
        assert forwarded_url == "http://loki:3100/loki/api/v1/labels"

    async def test_forwards_query_string_to_loki(self, client, admin_token):
        mock_resp = make_mock_response(200, b"{}")
        session = make_mock_session(mock_resp)
        client.app["session"] = session

        await client.get(
            '/query/loki/api/v1/query_range?query={app="x"}&limit=50',
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        call_kwargs = session.request.call_args
        forwarded_url = call_kwargs[1]["url"] if call_kwargs[1] else call_kwargs[0][1]
        assert "query=" in forwarded_url
        assert "limit=50" in forwarded_url


# ---------------------------------------------------------------------------
# /grafana routing
# ---------------------------------------------------------------------------

class TestGrafanaRoute:
    async def test_rejects_missing_token(self, client):
        resp = await client.get("/grafana/api/dashboards")
        assert resp.status == 401

    async def test_rejects_wrong_token(self, client):
        resp = await client.get(
            "/grafana/api/dashboards",
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status == 401

    async def test_accepts_correct_token(self, client, admin_token):
        mock_resp = make_mock_response(200, b"[]")
        client.app["session"] = make_mock_session(mock_resp)

        resp = await client.get(
            "/grafana/api/dashboards",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status == 200

    async def test_strips_authorization_before_forwarding_to_grafana(self, client, admin_token):
        """Authorization header should not be forwarded — Grafana manages its own sessions."""
        mock_resp = make_mock_response(200, b"[]")
        session = make_mock_session(mock_resp)
        client.app["session"] = session

        await client.get(
            "/grafana/api/dashboards",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        call_kwargs = session.request.call_args
        forwarded_headers = call_kwargs[1].get("headers", {})
        assert "authorization" not in {k.lower() for k in forwarded_headers}

    async def test_strips_grafana_prefix_when_forwarding(self, client, admin_token):
        mock_resp = make_mock_response(200, b"[]")
        session = make_mock_session(mock_resp)
        client.app["session"] = session

        await client.get(
            "/grafana/api/dashboards",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        call_kwargs = session.request.call_args
        forwarded_url = call_kwargs[1]["url"] if call_kwargs[1] else call_kwargs[0][1]
        assert forwarded_url == "http://grafana:3000/api/dashboards"


# ---------------------------------------------------------------------------
# Empty LOKI_ADMIN_TOKEN edge case
# ---------------------------------------------------------------------------

class TestNoAdminToken:
    async def test_query_rejects_all_when_token_unset(self, aiohttp_client, monkeypatch,
                                                       collector_url, loki_url, grafana_url):
        monkeypatch.setattr(proxy_mod, "LOKI_ADMIN_TOKEN", "")
        app = proxy_mod.create_app()
        client = await aiohttp_client(app)

        resp = await client.get("/query/loki/api/v1/labels",
                                headers={"Authorization": "Bearer anything"})
        assert resp.status == 401

    async def test_grafana_rejects_all_when_token_unset(self, aiohttp_client, monkeypatch,
                                                         collector_url, loki_url, grafana_url):
        monkeypatch.setattr(proxy_mod, "LOKI_ADMIN_TOKEN", "")
        app = proxy_mod.create_app()
        client = await aiohttp_client(app)

        resp = await client.get("/grafana/", headers={"Authorization": "Bearer anything"})
        assert resp.status == 401
