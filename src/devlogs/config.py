# Configuration loading for devlogs

import os
import re
import sys
import warnings
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, unquote, parse_qs

# Lazy load dotenv - only when config is first accessed
_dotenv_loaded = False
_custom_dotenv_path = None

# All recognized devlogs configuration keys
_DEVLOGS_CONFIG_KEYS = (
	# Collector URL (where apps send logs)
	"DEVLOGS_URL",
	# Forward mode: if set, collector forwards to this URL instead of ingesting
	"DEVLOGS_FORWARD_URL",
	# Forward mode: per-application index routing (KV format)
	"DEVLOGS_FORWARD_INDEX_MAP_KV",
	# Forward mode: internal logs index
	"DEVLOGS_FORWARD_INTERNAL_INDEX",
	# Admin/OpenSearch connection (for search/tail/UI/CLI and collector ingest)
	"DEVLOGS_OPENSEARCH_HOST",
	"DEVLOGS_OPENSEARCH_PORT",
	"DEVLOGS_OPENSEARCH_USER",
	"DEVLOGS_OPENSEARCH_PASS",
	"DEVLOGS_OPENSEARCH_TIMEOUT",
	"DEVLOGS_OPENSEARCH_URL",
	"DEVLOGS_OPENSEARCH_VERIFY_CERTS",
	"DEVLOGS_OPENSEARCH_CA_CERT",
	"DEVLOGS_INDEX",
	# Retention policy
	"DEVLOGS_RETENTION_DEBUG",
	"DEVLOGS_RETENTION_INFO",
	"DEVLOGS_RETENTION_WARNING",
	# Collector limits (future provisions, default unlimited)
	"DEVLOGS_COLLECTOR_RATE_LIMIT",
	"DEVLOGS_COLLECTOR_MAX_PAYLOAD_SIZE",
	# Collector binding settings
	"DEVLOGS_COLLECTOR_HOST",
	"DEVLOGS_COLLECTOR_PORT",
	"DEVLOGS_COLLECTOR_WORKERS",
	"DEVLOGS_COLLECTOR_LOG_LEVEL",
	# Authentication configuration
	"DEVLOGS_AUTH_MODE",
	"DEVLOGS_TOKEN_MAP_KV",
	# Legacy: Auth token header name (default: Authorization)
	"DEVLOGS_AUTH_HEADER",
)


def _getenv(name, default):
	value = os.getenv(name)
	return value if value else default


def _has_any_devlogs_settings() -> bool:
	for key in _DEVLOGS_CONFIG_KEYS:
		value = os.getenv(key)
		if value:
			return True
	return False


def parse_duration(value: str, unit: str = 'hours') -> int:
	"""Parse a duration string like '6h' or '7d' into numeric value.

	Args:
		value: Duration string (e.g., '6h', '7d', '30') or None
		unit: Default unit to use - 'hours' or 'days'

	Returns:
		Numeric value in the requested unit

	Supports:
		- '6h' or '6H' -> 6 hours
		- '7d' or '7D' -> 7 days
		- '30' -> 30 (in default unit)
	"""
	if not value:
		return 0

	value = value.strip()

	# Match duration pattern: number followed by optional h/d suffix
	match = re.match(r'^(\d+)([hHdD])?$', value)
	if not match:
		raise ValueError(f"Invalid duration format: '{value}'. Expected format: '6h', '7d', or '30'")

	number = int(match.group(1))
	suffix = match.group(2)

	if not suffix:
		# No suffix, return as-is in default unit
		return number

	suffix = suffix.lower()

	if suffix == 'h':
		# Hours requested
		if unit == 'hours':
			return number
		else:  # unit == 'days'
			# Convert hours to days (round up)
			return (number + 23) // 24
	elif suffix == 'd':
		# Days requested
		if unit == 'days':
			return number
		else:  # unit == 'hours'
			# Convert days to hours
			return number * 24

	return number


class URLParseError(ValueError):
	"""Raised when the OpenSearch URL is malformed."""
	pass


@dataclass
class CollectorURLConfig:
	"""Parsed collector URL configuration."""
	url: str  # Base URL (scheme://host:port/path, no credentials)
	token: Optional[str] = None  # Bearer token


@dataclass
class OpenSearchURLConfig:
	"""Parsed OpenSearch URL configuration."""
	scheme: str
	host: str
	port: int
	user: Optional[str] = None
	password: Optional[str] = None
	index: Optional[str] = None
	application: Optional[str] = None  # Optional application filter from second path segment


