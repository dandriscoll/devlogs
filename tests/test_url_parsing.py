# Tests for URL parsing and detection (collector vs opensearch)

import os
import warnings
import pytest
from devlogs import config
from devlogs.config import (
	parse_url,
	_parse_opensearch_scheme_url,
	_parse_collector_url_config,
)


class TestParseUrlDetection:
	"""Tests for parse_url() auto-detection logic."""

	def test_opensearchs_scheme(self):
		result = parse_url("opensearchs://admin:pass@host:9200/myindex")
		assert type(result).__name__ == "OpenSearchURLConfig"
		assert result.scheme == "https"
		assert result.host == "host"
		assert result.port == 9200
		assert result.user == "admin"
		assert result.password == "pass"
		assert result.index == "myindex"

	def test_opensearch_scheme(self):
		result = parse_url("opensearch://admin:pass@host:9200/myindex")
		assert type(result).__name__ == "OpenSearchURLConfig"
		assert result.scheme == "http"
		assert result.host == "host"

	def test_https_with_user_and_pass_is_legacy_opensearch(self):
		with warnings.catch_warnings(record=True) as w:
			warnings.simplefilter("always")
			result = parse_url("https://user:pass@host:9200/myindex")
			assert type(result).__name__ == "OpenSearchURLConfig"
			assert len(w) == 1
			assert "deprecated" in str(w[0].message).lower()

	def test_https_with_token_only_is_collector(self):
		result = parse_url("https://mytoken@host:8080/path")
		assert type(result).__name__ == "CollectorURLConfig"
		assert result.token == "mytoken"
		assert "mytoken" not in result.url
		assert "host:8080/path" in result.url

	def test_https_with_token_query_param_is_collector(self):
		result = parse_url("https://host:8080/path?token=SECRET")
		assert type(result).__name__ == "CollectorURLConfig"
		assert result.token == "SECRET"
		assert "token=" not in result.url

	def test_plain_https_is_collector(self):
		result = parse_url("https://host:8080/path")
		assert type(result).__name__ == "CollectorURLConfig"
		assert result.token is None
		assert result.url == "https://host:8080/path"

	def test_empty_url_raises(self):
		with pytest.raises(ValueError):
			parse_url("")

	def test_invalid_scheme_raises(self):
		with pytest.raises(ValueError):
			parse_url("ftp://host:21/path")


class TestOpenSearchSchemeUrl:
	"""Tests for opensearchs:// (TLS) and opensearch:// (non-TLS) URL parsing."""

	def test_basic_tls(self):
		result = _parse_opensearch_scheme_url("opensearchs://user:pass@host:9200/idx")
		assert result.scheme == "https"
		assert result.host == "host"
		assert result.port == 9200
		assert result.user == "user"
		assert result.password == "pass"
		assert result.index == "idx"

	def test_basic_non_tls(self):
		result = _parse_opensearch_scheme_url("opensearch://user:pass@host:9200/idx")
		assert result.scheme == "http"

	def test_default_port_tls(self):
		result = _parse_opensearch_scheme_url("opensearchs://user:pass@host/idx")
		assert result.port == 443

	def test_default_port_non_tls(self):
		result = _parse_opensearch_scheme_url("opensearch://user:pass@host/idx")
		assert result.port == 9200

	def test_application_from_second_path_segment(self):
		result = _parse_opensearch_scheme_url("opensearchs://user:pass@host:9200/myindex/myapp")
		assert result.index == "myindex"
		assert result.application == "myapp"

	def test_no_application_single_segment(self):
		result = _parse_opensearch_scheme_url("opensearchs://user:pass@host:9200/myindex")
		assert result.index == "myindex"
		assert result.application is None

	def test_no_path(self):
		result = _parse_opensearch_scheme_url("opensearchs://user:pass@host:9200")
		assert result.index is None
		assert result.application is None

	def test_missing_hostname_raises(self):
		with pytest.raises(ValueError):
			_parse_opensearch_scheme_url("opensearch:///index")

	def test_url_decodes_credentials(self):
		result = _parse_opensearch_scheme_url("opensearchs://user%40dom:p%21ss@host:9200/idx")
		assert result.user == "user@dom"
		assert result.password == "p!ss"


class TestCollectorUrlConfig:
	"""Tests for _parse_collector_url_config."""

	def test_token_in_userinfo(self):
		result = _parse_collector_url_config("https://mytoken@host:8080/path")
		assert result.token == "mytoken"
		assert "mytoken" not in result.url
		assert result.url == "https://host:8080/path"

	def test_token_in_query(self):
		result = _parse_collector_url_config("https://host:8080/path?token=SECRET")
		assert result.token == "SECRET"
		assert "token=" not in result.url

	def test_token_query_preserves_other_params(self):
		result = _parse_collector_url_config("https://host:8080/path?token=SECRET&foo=bar")
		assert result.token == "SECRET"
		assert "foo=bar" in result.url
		assert "token=" not in result.url

	def test_no_token(self):
		result = _parse_collector_url_config("https://host:8080/path")
		assert result.token is None
		assert result.url == "https://host:8080/path"


