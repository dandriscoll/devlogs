# Tests for the collector output plugin model

import json
import os
import pytest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from devlogs.collector.plugins import (
    OutputPlugin,
    register_plugin,
    get_plugin_for_url,
    get_registered_schemes,
    list_plugins,
    dict_to_record,
    _registry,
)
from devlogs.collector.errors import PluginError
from devlogs.collector.server import app
from devlogs import config


# -- Fixtures ----------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_registry():
    """Clear the plugin registry before and after each test."""
    saved = dict(_registry)
    _registry.clear()
    yield
    _registry.clear()
    _registry.update(saved)


@pytest.fixture
def client():
    """Create a test client for the collector app."""
    return TestClient(app)


@pytest.fixture
def reset_config(monkeypatch):
    """Reset config state before each test."""
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    for key in (
        "DEVLOGS_URL",
        "DEVLOGS_FORWARD_URL",
        "DEVLOGS_OPENSEARCH_HOST",
        "DEVLOGS_OPENSEARCH_URL",
        "DEVLOGS_INDEX",
    ):
        monkeypatch.delenv(key, raising=False)


# -- Test helpers: a minimal concrete plugin ---------------------------------

class StubPlugin(OutputPlugin):
    """Minimal plugin for testing."""
    name = "stub"
    schemes = ["stub"]

    def __init__(self, url, cfg):
        self.url = url
        self.cfg = cfg
        self.sent_records = []

    def send(self, records):
        self.sent_records.extend(records)
        return {"ingested": len(records)}

    def check(self):
        return "Stub: OK"

    def display_info(self):
        return f"Stub: {self.url}"


class FailingPlugin(OutputPlugin):
    """Plugin that raises PluginError on send."""
    name = "failing"
    schemes = ["failing"]

    def __init__(self, url, cfg):
        self.url = url

    def send(self, records):
        raise PluginError("BACKEND_ERROR", "Backend unreachable")

    def check(self):
        raise ConnectionError("Cannot reach backend")

    def display_info(self):
        return f"Failing: {self.url}"


class MultiSchemePlugin(OutputPlugin):
    """Plugin that handles multiple URL schemes."""
    name = "multi"
    schemes = ["lokis", "loki"]

    def __init__(self, url, cfg):
        self.url = url

    def send(self, records):
        return {"ingested": len(records)}

    def check(self):
        return "Multi: OK"

    def display_info(self):
        return f"Multi: {self.url}"


class CrashingInitPlugin(OutputPlugin):
    """Plugin whose __init__ raises."""
    name = "crashinit"
    schemes = ["crashinit"]

    def __init__(self, url, cfg):
        raise RuntimeError("bad config value")

    def send(self, records): ...
    def check(self): ...
    def display_info(self): ...


class UnexpectedErrorPlugin(OutputPlugin):
    """Plugin whose send() raises a non-PluginError exception."""
    name = "unex"
    schemes = ["unex"]

    def __init__(self, url, cfg):
        self.url = url

    def send(self, records):
        raise ConnectionError("connection reset by peer")

    def check(self):
        return "OK"

    def display_info(self):
        return self.url


class NoneReturnPlugin(OutputPlugin):
    """Plugin whose send() returns None instead of a dict."""
    name = "nonereturn"
    schemes = ["nonereturn"]

    def __init__(self, url, cfg):
        self.url = url

    def send(self, records):
        return None

    def check(self):
        return "OK"

    def display_info(self):
        return self.url


class NoIngestedKeyPlugin(OutputPlugin):
    """Plugin whose send() returns a dict without 'ingested' key."""
    name = "nokey"
    schemes = ["nokey"]

    def __init__(self, url, cfg):
        self.url = url

    def send(self, records):
        return {"status": "ok"}

    def check(self):
        return "OK"

    def display_info(self):
        return self.url


# -- Registry tests ----------------------------------------------------------

