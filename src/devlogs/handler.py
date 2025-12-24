# OpenSearchHandler implementation

import logging
import uuid
from datetime import datetime, timezone
from .context import get_area, get_operation_id, get_parent_operation_id

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
				operation_id = doc.get("operation_id")
				if operation_id:
					doc["doc_type"] = {"name": "log_entry", "parent": operation_id}
					self.client.index(index=self.index_name, body=doc, routing=operation_id)
				else:
					doc["doc_type"] = "operation"
					self.client.index(index=self.index_name, body=doc)
		except Exception as e:
			# Fallback: print warning, do not crash
			print(f"[devlogs] Failed to index log: {e}")

	def format_record(self, record):
		# Compose log document with context
		timestamp = None
		if getattr(record, "created", None) is not None:
			timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat().replace("+00:00", "Z")
		return {
			"timestamp": timestamp,
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
			"parent_operation_id": get_parent_operation_id(),
		}


class DiagnosticsHandler(OpenSearchHandler):
	"""Diagnostics handler that always accepts DEBUG and routes parent/child docs."""
	def __init__(self, opensearch_client=None, index_name=None):
		super().__init__(level=logging.DEBUG, opensearch_client=opensearch_client, index_name=index_name)

	def emit(self, record):
		doc = self.format_record(record)
		operation_id = doc.get("operation_id")
		if not operation_id:
			operation_id = str(uuid.uuid4())
			doc["operation_id"] = operation_id

		if operation_id and (get_operation_id() or getattr(record, "operation_id", None)):
			doc["doc_type"] = {"name": "log_entry", "parent": operation_id}
			routing = operation_id
		else:
			doc["doc_type"] = "operation"
			routing = operation_id

		try:
			if self.client:
				self.client.index(index=self.index_name, body=doc, routing=routing)
		except Exception as e:
			print(f"[devlogs] Failed to index log: {e}")

	def format_record(self, record):
		doc = super().format_record(record)
		extra_area = getattr(record, "area", None)
		extra_operation = getattr(record, "operation_id", None)
		if extra_area:
			doc["area"] = extra_area
		if extra_operation:
			doc["operation_id"] = extra_operation
		return doc