def parse_url(url: str):
	"""Parse a URL and return a CollectorURLConfig or OpenSearchURLConfig.

	Detection logic:
	- opensearchs:// (TLS) or opensearch:// (non-TLS) → OpenSearch
	- https:// or http:// with both user+pass → legacy OpenSearch (deprecation warning)
	- https:// or http:// with token-only or ?token= → Collector

	Returns: CollectorURLConfig or OpenSearchURLConfig
	Raises: URLParseError if URL is malformed
	"""
	if not url:
		raise URLParseError("Empty URL")

	# Check for opensearch:// or opensearchs:// schemes
	if url.startswith("opensearchs://") or url.startswith("opensearch://"):
		return _parse_opensearch_scheme_url(url)

	parsed = urlparse(url)

	if parsed.scheme not in ("http", "https"):
		raise URLParseError(f"Invalid URL scheme '{parsed.scheme}': expected 'http', 'https', 'opensearch', or 'opensearchs'")

	if not parsed.hostname:
		raise URLParseError(f"Invalid URL '{url}': missing hostname")

	# If both user AND password → legacy OpenSearch format, emit deprecation warning
	if parsed.username and parsed.password:
		warnings.warn(
			f"Using https://user:pass@host URL format for OpenSearch is deprecated. "
			f"Use opensearchs://user:pass@host instead.",
			DeprecationWarning,
			stacklevel=2,
		)
		return _parse_opensearch_url_to_config(url)

	# Otherwise it's a collector URL
	return _parse_collector_url_config(url)


def _parse_opensearch_scheme_url(url: str) -> OpenSearchURLConfig:
	"""Parse opensearchs:// (TLS) or opensearch:// (non-TLS) URL into OpenSearchURLConfig."""
	# Determine the transport scheme
	if url.startswith("opensearchs://"):
		transport_scheme = "https"
		parse_url_str = "https://" + url[len("opensearchs://"):]
	else:
		transport_scheme = "http"
		parse_url_str = "http://" + url[len("opensearch://"):]

	parsed = urlparse(parse_url_str)

	if not parsed.hostname:
		raise URLParseError(f"Invalid URL '{url}': missing hostname")

	host = parsed.hostname
	port = parsed.port or (443 if transport_scheme == "https" else 9200)
	user = unquote(parsed.username) if parsed.username else None
	password = unquote(parsed.password) if parsed.password else None

	# Path segments: first = index, second = application
	path = parsed.path.strip("/")
	parts = path.split("/", 1) if path else []
	index = parts[0] if parts else None
	application = parts[1] if len(parts) > 1 else None

	return OpenSearchURLConfig(
		scheme=transport_scheme,
		host=host,
		port=port,
		user=user,
		password=password,
		index=index or None,
		application=application or None,
	)


def _parse_collector_url_config(url: str) -> CollectorURLConfig:
	"""Parse an http(s) URL as a collector URL, extracting token."""
	parsed = urlparse(url)

	token = None

	# Check for token in userinfo (token-only, no password)
	if parsed.username and not parsed.password:
		token = unquote(parsed.username)
		# Rebuild URL without userinfo
		if parsed.port:
			netloc = f"{parsed.hostname}:{parsed.port}"
		else:
			netloc = parsed.hostname or ""
		from urllib.parse import urlunparse
		clean_url = urlunparse((
			parsed.scheme, netloc, parsed.path,
			parsed.params, parsed.query, parsed.fragment,
		))
	else:
		clean_url = url

	# Check for ?token= query param
	if not token:
		query_params = parse_qs(parsed.query)
		token_values = query_params.get("token")
		if token_values:
			token = token_values[0]
			# Strip token param from the URL
			from urllib.parse import urlencode
			remaining = {k: v[0] for k, v in query_params.items() if k != "token"}
			new_query = urlencode(remaining) if remaining else ""
			reparsed = urlparse(clean_url)
			from urllib.parse import urlunparse
			clean_url = urlunparse((
				reparsed.scheme, reparsed.netloc, reparsed.path,
				reparsed.params, new_query, reparsed.fragment,
			))

	return CollectorURLConfig(url=clean_url, token=token)


def _parse_opensearch_url_to_config(url: str) -> OpenSearchURLConfig:
	"""Parse a standard http(s) URL into OpenSearchURLConfig."""
	result = _parse_opensearch_url(url)
	if result is None:
		raise URLParseError(f"Invalid URL '{url}'")
	scheme, host, port, user, password, index = result
	return OpenSearchURLConfig(
		scheme=scheme, host=host, port=port,
		user=user, password=password, index=index,
	)


