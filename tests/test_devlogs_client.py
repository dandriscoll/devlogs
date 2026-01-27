# Tests for the Devlogs client library

import json
import pytest
from unittest.mock import Mock, patch

from devlogs.devlogs_client import DevlogsClient, create_client, emit_log, _parse_collector_url


class TestParseCollectorUrl:
    """Tests for URL parsing - distinguishes collector vs OpenSearch URLs."""

    def test_no_userinfo(self):
        """Plain URL without credentials."""
        url, token = _parse_collector_url("http://localhost:8080")
        assert url == "http://localhost:8080"
        assert token is None

    def test_collector_url_token_in_username(self):
        """Collector URL: token in username position only."""
        url, token = _parse_collector_url("http://mytoken@localhost:8080")
        assert url == "http://localhost:8080"
        assert token == "mytoken"

    def test_opensearch_url_user_and_password(self):
        """OpenSearch URL: both username and password - keep credentials in URL."""
        url, token = _parse_collector_url("http://admin:secretpass@localhost:9200")
        assert url == "http://admin:secretpass@localhost:9200"
        assert token is None

    def test_opensearch_url_preserves_all_parts(self):
        """OpenSearch URL preserves scheme, path, query."""
        url, token = _parse_collector_url("https://user:pass@opensearch.example.com:9200/_bulk?refresh=true")
        assert url == "https://user:pass@opensearch.example.com:9200/_bulk?refresh=true"
        assert token is None

    def test_collector_url_preserves_port(self):
        url, token = _parse_collector_url("http://token@localhost:9999")
        assert url == "http://localhost:9999"
        assert token == "token"

    def test_collector_url_preserves_path(self):
        url, token = _parse_collector_url("http://token@localhost:8080/path/to/api")
        assert url == "http://localhost:8080/path/to/api"
        assert token == "token"

    def test_collector_url_https_scheme(self):
        url, token = _parse_collector_url("https://token@example.com")
        assert url == "https://example.com"
        assert token == "token"

    def test_collector_url_encoded_token(self):
        url, token = _parse_collector_url("http://my%3Atoken%40special@localhost:8080")
        assert url == "http://localhost:8080"
        assert token == "my:token@special"

    def test_empty_url(self):
        url, token = _parse_collector_url("")
        assert url == ""
        assert token is None

    def test_devlogs_token_format(self):
        url, token = _parse_collector_url("http://dl1_myapp_abcdefghijklmnopqrstuvwxyz123456@localhost:8080")
        assert url == "http://localhost:8080"
        assert token == "dl1_myapp_abcdefghijklmnopqrstuvwxyz123456"


