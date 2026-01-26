# OpenSearch client factory and retry logic - using stdlib urllib for fast imports

import json
import socket
import urllib.request
import urllib.error
from base64 import b64encode

from ..config import load_config, URLParseError


class OpenSearchError(Exception):
	"""Base exception for OpenSearch errors with user-friendly messages."""
	pass


class ConnectionFailedError(OpenSearchError):
	"""Raised when OpenSearch is not reachable (generic connection failure)."""
	pass


class DNSResolutionError(ConnectionFailedError):
	"""Raised when the hostname cannot be resolved."""
	pass


class ConnectionRefusedError(ConnectionFailedError):
	"""Raised when the connection is actively refused."""
	pass


class ConnectionTimeoutError(ConnectionFailedError):
	"""Raised when the connection times out."""
	pass


class IndexNotFoundError(OpenSearchError):
	"""Raised when the specified index does not exist."""
	pass


class AuthenticationError(OpenSearchError):
	"""Raised when authentication fails."""
	pass


class QueryError(OpenSearchError):
	"""Raised when a query is malformed or invalid."""
	pass


class DevlogsDisabledError(OpenSearchError):
	"""Raised when devlogs is disabled due to missing configuration."""
	pass


def _raise_connection_error(url_error: urllib.error.URLError, url: str):
	"""Raise a specific connection error based on the URLError reason."""
	reason = url_error.reason

	# DNS resolution failure (socket.gaierror)
	if isinstance(reason, socket.gaierror):
		# Extract hostname from URL for better error message
		try:
			from urllib.parse import urlparse
			host = urlparse(url).hostname or url
		except Exception:
			host = url
		raise DNSResolutionError(f"Cannot resolve hostname '{host}': {reason.strerror}")

	# Connection refused (check errno for ECONNREFUSED on Linux/Windows)
	if isinstance(reason, OSError) and reason.errno in (111, 10061):
		raise ConnectionRefusedError(f"Connection refused: {reason}")

	# Timeout
	if isinstance(reason, socket.timeout) or isinstance(reason, TimeoutError):
		raise ConnectionTimeoutError(f"Connection timed out: {reason}")

	# Generic connection failure
	raise ConnectionFailedError(f"Cannot connect: {reason}")


class LightweightOpenSearchClient:
	"""Minimal OpenSearch client using stdlib urllib for fast imports."""

	def __init__(self, host, port, user, password, timeout=5, scheme="http"):
		self.base_url = f"{scheme}://{host}:{port}"
		self.timeout = timeout
		# Pre-compute auth header
		credentials = b64encode(f"{user}:{password}".encode()).decode('ascii')
		self.headers = {
			"Authorization": f"Basic {credentials}",
			"Content-Type": "application/json",
		}
		self.indices = _IndicesClient(self)

	def _request(self, method, path, body=None):
		"""Make HTTP request to OpenSearch."""
		url = f"{self.base_url}{path}"
		data = json.dumps(body).encode('utf-8') if body else None
		req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
		try:
			with urllib.request.urlopen(req, timeout=self.timeout) as resp:
				raw = resp.read().decode('utf-8')
				if not raw:
					return {}
				return json.loads(raw)
		except urllib.error.HTTPError as e:
			if e.code == 401:
				raise AuthenticationError(f"Authentication failed (HTTP 401)")
			if e.code == 404:
				return None
			if e.code == 400:
				# Try to extract error details from response body
				try:
					error_body = e.read().decode('utf-8')
					error_json = json.loads(error_body)
					reason = error_json.get("error", {}).get("reason", "Bad Request")
					root_cause = error_json.get("error", {}).get("root_cause", [])
					if root_cause:
						reason = root_cause[0].get("reason", reason)
					raise QueryError(f"Query error: {reason}")
				except (json.JSONDecodeError, KeyError):
					raise QueryError(f"Query error: Bad Request")
			raise
		except urllib.error.URLError as e:
			_raise_connection_error(e, url)

	def info(self):
		"""Get cluster info (used for connection check)."""
		return self._request("GET", "/")

	def search(self, index, body, scroll=None):
		"""Search an index."""
		path = f"/{index}/_search"
		if scroll:
			path += f"?scroll={scroll}"
		return self._request("POST", path, body)

	def index(self, index, body, routing=None, id=None, doc_id=None, refresh=None):
		"""Index a document."""
		doc_id = doc_id or id
		path = f"/{index}/_doc"
		method = "POST"
		if doc_id:
			path += f"/{doc_id}"
			method = "PUT"
		params = []
		if routing:
			params.append(f"routing={routing}")
		if refresh is not None:
			params.append(f"refresh={'true' if refresh else 'false'}")
		if params:
			path += "?" + "&".join(params)
		return self._request(method, path, body)

	def delete_by_query(self, index, body, routing=None, refresh=None, conflicts=None, slices=None):
		"""Delete documents matching a query."""
		path = f"/{index}/_delete_by_query"
		params = []
		if routing:
			params.append(f"routing={routing}")
		if refresh is not None:
			params.append(f"refresh={'true' if refresh else 'false'}")
		if conflicts:
			params.append(f"conflicts={conflicts}")
		if slices:
			params.append(f"slices={slices}")
		if params:
			path += "?" + "&".join(params)
		return self._request("POST", path, body)

	def count(self, index, body=None):
		"""Count documents matching an optional query."""
		path = f"/{index}/_count"
		if body:
			return self._request("POST", path, body)
		return self._request("GET", path)

	def bulk(self, body, refresh=None):
		"""Bulk index/delete/update documents.

		Args:
			body: List of action/document pairs in NDJSON format
			refresh: Whether to refresh after bulk operation
		"""
		path = "/_bulk"
		params = []
		if refresh is not None:
			params.append(f"refresh={'true' if refresh else 'false'}")
		if params:
			path += "?" + "&".join(params)
		# Bulk API uses NDJSON format, not JSON array
		if isinstance(body, list):
			ndjson = "\n".join(json.dumps(item) for item in body) + "\n"
		else:
			ndjson = body
		url = f"{self.base_url}{path}"
		data = ndjson.encode('utf-8') if isinstance(ndjson, str) else ndjson
		headers = dict(self.headers)
		headers["Content-Type"] = "application/x-ndjson"
		req = urllib.request.Request(url, data=data, headers=headers, method="POST")
		try:
			with urllib.request.urlopen(req, timeout=self.timeout) as resp:
				raw = resp.read().decode('utf-8')
				if not raw:
					return {}
				return json.loads(raw)
		except urllib.error.HTTPError as e:
			if e.code == 401:
				raise AuthenticationError(f"Authentication failed (HTTP 401)")
			raise
		except urllib.error.URLError as e:
			_raise_connection_error(e, url)