def _parse_opensearch_url(url: str):
	"""Parse DEVLOGS_OPENSEARCH_URL into components.

	Supports format: https://user:pass@host:port/index
	Also supports: opensearchs://user:pass@host:port/index (TLS)
	              opensearch://user:pass@host:port/index (non-TLS)
	Returns: (scheme, host, port, user, pass, index) or None if no URL
	Raises: URLParseError if URL is malformed
	"""
	if not url:
		return None

	# Handle opensearchs:// (TLS) and opensearch:// (non-TLS) schemes
	if url.startswith("opensearchs://"):
		actual_url = "https://" + url[len("opensearchs://"):]
		force_scheme = "https"
	elif url.startswith("opensearch://"):
		actual_url = "http://" + url[len("opensearch://"):]
		force_scheme = "http"
	else:
		actual_url = url
		force_scheme = None

	parsed = urlparse(actual_url)

	# Validate scheme
	if parsed.scheme and parsed.scheme not in ("http", "https"):
		raise URLParseError(f"Invalid URL scheme '{parsed.scheme}': must be 'http' or 'https'")

	# Validate hostname exists
	if not parsed.hostname:
		raise URLParseError(f"Invalid URL '{url}': missing hostname")

	scheme = force_scheme or parsed.scheme or "http"
	host = parsed.hostname
	port = parsed.port or (443 if scheme == "https" else 9200)
	# URL-decode username and password since urlparse doesn't do this automatically
	user = unquote(parsed.username) if parsed.username else None
	password = unquote(parsed.password) if parsed.password else None
	index = parsed.path.strip("/") or None
	return (scheme, host, port, user, password, index)


class DevlogsConfig:
	"""Loads configuration from environment variables and provides defaults.

	Configuration concepts:
	- DEVLOGS_URL: The collector base URL where applications send logs (ingestion endpoint)
	- DEVLOGS_FORWARD_URL: If set, collector forwards incoming requests to this URL (forward mode)
	- DEVLOGS_OPENSEARCH_*: Admin connection for direct OpenSearch access (search/tail/UI/CLI, and ingest mode)
	- DEVLOGS_INDEX: The OpenSearch index to use for log storage
	"""
	def __init__(self, enabled: bool = True):
		self.enabled = enabled

		# Collector URL (where apps send logs)
		self.collector_url = _getenv("DEVLOGS_URL", "")

		# Forward URL (if set, collector operates in forward mode)
		self.forward_url = _getenv("DEVLOGS_FORWARD_URL", "")

		# Check for URL shortcut first - it overrides individual settings
		# This is the admin OpenSearch connection used for search/tail/UI/CLI and ingest mode
		url_config = _parse_opensearch_url(os.getenv("DEVLOGS_OPENSEARCH_URL", ""))

		if url_config:
			scheme, host, port, url_user, url_pass, url_index = url_config
			self.opensearch_scheme = scheme
			self.opensearch_host = host
			self.opensearch_port = port
			# URL credentials override individual settings, but DEVLOGS_OPENSEARCH_PASS
			# can still override if URL omits password
			self.opensearch_user = url_user or _getenv("DEVLOGS_OPENSEARCH_USER", "admin")
			self.opensearch_pass = url_pass or _getenv("DEVLOGS_OPENSEARCH_PASS", "admin")
			# URL index takes priority, then DEVLOGS_INDEX env var, then default
			self.index = url_index or _getenv("DEVLOGS_INDEX", "devlogs-0001")
		else:
			self.opensearch_scheme = "http"
			self.opensearch_host = _getenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
			self.opensearch_port = int(_getenv("DEVLOGS_OPENSEARCH_PORT", "9200"))
			self.opensearch_user = _getenv("DEVLOGS_OPENSEARCH_USER", "admin")
			self.opensearch_pass = _getenv("DEVLOGS_OPENSEARCH_PASS", "admin")
			self.index = _getenv("DEVLOGS_INDEX", "devlogs-0001")

		self.opensearch_timeout = int(_getenv("DEVLOGS_OPENSEARCH_TIMEOUT", "30"))
		self.opensearch_verify_certs = _getenv("DEVLOGS_OPENSEARCH_VERIFY_CERTS", "true").lower() in ("true", "1", "yes")
		self.opensearch_ca_cert = _getenv("DEVLOGS_OPENSEARCH_CA_CERT", "")

		# Retention configuration (time-based cleanup)
		# Parse duration strings like "6h", "7d", or plain numbers
		self.retention_debug_hours = parse_duration(_getenv("DEVLOGS_RETENTION_DEBUG", "6h"), unit='hours')
		self.retention_info_days = parse_duration(_getenv("DEVLOGS_RETENTION_INFO", "7d"), unit='days')
		self.retention_warning_days = parse_duration(_getenv("DEVLOGS_RETENTION_WARNING", "30d"), unit='days')

		# Collector limits (future provisions - default unlimited)
		# Rate limit: requests per second (0 = unlimited)
		rate_limit_str = _getenv("DEVLOGS_COLLECTOR_RATE_LIMIT", "0")
		self.collector_rate_limit = int(rate_limit_str) if rate_limit_str else 0
		# Max payload size in bytes (0 = unlimited)
		max_payload_str = _getenv("DEVLOGS_COLLECTOR_MAX_PAYLOAD_SIZE", "0")
		self.collector_max_payload_size = int(max_payload_str) if max_payload_str else 0

		# Auth header name for token validation (legacy, use new auth system)
		self.auth_header = _getenv("DEVLOGS_AUTH_HEADER", "Authorization")

		# Authentication mode: allow_anonymous, require_token_passthrough, require_token_verified
		self.auth_mode = _getenv("DEVLOGS_AUTH_MODE", "allow_anonymous")

		# Token-to-identity mapping (KV format)
		self.token_map_kv = _getenv("DEVLOGS_TOKEN_MAP_KV", "")

		# Forward mode: per-application index routing (KV format)
		self.forward_index_map_kv = _getenv("DEVLOGS_FORWARD_INDEX_MAP_KV", "")

		# Forward mode: internal logs index
		self.forward_internal_index = _getenv("DEVLOGS_FORWARD_INTERNAL_INDEX", "")

		# Collector binding settings
		self.collector_host = _getenv("DEVLOGS_COLLECTOR_HOST", "0.0.0.0")
		self.collector_port = int(_getenv("DEVLOGS_COLLECTOR_PORT", "8080"))
		self.collector_workers = int(_getenv("DEVLOGS_COLLECTOR_WORKERS", "1"))
		self.collector_log_level = _getenv("DEVLOGS_COLLECTOR_LOG_LEVEL", "info")

	@property
	def url_mode(self) -> str:
		"""Return 'collector' if DEVLOGS_URL is set, 'opensearch' if OpenSearch is configured, else 'none'."""
		if self.collector_url:
			return "collector"
		if self.has_opensearch_config():
			return "opensearch"
		return "none"

	def has_opensearch_config(self) -> bool:
		"""Check if OpenSearch admin connection is configured."""
		return bool(
			os.getenv("DEVLOGS_OPENSEARCH_URL") or
			os.getenv("DEVLOGS_OPENSEARCH_HOST")
		)

	def get_collector_mode(self) -> str:
		"""Determine collector operating mode based on configuration.

		Returns:
			'forward' - if DEVLOGS_FORWARD_URL is set
			'ingest' - if OpenSearch admin connection is configured
			'error' - if neither is configured
		"""
		if self.forward_url:
			return 'forward'
		elif self.has_opensearch_config():
			return 'ingest'
		else:
			return 'error'

