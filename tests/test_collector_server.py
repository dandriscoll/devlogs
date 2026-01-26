# Tests for the collector HTTP server

import json
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

from fastapi.testclient import TestClient

from devlogs.collector.server import app, get_client_ip
from devlogs import config


@pytest.fixture
def client():
    """Create a test client for the collector app."""
    return TestClient(app)


@pytest.fixture
def reset_config(monkeypatch):
    """Reset config state before each test."""
    monkeypatch.setattr(config, "_dotenv_loaded", True)
    # Clear relevant env vars
    for key in (
        "DEVLOGS_URL",
        "DEVLOGS_FORWARD_URL",
        "DEVLOGS_OPENSEARCH_HOST",
        "DEVLOGS_OPENSEARCH_URL",
        "DEVLOGS_INDEX",
    ):
        monkeypatch.delenv(key, raising=False)


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_mode(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["mode"] == "ingest"

    def test_health_forward_mode(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "http://upstream:8080")
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "forward"


class TestIngestEndpoint:
    """Tests for the POST /v1/logs endpoint."""

    def test_rejects_non_json_content_type(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        response = client.post(
            "/v1/logs",
            content="some text",
            headers={"Content-Type": "text/plain"}
        )
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "VALIDATION_FAILED"
        assert "Content-Type" in data["message"]

    def test_rejects_invalid_json(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        response = client.post(
            "/v1/logs",
            content="not json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "VALIDATION_FAILED"

    def test_rejects_missing_required_field(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        response = client.post(
            "/v1/logs",
            json={"application": "test"}  # Missing component and timestamp
        )
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "VALIDATION_FAILED"

    def test_accepts_valid_single_record(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "test-index")

        # Mock the OpenSearch client
        mock_client = Mock()
        mock_client.index = Mock(return_value={})

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post(
                "/v1/logs",
                json={
                    "application": "test-app",
                    "component": "api",
                    "timestamp": "2024-01-15T10:30:00Z"
                }
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["ingested"] == 1

        # Verify OpenSearch was called
        mock_client.index.assert_called_once()
        call_args = mock_client.index.call_args
        assert call_args.kwargs["index"] == "test-index"
        body = call_args.kwargs["body"]
        assert body["application"] == "test-app"
        assert body["component"] == "api"
        # Default auth mode is allow_anonymous with no token → anonymous identity
        assert body["identity"]["mode"] == "anonymous"
        assert "collected_ts" in body
        assert "client_ip" in body

    def test_accepts_valid_batch(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "test-index")

        mock_client = Mock()
        mock_client.bulk = Mock(return_value={"errors": False, "items": []})

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post(
                "/v1/logs",
                json={
                    "records": [
                        {"application": "test-app", "component": "api", "timestamp": "2024-01-15T10:30:00Z"},
                        {"application": "test-app", "component": "worker", "timestamp": "2024-01-15T10:30:01Z"},
                    ]
                }
            )

        assert response.status_code == 202
        data = response.json()
        assert data["ingested"] == 2

        # Verify bulk was used
        mock_client.bulk.assert_called_once()

    def test_validates_batch_record_errors(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        response = client.post(
            "/v1/logs",
            json={
                "records": [
                    {"application": "test-app", "component": "api", "timestamp": "2024-01-15T10:30:00Z"},
                    {"application": "test-app"},  # Missing required fields
                ]
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert "Record 1" in data["message"]  # Index in error message

    def test_captures_client_ip(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "test-index")

        mock_client = Mock()
        mock_client.index = Mock(return_value={})

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post(
                "/v1/logs",
                json={
                    "application": "test-app",
                    "component": "api",
                    "timestamp": "2024-01-15T10:30:00Z"
                }
            )

        assert response.status_code == 202
        body = mock_client.index.call_args.kwargs["body"]
        # TestClient uses testclient as host
        assert body["client_ip"] is not None

    def test_captures_forwarded_ip(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "test-index")

        mock_client = Mock()
        mock_client.index = Mock(return_value={})

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post(
                "/v1/logs",
                json={
                    "application": "test-app",
                    "component": "api",
                    "timestamp": "2024-01-15T10:30:00Z"
                },
                headers={"X-Forwarded-For": "192.168.1.100, 10.0.0.1"}
            )

        assert response.status_code == 202
        body = mock_client.index.call_args.kwargs["body"]
        assert body["client_ip"] == "192.168.1.100"

    def test_valid_token_with_mapping_sets_verified_identity(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "test-index")
        # Set up a token mapping
        token = "dl1_testky_12345678901234567890123456789012"
        monkeypatch.setenv("DEVLOGS_TOKEN_MAP_KV", f"{token}=service-1,Test Service")

        mock_client = Mock()
        mock_client.index = Mock(return_value={})

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post(
                "/v1/logs",
                json={
                    "application": "test-app",
                    "component": "api",
                    "timestamp": "2024-01-15T10:30:00Z"
                },
                headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 202
        body = mock_client.index.call_args.kwargs["body"]
        assert body["identity"]["mode"] == "verified"
        assert body["identity"]["id"] == "service-1"
        assert body["identity"]["name"] == "Test Service"

    def test_unknown_token_in_anonymous_mode_sets_anonymous_identity(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "test-index")
        # Default auth mode is allow_anonymous

        mock_client = Mock()
        mock_client.index = Mock(return_value={})

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post(
                "/v1/logs",
                json={
                    "application": "test-app",
                    "component": "api",
                    "timestamp": "2024-01-15T10:30:00Z"
                },
                headers={"Authorization": "Bearer unknown-token"}
            )

        assert response.status_code == 202
        body = mock_client.index.call_args.kwargs["body"]
        # Unknown token in allow_anonymous mode → anonymous identity
        assert body["identity"]["mode"] == "anonymous"

    def test_require_token_verified_mode_rejects_unknown_token(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "test-index")
        monkeypatch.setenv("DEVLOGS_AUTH_MODE", "require_token_verified")
        # Valid format but unknown token
        token = "dl1_unknwn_12345678901234567890123456789012"

        mock_client = Mock()
        mock_client.index = Mock(return_value={})

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post(
                "/v1/logs",
                json={
                    "application": "test-app",
                    "component": "api",
                    "timestamp": "2024-01-15T10:30:00Z"
                },
                headers={"Authorization": f"Bearer {token}"}
            )

        assert response.status_code == 400
        data = response.json()
        assert data["subcode"] == "TOKEN_NOT_FOUND"

    def test_require_token_passthrough_mode_preserves_payload_identity(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "test-index")
        monkeypatch.setenv("DEVLOGS_AUTH_MODE", "require_token_passthrough")

        mock_client = Mock()
        mock_client.index = Mock(return_value={})

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post(
                "/v1/logs",
                json={
                    "application": "test-app",
                    "component": "api",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "identity": {"custom_id": "abc", "role": "admin"}
                },
                headers={"Authorization": "Bearer any-token"}
            )

        assert response.status_code == 202
        body = mock_client.index.call_args.kwargs["body"]
        assert body["identity"]["mode"] == "passthrough"
        assert body["identity"]["custom_id"] == "abc"
        assert body["identity"]["role"] == "admin"

    def test_devlogs1_auth_header(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "test-index")
        token = "dl1_testky_12345678901234567890123456789012"
        monkeypatch.setenv("DEVLOGS_TOKEN_MAP_KV", f"{token}=service-1")

        mock_client = Mock()
        mock_client.index = Mock(return_value={})

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post(
                "/v1/logs",
                json={
                    "application": "test-app",
                    "component": "api",
                    "timestamp": "2024-01-15T10:30:00Z"
                },
                headers={"Authorization": f"Devlogs1 {token}"}
            )

        assert response.status_code == 202
        body = mock_client.index.call_args.kwargs["body"]
        assert body["identity"]["mode"] == "verified"

    def test_x_devlogs_token_header(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "test-index")
        token = "dl1_testky_12345678901234567890123456789012"
        monkeypatch.setenv("DEVLOGS_TOKEN_MAP_KV", f"{token}=service-1")

        mock_client = Mock()
        mock_client.index = Mock(return_value={})

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post(
                "/v1/logs",
                json={
                    "application": "test-app",
                    "component": "api",
                    "timestamp": "2024-01-15T10:30:00Z"
                },
                headers={"X-Devlogs-Token": token}
            )

        assert response.status_code == 202
        body = mock_client.index.call_args.kwargs["body"]
        assert body["identity"]["mode"] == "verified"

    def test_optional_fields_accepted(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "test-index")

        mock_client = Mock()
        mock_client.index = Mock(return_value={})

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post(
                "/v1/logs",
                json={
                    "application": "test-app",
                    "component": "api",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "environment": "production",
                    "version": "1.2.3",
                }
            )

        assert response.status_code == 202
        body = mock_client.index.call_args.kwargs["body"]
        assert body["environment"] == "production"
        assert body["version"] == "1.2.3"

    def test_nested_fields_passthrough(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "test-index")

        mock_client = Mock()
        mock_client.index = Mock(return_value={})

        custom_fields = {
            "user_id": "123",
            "request": {
                "method": "POST",
                "path": "/api/users",
                "headers": {"Content-Type": "application/json"}
            },
            "metrics": {
                "duration_ms": 45,
                "db_queries": 3
            }
        }

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post(
                "/v1/logs",
                json={
                    "application": "test-app",
                    "component": "api",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "fields": custom_fields,
                }
            )

        assert response.status_code == 202
        body = mock_client.index.call_args.kwargs["body"]
        assert body["fields"] == custom_fields
        assert body["fields"]["request"]["method"] == "POST"
        assert body["fields"]["metrics"]["duration_ms"] == 45


class TestIndexRouting:
    """Tests for per-application index routing."""

    def test_routes_by_application(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "devlogs-default")
        monkeypatch.setenv("DEVLOGS_FORWARD_INDEX_MAP_KV", "app1=devlogs-app1;app2=devlogs-app2")

        mock_client = Mock()
        mock_client.bulk = Mock(return_value={"errors": False, "items": []})

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post(
                "/v1/logs",
                json={
                    "records": [
                        {"application": "app1", "component": "api", "timestamp": "2024-01-15T10:30:00Z"},
                        {"application": "app2", "component": "worker", "timestamp": "2024-01-15T10:30:01Z"},
                        {"application": "app3", "component": "other", "timestamp": "2024-01-15T10:30:02Z"},
                    ]
                }
            )

        assert response.status_code == 202

        # Verify bulk was called with correct indices
        call_args = mock_client.bulk.call_args
        bulk_body = call_args.kwargs["body"]

        # Check that each record has the correct target index
        assert bulk_body[0]["index"]["_index"] == "devlogs-app1"  # app1 → mapped
        assert bulk_body[2]["index"]["_index"] == "devlogs-app2"  # app2 → mapped
        assert bulk_body[4]["index"]["_index"] == "devlogs-default"  # app3 → default

    def test_single_record_routing(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
        monkeypatch.setenv("DEVLOGS_INDEX", "devlogs-default")
        monkeypatch.setenv("DEVLOGS_FORWARD_INDEX_MAP_KV", "my-app=devlogs-myapp")

        mock_client = Mock()
        mock_client.index = Mock(return_value={})

        with patch("devlogs.collector.server.get_opensearch_client", return_value=mock_client):
            response = client.post(
                "/v1/logs",
                json={
                    "application": "my-app",
                    "component": "api",
                    "timestamp": "2024-01-15T10:30:00Z"
                }
            )

        assert response.status_code == 202
        call_args = mock_client.index.call_args
        assert call_args.kwargs["index"] == "devlogs-myapp"


class TestNotConfiguredMode:
    """Tests for when collector is not configured."""

    def test_returns_503_when_not_configured(self, client, reset_config):
        response = client.post(
            "/v1/logs",
            json={
                "application": "test-app",
                "component": "api",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        )
        assert response.status_code == 503
        data = response.json()
        assert data["code"] == "NOT_CONFIGURED"


class TestForwardMode:
    """Tests for forward mode."""

    def test_forwards_to_upstream(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "http://upstream:8080")

        with patch("devlogs.collector.forwarder.urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.status = 202
            mock_response.read.return_value = b'{"status": "accepted"}'
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            response = client.post(
                "/v1/logs",
                json={
                    "application": "test-app",
                    "component": "api",
                    "timestamp": "2024-01-15T10:30:00Z"
                }
            )

        assert response.status_code == 202
        data = response.json()
        assert data["forwarded"] is True

    def test_forwards_auth_header(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "http://upstream:8080")

        with patch("devlogs.collector.forwarder.urllib.request.urlopen") as mock_urlopen:
            mock_response = Mock()
            mock_response.status = 202
            mock_response.read.return_value = b'{}'
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            response = client.post(
                "/v1/logs",
                json={"application": "test", "component": "api", "timestamp": "2024-01-15T10:30:00Z"},
                headers={"Authorization": "Bearer test-token"}
            )

        # Verify auth header was forwarded
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        assert request.get_header("Authorization") == "Bearer test-token"

    def test_handles_upstream_error(self, client, reset_config, monkeypatch):
        monkeypatch.setenv("DEVLOGS_FORWARD_URL", "http://upstream:8080")

        import urllib.error
        with patch("devlogs.collector.forwarder.urllib.request.urlopen") as mock_urlopen:
            mock_error = urllib.error.HTTPError(
                "http://upstream:8080/v1/logs",
                500,
                "Internal Server Error",
                {},
                None
            )
            mock_error.read = Mock(return_value=b"Server error")
            mock_urlopen.side_effect = mock_error

            response = client.post(
                "/v1/logs",
                json={"application": "test", "component": "api", "timestamp": "2024-01-15T10:30:00Z"}
            )

        assert response.status_code == 502
        data = response.json()
        assert data["code"] == "FORWARD_FAILED"
        assert "UPSTREAM_SERVER_ERROR" in data["subcode"]


class TestGetClientIp:
    """Tests for client IP extraction."""

    def test_extracts_forwarded_for(self):
        mock_request = Mock()
        mock_request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
        mock_request.client = Mock(host="127.0.0.1")
        assert get_client_ip(mock_request) == "192.168.1.1"

    def test_extracts_real_ip(self):
        mock_request = Mock()
        mock_request.headers = {"X-Real-IP": "192.168.1.1"}
        mock_request.client = Mock(host="127.0.0.1")
        assert get_client_ip(mock_request) == "192.168.1.1"

    def test_falls_back_to_client(self):
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.client = Mock(host="192.168.1.1")
        assert get_client_ip(mock_request) == "192.168.1.1"

    def test_returns_unknown_without_client(self):
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.client = None
        assert get_client_ip(mock_request) == "unknown"