class TestPluginRegistry:

    def test_register_and_lookup(self):
        register_plugin(StubPlugin)
        assert "stub" in get_registered_schemes()

    def test_get_plugin_for_url_returns_instance(self):
        register_plugin(StubPlugin)
        cfg = Mock()
        plugin = get_plugin_for_url("stub://localhost:9000", cfg)
        assert plugin is not None
        assert isinstance(plugin, StubPlugin)
        assert plugin.url == "stub://localhost:9000"

    def test_get_plugin_for_url_returns_none_for_http(self):
        register_plugin(StubPlugin)
        cfg = Mock()
        assert get_plugin_for_url("http://localhost:8080", cfg) is None

    def test_get_plugin_for_url_returns_none_for_https(self):
        register_plugin(StubPlugin)
        cfg = Mock()
        assert get_plugin_for_url("https://upstream:8080", cfg) is None

    def test_get_plugin_for_url_returns_none_for_no_scheme(self):
        register_plugin(StubPlugin)
        cfg = Mock()
        assert get_plugin_for_url("localhost:8080", cfg) is None

    def test_get_plugin_for_url_returns_none_for_unknown_scheme(self):
        register_plugin(StubPlugin)
        cfg = Mock()
        assert get_plugin_for_url("unknown://host", cfg) is None

    def test_multi_scheme_plugin(self):
        register_plugin(MultiSchemePlugin)
        cfg = Mock()
        assert get_plugin_for_url("loki://host:3100", cfg) is not None
        assert get_plugin_for_url("lokis://host:3100", cfg) is not None
        assert set(get_registered_schemes()) == {"loki", "lokis"}

    def test_list_plugins_deduplicates(self):
        register_plugin(MultiSchemePlugin)
        plugins = list_plugins()
        assert len(plugins) == 1
        assert plugins[0] is MultiSchemePlugin

    def test_register_plugin_rejects_empty_schemes(self):
        class BadPlugin(OutputPlugin):
            name = "bad"
            schemes = []
            def __init__(self, url, cfg): ...
            def send(self, records): ...
            def check(self): ...
            def display_info(self): ...

        with pytest.raises(ValueError, match="non-empty"):
            register_plugin(BadPlugin)

    def test_scheme_matching_is_case_insensitive(self):
        register_plugin(StubPlugin)
        cfg = Mock()
        assert get_plugin_for_url("STUB://host", cfg) is not None
        assert get_plugin_for_url("Stub://host", cfg) is not None

    def test_second_registration_overwrites_first(self):
        register_plugin(StubPlugin)
        register_plugin(MultiSchemePlugin)
        # MultiSchemePlugin doesn't handle "stub", so StubPlugin stays
        cfg = Mock()
        assert isinstance(get_plugin_for_url("stub://host", cfg), StubPlugin)

        # Now register a new plugin that claims "stub"
        class StubOverride(OutputPlugin):
            name = "override"
            schemes = ["stub"]
            def __init__(self, url, cfg): self.url = url
            def send(self, records): return {"ingested": 0}
            def check(self): return "OK"
            def display_info(self): return self.url

        register_plugin(StubOverride)
        assert isinstance(get_plugin_for_url("stub://host", cfg), StubOverride)

    def test_empty_registry_returns_empty(self):
        assert get_registered_schemes() == []
        assert list_plugins() == []

    def test_get_plugin_for_url_passes_cfg_to_constructor(self):
        register_plugin(StubPlugin)
        cfg = Mock()
        cfg.custom_setting = "hello"
        plugin = get_plugin_for_url("stub://host", cfg)
        assert plugin.cfg is cfg


# -- Plugin mode integration tests ------------------------------------------

