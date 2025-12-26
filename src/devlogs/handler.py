# OpenSearchHandler implementation

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from .context import get_area, get_operation_id, get_parent_operation_id
from .levels import normalize_level

_FEATURE_VALUE_TYPES = (str, int, float, bool, type(None))


def _coerce_feature_value(value: Any) -> Any:
	if isinstance(value, _FEATURE_VALUE_TYPES):
		return value
	return str(value)


def _normalize_features(value: Any) -> Optional[Dict[str, Any]]:
	if value is None:
		return None
	features: Dict[str, Any] = {}
	items: Sequence[Tuple[Any, Any]]
	if isinstance(value, Mapping):
		items = list(value.items())
	elif isinstance(value, (list, tuple, set)):
		items = list(value)
	else:
		return None
	for item in items:
		if isinstance(value, Mapping):
			key, val = item
		else:
			if not isinstance(item, (list, tuple)) or len(item) != 2:
				continue
			key, val = item
		if key is None:
			continue
		key_text = str(key).strip()
		if not key_text:
			continue
		features[key_text] = _coerce_feature_value(val)
	return features or None


def _extract_features(record: logging.LogRecord) -> Optional[Dict[str, Any]]:
	return _normalize_features(getattr(record, "features", None))


class OpenSearchHandler(logging.Handler):
	"""Logging handler that writes log records to OpenSearch."""
	# Circuit breaker state shared across all instances
	_circuit_open = False
	_circuit_open_until = 0.0
	_circuit_breaker_duration = 60.0  # seconds to wait before retrying
	_last_error_printed = 0.0
	_error_print_interval = 10.0  # only print errors every 10 seconds

	def __init__(self, level=logging.DEBUG, opensearch_client=None, index_name=None):
		super().__init__(level)
		self.client = opensearch_client
		self.index_name = index_name

	def emit(self, record):
		# Build log document
		doc = self.format_record(record)

		# Circuit breaker: skip indexing if we know the index is unavailable
		current_time = time.time()
		if OpenSearchHandler._circuit_open and current_time < OpenSearchHandler._circuit_open_until:
			# Silently fail - circuit is open
			return

		# Index document
		try:
			if self.client:
				operation_id = doc.get("operation_id")
				if operation_id:
					doc["doc_type"] = {"name": "log_entry", "parent": operation_id}
					self.client.index(index=self.index_name, body=doc, routing=operation_id)
				else:
					doc["doc_type"] = "operation"
					self.client.index(index=self.index_name, body=doc)
				# Success - close circuit breaker if it was open
				if OpenSearchHandler._circuit_open:
					OpenSearchHandler._circuit_open = False
					print(f"[devlogs] Connection restored, resuming indexing")
		except Exception as e:
			# Open circuit breaker to prevent further attempts
			OpenSearchHandler._circuit_open = True
			OpenSearchHandler._circuit_open_until = current_time + OpenSearchHandler._circuit_breaker_duration

			# Only print error occasionally to avoid log spam
			if current_time - OpenSearchHandler._last_error_printed > OpenSearchHandler._error_print_interval:
				print(f"[devlogs] Failed to index log, pausing indexing for {OpenSearchHandler._circuit_breaker_duration}s: {e}")
				OpenSearchHandler._last_error_printed = current_time

	def format_record(self, record):
		# Compose log document with context
		timestamp = None
		if getattr(record, "created", None) is not None:
			timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat().replace("+00:00", "Z")
		doc = {
			"timestamp": timestamp,
			"level": normalize_level(record.levelname),
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
		features = _extract_features(record)
		if features:
			doc["features"] = features
		return doc


class DiagnosticsHandler(OpenSearchHandler):
	"""Diagnostics handler that always accepts DEBUG and routes parent/child docs."""
	def __init__(self, opensearch_client=None, index_name=None):
		super().__init__(level=logging.DEBUG, opensearch_client=opensearch_client, index_name=index_name)

	def emit(self, record):
		# Circuit breaker: skip indexing if we know the index is unavailable
		current_time = time.time()
		if OpenSearchHandler._circuit_open and current_time < OpenSearchHandler._circuit_open_until:
			# Silently fail - circuit is open
			return

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
				# Success - close circuit breaker if it was open
				if OpenSearchHandler._circuit_open:
					OpenSearchHandler._circuit_open = False
					print(f"[devlogs] Connection restored, resuming indexing")
		except Exception as e:
			# Open circuit breaker to prevent further attempts
			OpenSearchHandler._circuit_open = True
			OpenSearchHandler._circuit_open_until = current_time + OpenSearchHandler._circuit_breaker_duration

			# Only print error occasionally to avoid log spam
			if current_time - OpenSearchHandler._last_error_printed > OpenSearchHandler._error_print_interval:
				print(f"[devlogs] Failed to index log, pausing indexing for {OpenSearchHandler._circuit_breaker_duration}s: {e}")
				OpenSearchHandler._last_error_printed = current_time

	def format_record(self, record):
		doc = super().format_record(record)
		extra_area = getattr(record, "area", None)
		extra_operation = getattr(record, "operation_id", None)
		if extra_area:
			doc["area"] = extra_area
		if extra_operation:
			doc["operation_id"] = extra_operation
		return doc
