"""Tests for the OpenSearch client module."""

import json
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch, Mock

import pytest

from devlogs.opensearch.client import (
    LightweightOpenSearchClient,
    OpenSearchError,
    ConnectionFailedError,
    IndexNotFoundError,
    AuthenticationError,
    QueryError,
    DevlogsDisabledError,
    get_opensearch_client,
    check_connection,
    check_index,
)


class TestLightweightOpenSearchClient:
    """Tests for LightweightOpenSearchClient."""

    def test_init_sets_base_url_and_headers(self):
        """Test client initialization sets base URL and auth headers."""
        client = LightweightOpenSearchClient(
            host="localhost",
            port=9200,
            user="admin",
            password="secret",
            timeout=10,
        )
        assert client.base_url == "http://localhost:9200"
        assert client.timeout == 10
        assert "Authorization" in client.headers
        assert client.headers["Authorization"].startswith("Basic ")
        assert client.headers["Content-Type"] == "application/json"

    def test_indices_client_attached(self):
        """Test that _IndicesClient is attached to the client."""
        client = LightweightOpenSearchClient("localhost", 9200, "admin", "pass")
        assert hasattr(client, "indices")
        assert client.indices._client is client


class TestClientRequest:
    """Tests for _request method error handling."""

    @pytest.fixture
    def client(self):
        return LightweightOpenSearchClient("localhost", 9200, "admin", "pass")

    def test_request_connection_error_raises_connection_failed(self, client):
        """Test URLError raises ConnectionFailedError."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
            with pytest.raises(ConnectionFailedError) as exc_info:
                client._request("GET", "/")
            assert "Cannot connect" in str(exc_info.value)

    def test_request_401_raises_authentication_error(self, client):
        """Test HTTP 401 raises AuthenticationError."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="http://localhost:9200/",
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=None,
            )
            with pytest.raises(AuthenticationError) as exc_info:
                client._request("GET", "/")
            assert "401" in str(exc_info.value)

    def test_request_404_returns_none(self, client):
        """Test HTTP 404 returns None (not an error)."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="http://localhost:9200/test",
                code=404,
                msg="Not Found",
                hdrs={},
                fp=None,
            )
            result = client._request("GET", "/test")
            assert result is None

    def test_request_400_raises_query_error(self, client):
        """Test HTTP 400 raises QueryError."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            error_body = json.dumps({
                "error": {
                    "reason": "Parse error",
                    "root_cause": [{"reason": "Invalid query syntax"}]
                }
            }).encode()
            mock_error = urllib.error.HTTPError(
                url="http://localhost:9200/_search",
                code=400,
                msg="Bad Request",
                hdrs={},
                fp=Mock(read=lambda: error_body),
            )
            mock_error.read = lambda: error_body
            mock_urlopen.side_effect = mock_error
            with pytest.raises(QueryError) as exc_info:
                client._request("POST", "/_search", {"query": {}})
            assert "Invalid query syntax" in str(exc_info.value)

    def test_request_400_with_malformed_body_raises_query_error(self, client):
        """Test HTTP 400 with non-JSON body still raises QueryError."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_error = urllib.error.HTTPError(
                url="http://localhost:9200/_search",
                code=400,
                msg="Bad Request",
                hdrs={},
                fp=Mock(read=lambda: b"not json"),
            )
            mock_error.read = lambda: b"not json"
            mock_urlopen.side_effect = mock_error
            with pytest.raises(QueryError) as exc_info:
                client._request("POST", "/_search", {"query": {}})
            assert "Bad Request" in str(exc_info.value)

    def test_request_success_returns_json(self, client):
        """Test successful request returns parsed JSON."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b'{"name": "opensearch-node"}'
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client._request("GET", "/")
            assert result == {"name": "opensearch-node"}

    def test_request_empty_response_returns_empty_dict(self, client):
        """Test empty response returns empty dict."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b""
            mock_response.__enter__ = lambda s: s
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client._request("GET", "/")
            assert result == {}


class TestClientMethods:
    """Tests for client methods."""

    @pytest.fixture
    def client(self):
        return LightweightOpenSearchClient("localhost", 9200, "admin", "pass")

    def test_info_calls_get_root(self, client):
        """Test info() calls GET /."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {"name": "node"}
            result = client.info()
            mock_request.assert_called_once_with("GET", "/")
            assert result == {"name": "node"}

    def test_search_without_scroll(self, client):
        """Test search without scroll parameter."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {"hits": {"hits": []}}
            client.search("my-index", {"query": {"match_all": {}}})
            mock_request.assert_called_once_with(
                "POST", "/my-index/_search", {"query": {"match_all": {}}}
            )

    def test_search_with_scroll(self, client):
        """Test search with scroll parameter."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {"hits": {"hits": []}}
            client.search("my-index", {"query": {"match_all": {}}}, scroll="1m")
            mock_request.assert_called_once_with(
                "POST", "/my-index/_search?scroll=1m", {"query": {"match_all": {}}}
            )

    def test_index_without_doc_id_uses_post(self, client):
        """Test index without doc_id uses POST."""
        with patch.object(client, "_request") as mock_request:
            client.index("my-index", {"field": "value"})
            mock_request.assert_called_once_with(
                "POST", "/my-index/_doc", {"field": "value"}
            )

    def test_index_with_doc_id_uses_put(self, client):
        """Test index with doc_id uses PUT."""
        with patch.object(client, "_request") as mock_request:
            client.index("my-index", {"field": "value"}, doc_id="123")
            mock_request.assert_called_once_with(
                "PUT", "/my-index/_doc/123", {"field": "value"}
            )

    def test_index_with_routing_and_refresh(self, client):
        """Test index with routing and refresh params."""
        with patch.object(client, "_request") as mock_request:
            client.index("my-index", {"field": "value"}, routing="r1", refresh=True)
            mock_request.assert_called_once_with(
                "POST", "/my-index/_doc?routing=r1&refresh=true", {"field": "value"}
            )

    def test_delete_by_query_basic(self, client):
        """Test delete_by_query basic call."""
        with patch.object(client, "_request") as mock_request:
            client.delete_by_query("my-index", {"query": {"match_all": {}}})
            mock_request.assert_called_once_with(
                "POST", "/my-index/_delete_by_query", {"query": {"match_all": {}}}
            )

    def test_delete_by_query_with_params(self, client):
        """Test delete_by_query with all params."""
        with patch.object(client, "_request") as mock_request:
            client.delete_by_query(
                "my-index",
                {"query": {"match_all": {}}},
                routing="r1",
                refresh=True,
                conflicts="proceed",
                slices="auto",
            )
            mock_request.assert_called_once_with(
                "POST",
                "/my-index/_delete_by_query?routing=r1&refresh=true&conflicts=proceed&slices=auto",
                {"query": {"match_all": {}}},
            )