class TestPluginModeIntegration:
    """Test plugin mode end-to-end with the collector server."""

    def _make_valid_record(self):
        return {
            "application": "test-app",
            "component": "api",
            "timestamp": "2024-01-15T10:30:00Z",
        }

    def test_plugin_receives_enriched_records(self, client, reset_config, monkeypatch):
        register_plugin(StubPlugin)
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "stub://backend:9000")

        # Patch get_plugin_for_url to return our tracked instance
        sent = []

        class TrackingPlugin(OutputPlugin):
            name = "stub"
            schemes = ["stub"]
            def __init__(self, url, cfg):
                self.url = url
            def send(self, records):
                sent.extend(records)
                return {"ingested": len(records)}
            def check(self):
                return "OK"
            def display_info(self):
                return self.url

        _registry["stub"] = TrackingPlugin

        response = client.post("/", json=self._make_valid_record())

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["ingested"] == 1

        # Verify the plugin received an enriched record
        assert len(sent) == 1
        record = sent[0]
        assert record.application == "test-app"
        assert record.component == "api"
        assert record.collected_ts is not None
        assert record.client_ip is not None
        assert record.identity is not None

    def test_plugin_receives_batch(self, client, reset_config, monkeypatch):
        sent = []

        class TrackingPlugin(OutputPlugin):
            name = "stub"
            schemes = ["stub"]
            def __init__(self, url, cfg):
                self.url = url
            def send(self, records):
                sent.extend(records)
                return {"ingested": len(records)}
            def check(self):
                return "OK"
            def display_info(self):
                return self.url

        _registry["stub"] = TrackingPlugin
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "stub://backend:9000")

        response = client.post("/", json={
            "records": [
                self._make_valid_record(),
                {
                    "application": "test-app",
                    "component": "worker",
                    "timestamp": "2024-01-15T10:30:01Z",
                },
            ]
        })

        assert response.status_code == 202
        assert response.json()["ingested"] == 2
        assert len(sent) == 2

    def test_plugin_error_returns_structured_response(self, client, reset_config, monkeypatch):
        register_plugin(FailingPlugin)
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "failing://backend:9000")

        response = client.post("/", json=self._make_valid_record())

        assert response.status_code == 502
        data = response.json()
        assert data["code"] == "PLUGIN_FAILED"
        assert data["subcode"] == "BACKEND_ERROR"

    def test_validation_still_runs_before_plugin(self, client, reset_config, monkeypatch):
        register_plugin(StubPlugin)
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "stub://backend:9000")

        # Missing required field
        response = client.post("/", json={"application": "test-app"})

        assert response.status_code == 400
        assert response.json()["code"] == "VALIDATION_FAILED"

    def test_http_url_still_uses_forward_mode(self, client, reset_config, monkeypatch):
        """Ensure http:// URLs bypass plugins and use raw forward mode."""
        register_plugin(StubPlugin)
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "http://upstream:8080")

        with patch("devlogs.collector.forwarder.urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.status = 202
            mock_response.read.return_value = b'{"status": "accepted"}'
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            response = client.post("/", json=self._make_valid_record())

        assert response.status_code == 202
        data = response.json()
        assert data["forwarded"] is True  # Forward mode, not plugin mode

    def test_ingest_mode_unchanged_with_plugins_registered(self, client, reset_config, monkeypatch):
        """Ensure ingest mode is unaffected by registered plugins."""
        register_plugin(StubPlugin)
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "test-index")

        mock_client = Mock()
        mock_client.index = Mock(return_value={})

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post("/", json=self._make_valid_record())

        assert response.status_code == 202
        assert response.json()["ingested"] == 1
        mock_client.index.assert_called_once()

    def test_non_plugin_error_from_send_returns_structured_response(self, client, reset_config, monkeypatch):
        """A bare exception from plugin.send() must not leak as a raw 500."""
        register_plugin(UnexpectedErrorPlugin)
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "unex://backend:9000")

        response = client.post("/", json=self._make_valid_record())

        assert response.status_code == 502
        data = response.json()
        assert data["code"] == "PLUGIN_FAILED"
        assert data["subcode"] == "UNEXPECTED_ERROR"
        assert "connection reset" in data["message"]

    def test_plugin_init_failure_returns_structured_response(self, client, reset_config, monkeypatch):
        """If the plugin constructor raises, we get a structured error, not a raw 500."""
        register_plugin(CrashingInitPlugin)
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "crashinit://backend:9000")

        response = client.post("/", json=self._make_valid_record())

        assert response.status_code == 502
        data = response.json()
        assert data["code"] == "PLUGIN_FAILED"
        assert data["subcode"] == "INIT_FAILED"
        assert "bad config value" in data["message"]

    def test_plugin_returning_none_does_not_crash(self, client, reset_config, monkeypatch):
        """send() returning None should not crash; fallback to record count."""
        register_plugin(NoneReturnPlugin)
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "nonereturn://backend:9000")

        response = client.post("/", json=self._make_valid_record())

        assert response.status_code == 202
        assert response.json()["ingested"] == 1  # Falls back to len(records)

    def test_plugin_omitting_ingested_key_falls_back(self, client, reset_config, monkeypatch):
        """send() returning {"status": "ok"} without 'ingested' key should fall back."""
        register_plugin(NoIngestedKeyPlugin)
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "nokey://backend:9000")

        response = client.post("/", json={
            "records": [
                self._make_valid_record(),
                {"application": "a", "component": "b", "timestamp": "2024-01-15T10:30:01Z"},
            ]
        })

        assert response.status_code == 202
        assert response.json()["ingested"] == 2  # Falls back to len(records)

    def test_auth_identity_flows_through_to_plugin(self, client, reset_config, monkeypatch):
        """Verified identity from token map should be visible in records sent to plugin."""
        sent = []

        class TrackingPlugin(OutputPlugin):
            name = "stub"
            schemes = ["stub"]
            def __init__(self, url, cfg): self.url = url
            def send(self, records):
                sent.extend(records)
                return {"ingested": len(records)}
            def check(self): return "OK"
            def display_info(self): return self.url

        _registry["stub"] = TrackingPlugin
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "stub://backend:9000")

        token = "dl1_testky_12345678901234567890123456789012"
        monkeypatch.setenv("DEVLOGS_TOKEN_MAP_KV", f"{token}=service-1,Test Service")

        response = client.post(
            "/",
            json=self._make_valid_record(),
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 202
        assert len(sent) == 1
        assert sent[0].identity["mode"] == "verified"
        assert sent[0].identity["id"] == "service-1"
        assert sent[0].identity["name"] == "Test Service"

    def test_require_token_verified_rejects_before_plugin(self, client, reset_config, monkeypatch):
        """Auth rejection must happen before plugin.send() is ever called."""
        sent = []

        class TrackingPlugin(OutputPlugin):
            name = "stub"
            schemes = ["stub"]
            def __init__(self, url, cfg): self.url = url
            def send(self, records):
                sent.extend(records)
                return {"ingested": len(records)}
            def check(self): return "OK"
            def display_info(self): return self.url

        _registry["stub"] = TrackingPlugin
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "stub://backend:9000")
        monkeypatch.setenv("DEVLOGS_AUTH_MODE", "require_token_verified")

        response = client.post("/", json=self._make_valid_record())

        assert response.status_code == 400
        assert response.json()["code"] == "VALIDATION_FAILED"
        assert len(sent) == 0  # Plugin was never called


