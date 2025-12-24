# OpenSearch client factory and retry logic - using stdlib urllib for fast imports

import json
import urllib.request
import urllib.error
from base64 import b64encode

from ..config import load_config


class OpenSearchError(Exception):
	"""Base exception for OpenSearch errors with user-friendly messages."""
	pass


class ConnectionFailedError(OpenSearchError):
	"""Raised when OpenSearch is not reachable."""
	pass


class IndexNotFoundError(OpenSearchError):
	"""Raised when the specified index does not exist."""
	pass


class AuthenticationError(OpenSearchError):
	"""Raised when authentication fails."""
	pass


class LightweightOpenSearchClient:
	"""Minimal OpenSearch client using stdlib urllib for fast imports."""

	def __init__(self, host, port, user, password, timeout=5):
		self.base_url = f"http://{host}:{port}"
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
				return json.loads(resp.read().decode('utf-8'))
		except urllib.error.HTTPError as e:
			if e.code == 401:
				raise AuthenticationError(f"Authentication failed (HTTP 401)")
			if e.code == 404:
				return None
			raise
		except urllib.error.URLError as e:
			raise ConnectionFailedError(f"Cannot connect: {e.reason}")

	def info(self):
		"""Get cluster info (used for connection check)."""
		return self._request("GET", "/")

	def search(self, index, body):
		"""Search an index."""
		return self._request("POST", f"/{index}/_search", body)

	def index(self, index, body, routing=None):
		"""Index a document."""
		path = f"/{index}/_doc"
		if routing:
			path += f"?routing={routing}"
		return self._request("POST", path, body)


class _IndicesClient:
	"""Minimal indices operations."""

	def __init__(self, client):
		self._client = client

	def exists(self, index):
		"""Check if index exists."""
		try:
			result = self._client._request("HEAD", f"/{index}")
			return True
		except urllib.error.HTTPError as e:
			if e.code == 404:
				return False
			raise
		except:
			# HEAD request succeeded
			return True

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

	def refresh(self, index):
		"""Refresh an index to make recent changes searchable."""
		return self._client._request("POST", f"/{index}/_refresh")


def get_opensearch_client():
	cfg = load_config()
	return LightweightOpenSearchClient(
		host=cfg.opensearch_host,
		port=cfg.opensearch_port,
		user=cfg.opensearch_user,
		password=cfg.opensearch_pass,
		timeout=cfg.opensearch_timeout,
	)


def check_connection(client):
	"""Check if OpenSearch is reachable. Raises ConnectionFailedError if not."""
	cfg = load_config()
	try:
		client.info()
	except ConnectionFailedError:
		raise ConnectionFailedError(
			f"Cannot connect to OpenSearch at {cfg.opensearch_host}:{cfg.opensearch_port}\n"
			f"Make sure OpenSearch is running and accessible."
		)
	except AuthenticationError:
		raise AuthenticationError(
			f"Authentication failed for OpenSearch at {cfg.opensearch_host}:{cfg.opensearch_port}\n"
			f"Check OPENSEARCH_USER and OPENSEARCH_PASS in your .env file."
		)


def check_index(client, index_name):
	"""Check if an index exists. Raises IndexNotFoundError if not."""
	if not client.indices.exists(index=index_name):
		raise IndexNotFoundError(
			f"Index '{index_name}' does not exist.\n"
			f"Run 'devlogs init' to create it."
		)
