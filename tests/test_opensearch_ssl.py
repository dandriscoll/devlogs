# Tests for DL-006: DEVLOGS_OPENSEARCH_VERIFY_CERTS / DEVLOGS_OPENSEARCH_CA_CERT
# must actually take effect via an ssl.SSLContext threaded through to urlopen.

import ssl
from unittest import mock

from devlogs.opensearch.client import build_ssl_context, LightweightOpenSearchClient


def test_verify_certs_false_returns_insecure_context():
    ctx = build_ssl_context(verify_certs=False, ca_cert="")
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is False
    assert ctx.verify_mode == ssl.CERT_NONE


def test_default_returns_none_for_os_trust_store():
    # verify on, no custom CA -> None (current/default behaviour, OS trust store)
    assert build_ssl_context(verify_certs=True, ca_cert="") is None


def test_verify_off_takes_precedence_over_ca_cert():
    # "off means off": verify_certs=False wins even if a ca_cert is provided.
    ctx = build_ssl_context(verify_certs=False, ca_cert="/some/ca.pem")
    assert ctx.verify_mode == ssl.CERT_NONE


def test_ca_cert_is_loaded_into_default_context():
    fake_ctx = mock.MagicMock()
    with mock.patch(
        "devlogs.opensearch.client.ssl.create_default_context",
        return_value=fake_ctx,
    ):
        result = build_ssl_context(verify_certs=True, ca_cert="/path/to/ca.pem")
    fake_ctx.load_verify_locations.assert_called_once_with("/path/to/ca.pem")
    assert result is fake_ctx


class _FakeResp:
    def __init__(self, body=b"{}"):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def test_client_passes_ssl_context_to_urlopen():
    # The load-bearing guarantee: the configured context object reaches urlopen.
    # If `context=self.ssl_context` is removed from _request, this test goes red.
    sentinel = object()
    client = LightweightOpenSearchClient(
        "host", 9200, "user", "pass", timeout=3, scheme="https", ssl_context=sentinel
    )
    captured = {}

    def fake_urlopen(req, timeout=None, context=None):
        captured["context"] = context
        return _FakeResp()

    with mock.patch(
        "devlogs.opensearch.client.urllib.request.urlopen", side_effect=fake_urlopen
    ):
        client._request("GET", "/")

    assert captured["context"] is sentinel


def test_client_default_ssl_context_is_none():
    client = LightweightOpenSearchClient("host", 9200, "user", "pass")
    assert client.ssl_context is None