# -- PluginError tests -------------------------------------------------------

class TestPluginError:

    def test_plugin_error_attributes(self):
        err = PluginError("TIMEOUT", "Request timed out")
        assert err.code == "PLUGIN_FAILED"
        assert err.subcode == "TIMEOUT"
        assert err.message == "Request timed out"
        assert err.status_code == 502

    def test_plugin_error_custom_status(self):
        err = PluginError("RATE_LIMITED", "Too many requests", status_code=429)
        assert err.status_code == 429

    def test_plugin_error_to_dict(self):
        err = PluginError("BACKEND_ERROR", "Connection refused")
        d = err.to_dict()
        assert d == {
            "code": "PLUGIN_FAILED",
            "subcode": "BACKEND_ERROR",
            "message": "Connection refused",
        }


# -- dict_to_record tests ---------------------------------------------------

class TestDictToRecord:

    def test_converts_minimal_dict(self):
        doc = {
            "application": "my-app",
            "component": "api",
            "timestamp": "2024-01-15T10:30:00Z",
        }
        record = dict_to_record(doc)
        assert record.application == "my-app"
        assert record.component == "api"
        assert record.timestamp == "2024-01-15T10:30:00Z"
        assert record.message is None
        assert record.level is None
        assert record.fields is None

    def test_packs_extra_keys_into_fields(self):
        doc = {
            "application": "my-app",
            "component": "api",
            "timestamp": "2024-01-15T10:30:00Z",
            "message": "hello",
            "logger": "test.logger",
            "pathname": "/path/to/file.py",
            "lineno": 42,
            "process": 1234,
            "thread": 5678,
        }
        record = dict_to_record(doc)
        assert record.message == "hello"
        assert record.fields is not None
        assert record.fields["logger"] == "test.logger"
        assert record.fields["pathname"] == "/path/to/file.py"
        assert record.fields["lineno"] == 42
        assert record.fields["process"] == 1234
        assert record.fields["thread"] == 5678

    def test_merges_extra_keys_with_existing_fields(self):
        doc = {
            "application": "my-app",
            "component": "api",
            "timestamp": "2024-01-15T10:30:00Z",
            "fields": {"user_id": "123"},
            "logger": "test.logger",
        }
        record = dict_to_record(doc)
        assert record.fields["user_id"] == "123"
        assert record.fields["logger"] == "test.logger"

    def test_handles_missing_optional_fields(self):
        doc = {}
        record = dict_to_record(doc)
        assert record.application == "unknown"
        assert record.component == "default"
        assert record.timestamp == ""
        assert record.message is None
        assert record.level is None
        assert record.area is None
        assert record.operation_id is None
        assert record.environment is None
        assert record.version is None
        assert record.fields is None

    def test_none_values_not_packed_into_fields(self):
        doc = {
            "application": "my-app",
            "component": "api",
            "timestamp": "2024-01-15T10:30:00Z",
            "funcname": None,
        }
        record = dict_to_record(doc)
        assert record.fields is None
