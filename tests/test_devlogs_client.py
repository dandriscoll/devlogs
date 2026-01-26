# Tests for the Devlogs client library

import json
import pytest
from unittest.mock import Mock, patch

from devlogs.devlogs_client import DevlogsClient, create_client, emit_log


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