class TestSetUrlBranching:
	"""Tests for set_url() routing to correct env var."""

	def test_collector_url_sets_devlogs_url(self, monkeypatch):
		monkeypatch.setattr(config, "_dotenv_loaded", True)
		for key in config._DEVLOGS_CONFIG_KEYS:
			monkeypatch.delenv(key, raising=False)

		config.set_url("https://TOKEN@host:8080/path")
		assert os.environ.get("DEVLOGS_URL") == "https://TOKEN@host:8080/path"
		# Clean up
		monkeypatch.delenv("DEVLOGS_URL", raising=False)

	def test_opensearch_url_sets_devlogs_url(self, monkeypatch):
		monkeypatch.setattr(config, "_dotenv_loaded", True)
		for key in config._DEVLOGS_CONFIG_KEYS:
			monkeypatch.delenv(key, raising=False)

		config.set_url("opensearchs://user:pass@host:9200/myindex")
		assert os.environ.get("DEVLOGS_URL") == "opensearchs://user:pass@host:9200/myindex"
		# Clean up
		monkeypatch.delenv("DEVLOGS_URL", raising=False)

	def test_legacy_https_opensearch_sets_devlogs_url(self, monkeypatch):
		monkeypatch.setattr(config, "_dotenv_loaded", True)
		for key in config._DEVLOGS_CONFIG_KEYS:
			monkeypatch.delenv(key, raising=False)

		with warnings.catch_warnings():
			warnings.simplefilter("ignore", DeprecationWarning)
			config.set_url("https://user:pass@host:9200/myindex")
		assert os.environ.get("DEVLOGS_URL") == "https://user:pass@host:9200/myindex"
		# Clean up
		monkeypatch.delenv("DEVLOGS_URL", raising=False)


class TestUrlModeProperty:
	"""Tests for DevlogsConfig.url_mode property."""

	def test_collector_mode(self, monkeypatch):
		monkeypatch.setattr(config, "_dotenv_loaded", True)
		for key in config._DEVLOGS_CONFIG_KEYS:
			monkeypatch.delenv(key, raising=False)
		monkeypatch.setenv("DEVLOGS_URL", "https://token@host:8080")
		cfg = config.load_config()
		assert cfg.url_mode == "collector"

	def test_opensearch_mode(self, monkeypatch):
		monkeypatch.setattr(config, "_dotenv_loaded", True)
		for key in config._DEVLOGS_CONFIG_KEYS:
			monkeypatch.delenv(key, raising=False)
		monkeypatch.setenv("DEVLOGS_OPENSEARCH_URL", "https://admin:pass@host:9200")
		cfg = config.load_config()
		assert cfg.url_mode == "opensearch"

	def test_none_mode(self, monkeypatch):
		monkeypatch.setattr(config, "_dotenv_loaded", True)
		for key in config._DEVLOGS_CONFIG_KEYS:
			monkeypatch.delenv(key, raising=False)
		cfg = config.load_config()
		assert cfg.url_mode == "none"


class TestParseOpensearchUrlWithNewSchemes:
	"""Tests for _parse_opensearch_url supporting opensearchs:// and opensearch:// schemes."""

	def test_opensearchs_scheme(self):
		result = config._parse_opensearch_url("opensearchs://admin:pass@host:9200/idx")
		assert result == ("https", "host", 9200, "admin", "pass", "idx")

	def test_opensearch_scheme(self):
		result = config._parse_opensearch_url("opensearch://admin:pass@host:9200/idx")
		assert result == ("http", "host", 9200, "admin", "pass", "idx")


class TestDevlogsConfigApplication:
	"""Tests for DevlogsConfig.application from opensearch URL."""

	def test_application_from_opensearch_url(self, monkeypatch):
		monkeypatch.setattr(config, "_dotenv_loaded", True)
		for key in config._DEVLOGS_CONFIG_KEYS:
			monkeypatch.delenv(key, raising=False)
		monkeypatch.setenv("DEVLOGS_OPENSEARCH_URL", "opensearch://admin:pass@host:9200/myindex/myapp")
		cfg = config.load_config()
		assert cfg.application == "myapp"
		assert cfg.index == "myindex"

	def test_no_application_without_second_segment(self, monkeypatch):
		monkeypatch.setattr(config, "_dotenv_loaded", True)
		for key in config._DEVLOGS_CONFIG_KEYS:
			monkeypatch.delenv(key, raising=False)
		monkeypatch.setenv("DEVLOGS_OPENSEARCH_URL", "opensearch://admin:pass@host:9200/myindex")
		cfg = config.load_config()
		assert cfg.application is None

	def test_no_application_with_legacy_url(self, monkeypatch):
		monkeypatch.setattr(config, "_dotenv_loaded", True)
		for key in config._DEVLOGS_CONFIG_KEYS:
			monkeypatch.delenv(key, raising=False)
		monkeypatch.setenv("DEVLOGS_OPENSEARCH_URL", "https://admin:pass@host:9200/myindex")
		cfg = config.load_config()
		assert cfg.application is None

	def test_no_application_with_env_vars(self, monkeypatch):
		monkeypatch.setattr(config, "_dotenv_loaded", True)
		for key in config._DEVLOGS_CONFIG_KEYS:
			monkeypatch.delenv(key, raising=False)
		monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
		cfg = config.load_config()
		assert cfg.application is None


class TestDevlogsClientTokenQuery:
	"""Tests for _parse_collector_url with ?token= param in devlogs_client."""

	def test_token_query_param(self):
		from devlogs.devlogs_client import _parse_collector_url
		url, token = _parse_collector_url("https://host:8080/path?token=SECRET")
		assert token == "SECRET"
		assert "token=" not in url

	def test_token_query_with_other_params(self):
		from devlogs.devlogs_client import _parse_collector_url
		url, token = _parse_collector_url("https://host:8080/path?token=SECRET&other=val")
		assert token == "SECRET"
		assert "other=val" in url
		assert "token=" not in url

	def test_no_token(self):
		from devlogs.devlogs_client import _parse_collector_url
		url, token = _parse_collector_url("https://host:8080/path")
		assert token is None
		assert url == "https://host:8080/path"