class TestDevlogsClient:
    """Tests for the DevlogsClient class."""

    def test_builds_minimal_record(self):
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
        )
        record = client._build_record(message="Hello")
        assert record["application"] == "test-app"
        assert record["component"] == "api"
        assert "timestamp" in record
        # message is now a top-level field
        assert record["message"] == "Hello"

    def test_builds_record_with_level(self):
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
        )
        record = client._build_record(message="Error!", level="error")
        # level is now a top-level field
        assert record["level"] == "error"
        assert record["message"] == "Error!"

    def test_builds_record_with_area(self):
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
        )
        record = client._build_record(message="Hello", area="auth")
        assert record["area"] == "auth"

    def test_builds_record_with_optional_fields(self):
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
            environment="production",
            version="1.2.3",
        )
        record = client._build_record(message="Hello")
        assert record["environment"] == "production"
        assert record["version"] == "1.2.3"

    def test_builds_record_with_custom_fields(self):
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
        )
        record = client._build_record(
            message="Request processed",
            fields={"user_id": "123", "duration_ms": 45}
        )
        assert record["fields"]["user_id"] == "123"
        assert record["fields"]["duration_ms"] == 45

    def test_builds_record_with_extra_kwargs(self):
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
        )
        record = client._build_record(
            message="Hello",
            custom_key="custom_value"
        )
        assert record["fields"]["custom_key"] == "custom_value"

    def test_get_endpoint(self):
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
        )
        assert client._get_endpoint() == "http://localhost:8080/v1/logs"

    def test_get_endpoint_strips_trailing_slash(self):
        client = DevlogsClient(
            collector_url="http://localhost:8080/",
            application="test-app",
            component="api",
        )
        assert client._get_endpoint() == "http://localhost:8080/v1/logs"

    def test_get_headers_without_auth(self):
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
        )
        headers = client._get_headers()
        assert headers["Content-Type"] == "application/json"
        assert "Authorization" not in headers

    def test_get_headers_with_auth(self):
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
            auth_token="my-secret-token",
        )
        headers = client._get_headers()
        assert headers["Authorization"] == "Bearer my-secret-token"

    def test_get_headers_with_token_in_url(self):
        """Collector URL: token in username position extracts Bearer auth."""
        client = DevlogsClient(
            collector_url="http://url-token@localhost:8080",
            application="test-app",
            component="api",
        )
        headers = client._get_headers()
        assert headers["Authorization"] == "Bearer url-token"

    def test_auth_token_param_overrides_url_token(self):
        client = DevlogsClient(
            collector_url="http://url-token@localhost:8080",
            application="test-app",
            component="api",
            auth_token="param-token",
        )
        headers = client._get_headers()
        assert headers["Authorization"] == "Bearer param-token"

    def test_get_endpoint_strips_userinfo_for_collector_url(self):
        """Collector URL: userinfo is stripped from endpoint."""
        client = DevlogsClient(
            collector_url="http://mytoken@localhost:8080",
            application="test-app",
            component="api",
        )
        assert client._get_endpoint() == "http://localhost:8080/v1/logs"

    def test_opensearch_url_keeps_credentials(self):
        """OpenSearch URL: credentials remain in URL, no Bearer token."""
        client = DevlogsClient(
            collector_url="https://admin:password@opensearch.example.com:9200",
            application="test-app",
            component="api",
        )
        headers = client._get_headers()
        assert "Authorization" not in headers
        assert client._get_endpoint() == "https://admin:password@opensearch.example.com:9200/v1/logs"

    def test_emit_sends_single_record(self):
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
        )

        with patch("devlogs.devlogs_client.urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.status = 202
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client.emit(message="Hello", level="info")

        assert result is True
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        body = json.loads(request.data.decode("utf-8"))
        # Single record should not have "records" wrapper
        assert "records" not in body
        assert body["application"] == "test-app"

    def test_emit_batch_sends_wrapped_records(self):
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
        )

        with patch("devlogs.devlogs_client.urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.status = 202
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client.emit_batch([
                {"message": "Event 1"},
                {"message": "Event 2"},
            ])

        assert result is True
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        body = json.loads(request.data.decode("utf-8"))
        assert "records" in body
        assert len(body["records"]) == 2

    def test_emit_returns_false_on_error(self):
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
        )

        import urllib.error
        with patch("devlogs.devlogs_client.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                "http://localhost:8080/v1/logs",
                400,
                "Bad Request",
                {},
                None
            )

            result = client.emit(message="Hello")

        assert result is False

    def test_emit_returns_false_on_connection_error(self):
        client = DevlogsClient(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
        )

        import urllib.error
        with patch("devlogs.devlogs_client.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

            result = client.emit(message="Hello")

        assert result is False


class TestCreateClient:
    """Tests for the create_client factory function."""

    def test_creates_client_with_required_args(self):
        client = create_client(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
        )
        assert isinstance(client, DevlogsClient)
        assert client.collector_url == "http://localhost:8080"
        assert client.application == "test-app"
        assert client.component == "api"

    def test_creates_client_with_optional_args(self):
        client = create_client(
            collector_url="http://localhost:8080",
            application="test-app",
            component="api",
            environment="production",
            version="1.0.0",
            auth_token="secret",
        )
        assert client.environment == "production"
        assert client.version == "1.0.0"
        assert client.auth_token == "secret"


class TestEmitLog:
    """Tests for the emit_log convenience function."""

    def test_emits_single_log(self):
        with patch("devlogs.devlogs_client.urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.status = 202
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = emit_log(
                collector_url="http://localhost:8080",
                application="test-app",
                component="api",
                message="Hello world",
            )

        assert result is True
