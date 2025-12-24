# Configuration loading for devlogs

import os

# Lazy load dotenv - only when config is first accessed
_dotenv_loaded = False

def _getenv(name, default):
	value = os.getenv(name)
	return value if value else default

class DevlogsConfig:
	"""Loads configuration from environment variables and provides defaults."""
	def __init__(self):
		self.opensearch_host = _getenv("OPENSEARCH_HOST", "localhost")
		self.opensearch_port = int(_getenv("OPENSEARCH_PORT", "9200"))
		self.opensearch_user = _getenv("OPENSEARCH_USER", "admin")
		self.opensearch_pass = _getenv("OPENSEARCH_PASS", "admin")
		self.opensearch_timeout = int(_getenv("OPENSEARCH_TIMEOUT", "30"))
		self.index_logs = _getenv("DEVLOGS_INDEX_LOGS", "devlogs-0001")
		self.retention_debug_hours = int(_getenv("DEVLOGS_RETENTION_DEBUG_HOURS", "24"))
		self.area_default = _getenv("DEVLOGS_AREA_DEFAULT", "general")

def load_config() -> DevlogsConfig:
	"""Return a config object with all settings loaded."""
	global _dotenv_loaded
	if not _dotenv_loaded:
		try:
			from dotenv import load_dotenv
			load_dotenv()
		except ModuleNotFoundError:
			pass
		_dotenv_loaded = True
	return DevlogsConfig()
