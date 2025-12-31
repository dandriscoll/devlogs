# Configuration loading for devlogs

import os

# Lazy load dotenv - only when config is first accessed
_dotenv_loaded = False
_custom_dotenv_path = None

def _getenv(name, default):
	value = os.getenv(name)
	return value if value else default

class DevlogsConfig:
	"""Loads configuration from environment variables and provides defaults."""
	def __init__(self):
		self.opensearch_host = _getenv("DEVLOGS_OPENSEARCH_HOST", "localhost")
		self.opensearch_port = int(_getenv("DEVLOGS_OPENSEARCH_PORT", "9200"))
		self.opensearch_user = _getenv("DEVLOGS_OPENSEARCH_USER", "admin")
		self.opensearch_pass = _getenv("DEVLOGS_OPENSEARCH_PASS", "admin")
		self.opensearch_timeout = int(_getenv("DEVLOGS_OPENSEARCH_TIMEOUT", "30"))
		self.index_logs = _getenv("DEVLOGS_INDEX_LOGS", "devlogs-0001")
		# Retention configuration (time-based cleanup)
		self.retention_debug_hours = int(_getenv("DEVLOGS_RETENTION_DEBUG_HOURS", "6"))
		self.retention_info_days = int(_getenv("DEVLOGS_RETENTION_INFO_DAYS", "7"))
		self.retention_warning_days = int(_getenv("DEVLOGS_RETENTION_WARNING_DAYS", "30"))
		self.area_default = _getenv("DEVLOGS_AREA_DEFAULT", "general")

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
				dotenv_path = find_dotenv(usecwd=True)
				if dotenv_path:
					load_dotenv(dotenv_path)
				else:
					load_dotenv()
		except ModuleNotFoundError:
			pass
		_dotenv_loaded = True
	return DevlogsConfig()
