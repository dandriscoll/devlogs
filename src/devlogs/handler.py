# DevlogsHandler implementation
#
# A Python logging handler that writes log records to OpenSearch using
# the devlogs record schema (v2.0).

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from .context import get_area, get_operation_id
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


class DevlogsHandler(logging.Handler):
	"""Logging handler that writes log records to OpenSearch.

	Uses the devlogs v2.0 schema with required application and component fields,
	and top-level message, level, and area fields.

	Usage:
		from devlogs.handler import DevlogsHandler

		handler = DevlogsHandler(
			application="my-app",
			component="api",
			level=logging.INFO,
		)
		logging.getLogger().addHandler(handler)
	"""
	# Circuit breaker state shared across all instances
	_circuit_open = False
	_circuit_open_until = 0.0
	_circuit_breaker_duration = 60.0  # seconds to wait before retrying
	_last_error_printed = 0.0
	_error_print_interval = 10.0  # only print errors every 10 seconds

	def __init__(
		self,
		application: str = "unknown",
		component: str = "default",
		level: int = logging.DEBUG,
		opensearch_client: Any = None,
		index_name: Optional[str] = None,
		environment: Optional[str] = None,
		version: Optional[str] = None,
	):
		"""Initialize the DevlogsHandler.

		Args:
			application: Application name (required for devlogs schema)
			component: Component name within the application
			level: Minimum log level to handle
			opensearch_client: OpenSearch client instance (auto-created if None)
			index_name: Target OpenSearch index (from config if None)
			environment: Deployment environment (optional)
			version: Application version (optional)
		"""
		super().__init__(level)
		self.application = application
		self.component = component
		self.environment = environment
		self.version = version
		self.client = opensearch_client
		self.index_name = index_name

	def emit(self, record: logging.LogRecord) -> None:
		"""Emit a log record to OpenSearch."""
		# Build log document
		doc = self.format_record(record)

		# Circuit breaker: skip indexing if we know the index is unavailable
		current_time = time.time()
		if DevlogsHandler._circuit_open and current_time < DevlogsHandler._circuit_open_until:
			# Silently fail - circuit is open
			return

		# Index document
		try:
			if self.client:
				doc["doc_type"] = "log_entry"
				self.client.index(index=self.index_name, body=doc)
				# Success - close circuit breaker if it was open
				if DevlogsHandler._circuit_open:
					DevlogsHandler._circuit_open = False
					print(f"[devlogs] Connection restored, resuming indexing")
		except Exception as e:
			# Open circuit breaker to prevent further attempts
			DevlogsHandler._circuit_open = True
			DevlogsHandler._circuit_open_until = current_time + DevlogsHandler._circuit_breaker_duration

			# Only print error occasionally to avoid log spam
			if current_time - DevlogsHandler._last_error_printed > DevlogsHandler._error_print_interval:
				print(f"[devlogs] Failed to index log, pausing indexing for {DevlogsHandler._circuit_breaker_duration}s: {e}")
				DevlogsHandler._last_error_printed = current_time

	def format_record(self, record: logging.LogRecord) -> Dict[str, Any]:
		"""Format a log record into a devlogs schema document.

		Returns a document with the devlogs v2.0 schema:
		- Required: application, component, timestamp
		- Top-level: message, level, area
		- Optional: environment, version, fields, identity
		"""
		# Generate timestamp
		timestamp = None
		if getattr(record, "created", None) is not None:
			timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat().replace("+00:00", "Z")

		# Build document with devlogs v2.0 schema
		doc: Dict[str, Any] = {
			# Required fields
			"application": self.application,
			"component": self.component,
			"timestamp": timestamp,
			# Top-level log fields
			"message": self.format(record),
			"level": normalize_level(record.levelname),
			"area": getattr(record, "area", None) or get_area(),
		}

		# Optional standardized fields
		if self.environment:
			doc["environment"] = self.environment
		if self.version:
			doc["version"] = self.version

		# Operation ID for request correlation
		operation_id = getattr(record, "operation_id", None) or get_operation_id()
		if operation_id:
			doc["operation_id"] = operation_id

		# Custom fields
		fields = _extract_features(record)
		if fields:
			doc["fields"] = fields

		# Source location info (flat schema to match mappings)
		doc["logger"] = record.name
		doc["pathname"] = record.pathname
		doc["lineno"] = record.lineno
		doc["funcname"] = record.funcName

		# Process/thread info (flat schema to match mappings)
		doc["process"] = record.process
		doc["thread"] = record.thread

		# Exception info if present
		exc_text = getattr(record, "exc_text", None)
		if exc_text:
			doc["exception"] = exc_text

		return doc


# Backward compatibility alias
OpenSearchHandler = DevlogsHandler


class DiagnosticsHandler(DevlogsHandler):
	"""Diagnostics handler that always accepts DEBUG level.

	Auto-generates operation_id if not set.
	"""
	def __init__(
		self,
		application: str = "diagnostics",
		component: str = "default",
		opensearch_client: Any = None,
		index_name: Optional[str] = None,
	):
		super().__init__(
			application=application,
			component=component,
			level=logging.DEBUG,
			opensearch_client=opensearch_client,
			index_name=index_name,
		)

	def emit(self, record: logging.LogRecord) -> None:
		# Circuit breaker: skip indexing if we know the index is unavailable
		current_time = time.time()
		if DevlogsHandler._circuit_open and current_time < DevlogsHandler._circuit_open_until:
			# Silently fail - circuit is open
			return

		doc = self.format_record(record)

		# Auto-generate operation_id if not present
		if not doc.get("operation_id"):
			doc["operation_id"] = str(uuid.uuid4())

		doc["doc_type"] = "log_entry"

		try:
			if self.client:
				self.client.index(index=self.index_name, body=doc)
				# Success - close circuit breaker if it was open
				if DevlogsHandler._circuit_open:
					DevlogsHandler._circuit_open = False
					print(f"[devlogs] Connection restored, resuming indexing")
		except Exception as e:
			# Open circuit breaker to prevent further attempts
			DevlogsHandler._circuit_open = True
			DevlogsHandler._circuit_open_until = current_time + DevlogsHandler._circuit_breaker_duration

			# Only print error occasionally to avoid log spam
			if current_time - DevlogsHandler._last_error_printed > DevlogsHandler._error_print_interval:
				print(f"[devlogs] Failed to index log, pausing indexing for {DevlogsHandler._circuit_breaker_duration}s: {e}")
				DevlogsHandler._last_error_printed = current_time
