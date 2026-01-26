# Tests for collector configuration

import pytest
from devlogs import config


@pytest.fixture
def reset_config(monkeypatch):
    """Reset config state before each test."""
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    monkeypatch.setattr(config, "_custom_dotenv_path", None)
    # Clear all relevant env vars
    for key in config._DEVLOGS_CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)


class TestCollectorUrlConfig:
    """Tests for collector URL configuration."""

    def test_collector_url_default_empty(self, reset_config):
        cfg = config.load_config()
        assert cfg.collector_url == ""

    def test_collector_url_from_env(self, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_URL", "http://collector.example.com")
        cfg = config.load_config()
        assert cfg.collector_url == "http://collector.example.com"


class TestForwardUrlConfig:
    """Tests for forward URL configuration."""

    def test_forward_url_default_empty(self, reset_config):
        cfg = config.load_config()
        assert cfg.forward_url == ""

    def test_forward_url_from_env(self, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "http://upstream:8080")
        cfg = config.load_config()
        assert cfg.forward_url == "http://upstream:8080"


class TestCollectorModeSelection:
    """Tests for collector mode selection."""

    def test_mode_error_when_not_configured(self, reset_config):
        cfg = config.load_config()
        assert cfg.get_collector_mode() == "error"

    def test_mode_forward_when_forward_url_set(self, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "http://upstream:8080")
        cfg = config.load_config()
        assert cfg.get_collector_mode() == "forward"

    def test_mode_ingest_when_opensearch_host_set(self, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        cfg = config.load_config()
        assert cfg.get_collector_mode() == "ingest"

    def test_mode_ingest_when_opensearch_url_set(self, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_URL", "https://admin:pass@host:9200/index")
        cfg = config.load_config()
        assert cfg.get_collector_mode() == "ingest"

    def test_forward_takes_priority_over_ingest(self, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "http://upstream:8080")
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        cfg = config.load_config()
        assert cfg.get_collector_mode() == "forward"


class TestCollectorLimits:
    """Tests for rate limit and payload size limit configuration."""

    def test_rate_limit_default_unlimited(self, reset_config):
        cfg = config.load_config()
        assert cfg.collector_rate_limit == 0

    def test_rate_limit_from_env(self, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_COLLECTOR_RATE_LIMIT", "100")
        cfg = config.load_config()
        assert cfg.collector_rate_limit == 100

    def test_max_payload_size_default_unlimited(self, reset_config):
        cfg = config.load_config()
        assert cfg.collector_max_payload_size == 0

    def test_max_payload_size_from_env(self, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_COLLECTOR_MAX_PAYLOAD_SIZE", "1048576")
        cfg = config.load_config()
        assert cfg.collector_max_payload_size == 1048576


class TestAuthHeaderConfig:
    """Tests for auth header configuration."""

    def test_auth_header_default(self, reset_config):
        cfg = config.load_config()
        assert cfg.auth_header == "Authorization"

    def test_auth_header_from_env(self, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_AUTH_HEADER", "X-API-Key")
        cfg = config.load_config()
        assert cfg.auth_header == "X-API-Key"


class TestHasOpensearchConfig:
    """Tests for has_opensearch_config method."""

    def test_false_when_nothing_set(self, reset_config):
        cfg = config.load_config()
        assert cfg.has_opensearch_config() is False

    def test_true_when_host_set(self, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        cfg = config.load_config()
        assert cfg.has_opensearch_config() is True

    def test_true_when_url_set(self, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_URL", "https://admin:pass@host:9200")
        cfg = config.load_config()
        assert cfg.has_opensearch_config() is True