class _IndicesClient:
	"""Minimal indices operations."""

	def __init__(self, client):
		self._client = client

	def exists(self, index):
		"""Check if index exists."""
		result = self._client._request("HEAD", f"/{index}")
		return result is not None

	def create(self, index, body=None):
		"""Create an index."""
		return self._client._request("PUT", f"/{index}", body)

	def delete(self, index):
		"""Delete an index."""
		return self._client._request("DELETE", f"/{index}")

	def put_index_template(self, name, body):
		"""Create or update an index template."""
		return self._client._request("PUT", f"/_index_template/{name}", body)

	def put_template(self, name, body):
		"""Create or update a legacy index template."""
		return self._client._request("PUT", f"/_template/{name}", body)

	def delete_template(self, name):
		"""Delete a legacy index template."""
		try:
			return self._client._request("DELETE", f"/_template/{name}")
		except urllib.error.HTTPError as e:
			if e.code == 404:
				return None
			raise

	def delete_index_template(self, name):
		"""Delete a composable index template."""
		try:
			return self._client._request("DELETE", f"/_index_template/{name}")
		except urllib.error.HTTPError as e:
			if e.code == 404:
				return None
			raise

	def refresh(self, index):
		"""Refresh an index to make recent changes searchable."""
		return self._client._request("POST", f"/{index}/_refresh")

	def get_mapping(self, index):
		"""Get index mapping."""
		return self._client._request("GET", f"/{index}/_mapping")

	def reindex(self, body):
		"""Reindex documents from one index to another."""
		return self._client._request("POST", "/_reindex", body)


def get_opensearch_client():
	cfg = load_config()
	if not getattr(cfg, "enabled", True):
		raise DevlogsDisabledError(
			"Devlogs is disabled because no DEVLOGS_* settings were found. "
			"Set at least one devlogs setting (e.g., DEVLOGS_OPENSEARCH_HOST) to enable it."
		)
	return LightweightOpenSearchClient(
		host=cfg.opensearch_host,
		port=cfg.opensearch_port,
		user=cfg.opensearch_user,
		password=cfg.opensearch_pass,
		timeout=cfg.opensearch_timeout,
		scheme=getattr(cfg, "opensearch_scheme", "http"),
	)


def check_connection(client):
	"""Check if OpenSearch is reachable. Raises specific error for each failure type."""
	cfg = load_config()
	try:
		client.info()
	except DNSResolutionError:
		raise DNSResolutionError(
			f"Cannot resolve hostname '{cfg.opensearch_host}'\n"
			f"Check that DEVLOGS_OPENSEARCH_HOST is spelled correctly."
		)
	except ConnectionRefusedError:
		raise ConnectionRefusedError(
			f"Connection refused by {cfg.opensearch_host}:{cfg.opensearch_port}\n"
			f"Make sure OpenSearch is running on this host and port."
		)
	except ConnectionTimeoutError:
		raise ConnectionTimeoutError(
			f"Connection timed out to {cfg.opensearch_host}:{cfg.opensearch_port}\n"
			f"Check network connectivity and firewall settings."
		)
	except ConnectionFailedError as e:
		raise ConnectionFailedError(
			f"Cannot connect to OpenSearch at {cfg.opensearch_host}:{cfg.opensearch_port}\n"
			f"Error: {e}"
		)
	except AuthenticationError:
		raise AuthenticationError(
			f"Authentication failed for OpenSearch at {cfg.opensearch_host}:{cfg.opensearch_port}\n"
			f"Check DEVLOGS_OPENSEARCH_USER and DEVLOGS_OPENSEARCH_PASS in your .env file."
		)


def check_index(client, index_name):
	"""Check if an index exists. Raises IndexNotFoundError if not."""
	if not client.indices.exists(index=index_name):
		raise IndexNotFoundError(
			f"Index '{index_name}' does not exist.\n"
			f"Run 'devlogs init' to create it."
		)
