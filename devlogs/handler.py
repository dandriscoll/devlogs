# OpenSearchHandler implementation

import logging
from .context import get_area, get_operation_id

class OpenSearchHandler(logging.Handler):
	"""Logging handler that writes log records to OpenSearch."""
	def __init__(self, level=logging.DEBUG, opensearch_client=None, index_name=None):
		super().__init__(level)
		self.client = opensearch_client
		self.index_name = index_name

	def emit(self, record):
		# Build log document
		doc = self.format_record(record)
		# Index document (stub)
		try:
			if self.client:
				self.client.index(index=self.index_name, body=doc)
		except Exception as e:
			# Fallback: print warning, do not crash
			print(f"[devlogs] Failed to index log: {e}")

	def format_record(self, record):
		# Compose log document with context
		return {
			"timestamp": getattr(record, "created", None),
			"level": record.levelname,
			"levelno": record.levelno,
			"logger_name": record.name,
			"message": self.format(record),
			"pathname": record.pathname,
			"lineno": record.lineno,
			"funcName": record.funcName,
			"thread": record.thread,
			"process": record.process,
			"exception": getattr(record, "exc_text", None),
			"area": get_area(),
			"operation_id": get_operation_id(),
		}
