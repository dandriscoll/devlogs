# Configuration loading for devlogs

import os
import re
from urllib.parse import urlparse

# Lazy load dotenv - only when config is first accessed
_dotenv_loaded = False
_custom_dotenv_path = None

_DEVLOGS_CONFIG_KEYS = (
	"DEVLOGS_OPENSEARCH_HOST",
	"DEVLOGS_OPENSEARCH_PORT",
	"DEVLOGS_OPENSEARCH_USER",
	"DEVLOGS_OPENSEARCH_PASS",
	"DEVLOGS_OPENSEARCH_TIMEOUT",
	"DEVLOGS_OPENSEARCH_URL",
	"DEVLOGS_OPENSEARCH_VERIFY_CERTS",
	"DEVLOGS_OPENSEARCH_CA_CERT",
	"DEVLOGS_INDEX",
	"DEVLOGS_RETENTION_DEBUG",
	"DEVLOGS_RETENTION_INFO",
	"DEVLOGS_RETENTION_WARNING",
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

def _parse_opensearch_url(url: str):
	"""Parse DEVLOGS_OPENSEARCH_URL into components.

	Supports format: https://user:pass@host:port/index
	Returns: (scheme, host, port, user, pass, index) or None if no URL
	"""
	if not url:
		return None
	parsed = urlparse(url)
	scheme = parsed.scheme or "http"
	host = parsed.hostname or "localhost"
	port = parsed.port or (443 if scheme == "https" else 9200)
	user = parsed.username
	password = parsed.password
	index = parsed.path.strip("/") or None
	return (scheme, host, port, user, password, index)


class DevlogsConfig:
	"""Loads configuration from environment variables and provides defaults."""
	def __init__(self, enabled: bool = True):
		self.enabled = enabled

		# Check for URL shortcut first - it overrides individual settings
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

def set_dotenv_path(path: str):
	"""Set a custom .env file path to load. Must be called before load_config()."""
	global _custom_dotenv_path, _dotenv_loaded
	_custom_dotenv_path = path
	_dotenv_loaded = False  # Reset to force reload with new path

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