class TestIndicesClient:
    """Tests for _IndicesClient."""

    @pytest.fixture
    def client(self):
        return LightweightOpenSearchClient("localhost", 9200, "admin", "pass")

    def test_exists_returns_true_when_index_exists(self, client):
        """Test exists returns True when index exists."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {}  # HEAD returns empty dict on success
            result = client.indices.exists("my-index")
            mock_request.assert_called_once_with("HEAD", "/my-index")
            assert result is True

    def test_exists_returns_false_when_index_missing(self, client):
        """Test exists returns False when index doesn't exist."""
        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = None  # 404 returns None
            result = client.indices.exists("missing-index")
            assert result is False

    def test_create_index(self, client):
        """Test create index."""
        with patch.object(client, "_request") as mock_request:
            client.indices.create("new-index", {"settings": {}})
            mock_request.assert_called_once_with(
                "PUT", "/new-index", {"settings": {}}
            )

    def test_delete_index(self, client):
        """Test delete index."""
        with patch.object(client, "_request") as mock_request:
            client.indices.delete("old-index")
            mock_request.assert_called_once_with("DELETE", "/old-index")

    def test_put_index_template(self, client):
        """Test put index template."""
        with patch.object(client, "_request") as mock_request:
            client.indices.put_index_template("my-template", {"index_patterns": ["*"]})
            mock_request.assert_called_once_with(
                "PUT", "/_index_template/my-template", {"index_patterns": ["*"]}
            )

    def test_put_template_legacy(self, client):
        """Test put legacy template."""
        with patch.object(client, "_request") as mock_request:
            client.indices.put_template("legacy-template", {"index_patterns": ["*"]})
            mock_request.assert_called_once_with(
                "PUT", "/_template/legacy-template", {"index_patterns": ["*"]}
            )

    def test_delete_template_success(self, client):
        """Test delete legacy template."""
        with patch.object(client, "_request") as mock_request:
            client.indices.delete_template("old-template")
            mock_request.assert_called_once_with("DELETE", "/_template/old-template")

    def test_delete_template_404_returns_none(self, client):
        """Test delete template returns None for 404."""
        with patch.object(client, "_request") as mock_request:
            mock_request.side_effect = urllib.error.HTTPError(
                url="", code=404, msg="Not Found", hdrs={}, fp=None
            )
            result = client.indices.delete_template("missing-template")
            assert result is None

    def test_refresh_index(self, client):
        """Test refresh index."""
        with patch.object(client, "_request") as mock_request:
            client.indices.refresh("my-index")
            mock_request.assert_called_once_with("POST", "/my-index/_refresh")


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_get_opensearch_client_creates_client(self):
        """Test get_opensearch_client creates a client from config."""
        with patch("devlogs.opensearch.client.load_config") as mock_config:
            mock_config.return_value = MagicMock(
                opensearch_host="myhost",
                opensearch_port=9201,
                opensearch_user="user",
                opensearch_pass="pass",
                opensearch_timeout=15,
                enabled=True,
            )
            client = get_opensearch_client()
            assert client.base_url == "http://myhost:9201"
            assert client.timeout == 15

    def test_get_opensearch_client_disabled(self):
        """Test get_opensearch_client raises when devlogs is disabled."""
        with patch("devlogs.opensearch.client.load_config") as mock_config:
            mock_config.return_value = MagicMock(enabled=False)
            with pytest.raises(DevlogsDisabledError):
                get_opensearch_client()

    def test_check_connection_success(self):
        """Test check_connection succeeds when client connects."""
        mock_client = MagicMock()
        mock_client.info.return_value = {"name": "node"}
        # Should not raise
        with patch("devlogs.opensearch.client.load_config"):
            check_connection(mock_client)

    def test_check_connection_failure_raises(self):
        """Test check_connection raises ConnectionFailedError."""
        mock_client = MagicMock()
        mock_client.info.side_effect = ConnectionFailedError("Cannot connect")
        with patch("devlogs.opensearch.client.load_config") as mock_config:
            mock_config.return_value = MagicMock(
                opensearch_host="badhost",
                opensearch_port=9200,
            )
            with pytest.raises(ConnectionFailedError) as exc_info:
                check_connection(mock_client)
            assert "badhost" in str(exc_info.value)

    def test_check_connection_auth_failure_raises(self):
        """Test check_connection raises AuthenticationError."""
        mock_client = MagicMock()
        mock_client.info.side_effect = AuthenticationError("Auth failed")
        with patch("devlogs.opensearch.client.load_config") as mock_config:
            mock_config.return_value = MagicMock(
                opensearch_host="host",
                opensearch_port=9200,
            )
            with pytest.raises(AuthenticationError) as exc_info:
                check_connection(mock_client)
            assert "Authentication failed" in str(exc_info.value)

    def test_check_index_success(self):
        """Test check_index succeeds when index exists."""
        mock_client = MagicMock()
        mock_client.indices.exists.return_value = True
        # Should not raise
        check_index(mock_client, "my-index")

    def test_check_index_missing_raises(self):
        """Test check_index raises IndexNotFoundError."""
        mock_client = MagicMock()
        mock_client.indices.exists.return_value = False
        with pytest.raises(IndexNotFoundError) as exc_info:
            check_index(mock_client, "missing-index")
        assert "missing-index" in str(exc_info.value)
        assert "devlogs init" in str(exc_info.value)


class TestExceptionHierarchy:
    """Tests for exception classes."""

    def test_all_exceptions_inherit_from_opensearch_error(self):
        """Test all custom exceptions inherit from OpenSearchError."""
        assert issubclass(ConnectionFailedError, OpenSearchError)
        assert issubclass(IndexNotFoundError, OpenSearchError)
        assert issubclass(AuthenticationError, OpenSearchError)
        assert issubclass(QueryError, OpenSearchError)

    def test_exceptions_can_be_caught_as_opensearch_error(self):
        """Test exceptions can be caught with base class."""
        try:
            raise ConnectionFailedError("test")
        except OpenSearchError as e:
            assert "test" in str(e)

        try:
            raise AuthenticationError("auth test")
        except OpenSearchError as e:
            assert "auth test" in str(e)
