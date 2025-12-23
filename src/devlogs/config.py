# Configuration loading for devlogs

import os

from dotenv import load_dotenv

load_dotenv()

class DevlogsConfig:
	"""Loads configuration from environment variables and provides defaults."""
	def __init__(self):
		self.opensearch_host = os.getenv("OPENSEARCH_HOST", "localhost")
		self.opensearch_port = int(os.getenv("OPENSEARCH_PORT", "9200"))
		self.opensearch_user = os.getenv("OPENSEARCH_USER", "admin")
		self.opensearch_pass = os.getenv("OPENSEARCH_PASS", "admin")
		self.index_logs = os.getenv("DEVLOGS_INDEX_LOGS", "devlogs-0001")
		self.retention_debug_hours = int(os.getenv("DEVLOGS_RETENTION_DEBUG_HOURS", "24"))
		self.area_default = os.getenv("DEVLOGS_AREA_DEFAULT", "general")

def load_config() -> DevlogsConfig:
	"""Return a config object with all settings loaded."""
	return DevlogsConfig()