def set_dotenv_path(path: str):
	"""Set a custom .env file path to load. Must be called before load_config()."""
	global _custom_dotenv_path, _dotenv_loaded
	_custom_dotenv_path = path
	_dotenv_loaded = False  # Reset to force reload with new path


def set_url(url: str):
	"""Set the URL, auto-detecting whether it's a collector or OpenSearch URL.

	Uses parse_url() to detect the URL type:
	- Collector URLs → sets DEVLOGS_URL
	- OpenSearch URLs → sets DEVLOGS_OPENSEARCH_URL
	"""
	if not url:
		return
	try:
		parsed = parse_url(url)
	except URLParseError:
		# Fall back to legacy behavior
		os.environ["DEVLOGS_OPENSEARCH_URL"] = url
		return

	if isinstance(parsed, CollectorURLConfig):
		# Reconstruct the full collector URL for DEVLOGS_URL
		os.environ["DEVLOGS_URL"] = url
	else:
		# OpenSearch URL - reconstruct with the correct scheme for _parse_opensearch_url
		os.environ["DEVLOGS_OPENSEARCH_URL"] = url

def load_config() -> DevlogsConfig:
	"""Return a config object with all settings loaded."""
	global _dotenv_loaded, _custom_dotenv_path
	if not _dotenv_loaded:
		try:
			from dotenv import load_dotenv, find_dotenv
			# Check for DOTENV_PATH environment variable first
			dotenv_path = os.getenv("DOTENV_PATH") or _custom_dotenv_path
			if dotenv_path:
				# Load from explicitly specified path with override=True
				# to ensure custom env file values take precedence
				load_dotenv(dotenv_path, override=True)
			else:
				# Search for .env file in current directory and parents
				# Use usecwd=True to search from cwd, not from the source file location
				dotenv_path = find_dotenv(usecwd=True)
				if dotenv_path:
					load_dotenv(dotenv_path)
				# If no .env found, don't call load_dotenv() with no args
				# because it uses find_dotenv() without usecwd=True, which
				# would search from the source file location instead of cwd
		except ModuleNotFoundError:
			pass
		_dotenv_loaded = True
	enabled = _has_any_devlogs_settings()
	return DevlogsConfig(enabled=enabled)
