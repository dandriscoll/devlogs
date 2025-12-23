# OpenSearch client factory and retry logic

from opensearchpy import OpenSearch
from opensearchpy.exceptions import ConnectionError, NotFoundError, AuthenticationException
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


def get_opensearch_client():
	cfg = load_config()
	return OpenSearch(
		hosts=[{"host": cfg.opensearch_host, "port": cfg.opensearch_port}],
		http_auth=(cfg.opensearch_user, cfg.opensearch_pass),
		use_ssl=False,
		verify_certs=False,
		timeout=5,
		max_retries=1,
	)


def check_connection(client):
	"""Check if OpenSearch is reachable. Raises ConnectionFailedError if not."""
	cfg = load_config()
	try:
		client.info()
	except ConnectionError:
		raise ConnectionFailedError(
			f"Cannot connect to OpenSearch at {cfg.opensearch_host}:{cfg.opensearch_port}\n"
			f"Make sure OpenSearch is running and accessible."
		)
	except AuthenticationException:
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
