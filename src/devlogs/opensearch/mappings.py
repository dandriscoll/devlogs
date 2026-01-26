# OpenSearch index templates and mappings

from typing import Optional


# Current schema version
SCHEMA_VERSION = 2

# V2 required fields (flat schema)
V2_REQUIRED_FIELDS = {"logger", "funcname", "fields"}

# V1 fields that indicate old schema
V1_INDICATOR_FIELDS = {"logger_name", "features", "funcName"}


def detect_schema_version(mapping: dict) -> Optional[int]:
	"""Detect schema version from index mapping.

	Returns:
		2 if v2-compatible (flat schema with logger, funcname, fields)
		1 if v1 schema (nested source/process, logger_name, features)
		None if unknown/empty
	"""
	if not mapping:
		return None

	# Extract properties from mapping (handle different response formats)
	properties = mapping.get("properties", {})
	if not properties:
		# Try nested format from get_mapping response
		for index_data in mapping.values():
			if isinstance(index_data, dict):
				properties = index_data.get("mappings", {}).get("properties", {})
				if properties:
					break

	if not properties:
		return None

	field_names = set(properties.keys())

	# Check for v2 indicators
	has_v2_fields = V2_REQUIRED_FIELDS.issubset(field_names)

	# Check for v1 indicators
	has_v1_fields = bool(V1_INDICATOR_FIELDS & field_names)

	# Check if process is an object (v1) vs integer (v2)
	process_mapping = properties.get("process", {})
	process_is_object = process_mapping.get("type") == "object" or "properties" in process_mapping

	if has_v2_fields and not has_v1_fields and not process_is_object:
		return 2
	elif has_v1_fields or process_is_object:
		return 1

	# If we have some standard fields but can't determine version, assume v1
	if field_names & {"timestamp", "level", "message"}:
		return 1

	return None


def get_schema_issues(mapping: dict) -> list[str]:
	"""Get list of schema compatibility issues.

	Returns list of human-readable issues that need to be fixed for v2 compatibility.
	"""
	issues = []

	properties = mapping.get("properties", {})
	if not properties:
		for index_data in mapping.values():
			if isinstance(index_data, dict):
				properties = index_data.get("mappings", {}).get("properties", {})
				if properties:
					break

	if not properties:
		return ["No mapping properties found"]

	field_names = set(properties.keys())

	# Check for old field names
	if "logger_name" in field_names:
		issues.append("Has 'logger_name' field (v2 uses 'logger')")
	if "funcName" in field_names:
		issues.append("Has 'funcName' field (v2 uses 'funcname')")
	if "features" in field_names:
		issues.append("Has 'features' field (v2 uses 'fields')")

	# Check process type
	process_mapping = properties.get("process", {})
	if process_mapping.get("type") == "object" or "properties" in process_mapping:
		issues.append("'process' is an object (v2 expects integer)")

	# Check for nested source object
	if "source" in field_names:
		source_mapping = properties.get("source", {})
		if source_mapping.get("type") == "object" or "properties" in source_mapping:
			issues.append("Has nested 'source' object (v2 uses flat fields)")

	# Check for missing v2 fields
	for field in V2_REQUIRED_FIELDS:
		if field not in field_names:
			issues.append(f"Missing '{field}' field")

	return issues


def build_reindex_script() -> str:
	"""Build Painless script to transform v1 documents to v2 schema."""
	return """
		// Transform logger_name to logger
		if (ctx._source.containsKey('logger_name')) {
			ctx._source.logger = ctx._source.remove('logger_name');
		}
		// Transform source.logger to logger (if nested)
		if (ctx._source.containsKey('source') && ctx._source.source instanceof Map) {
			if (ctx._source.source.containsKey('logger')) {
				ctx._source.logger = ctx._source.source.logger;
			}
			if (ctx._source.source.containsKey('pathname')) {
				ctx._source.pathname = ctx._source.source.pathname;
			}
			if (ctx._source.source.containsKey('lineno')) {
				ctx._source.lineno = ctx._source.source.lineno;
			}
			if (ctx._source.source.containsKey('funcName')) {
				ctx._source.funcname = ctx._source.source.funcName;
			}
			ctx._source.remove('source');
		}
		// Transform funcName to funcname
		if (ctx._source.containsKey('funcName')) {
			ctx._source.funcname = ctx._source.remove('funcName');
		}
		// Transform features to fields
		if (ctx._source.containsKey('features')) {
			ctx._source.fields = ctx._source.remove('features');
		}
		// Transform nested process object to flat fields
		if (ctx._source.containsKey('process') && ctx._source.process instanceof Map) {
			def proc = ctx._source.process;
			if (proc.containsKey('id')) {
				ctx._source.process = proc.id;
			}
			if (proc.containsKey('thread')) {
				ctx._source.thread = proc.thread;
			}
		}
	""".strip()


def build_log_index_template(index_name: str) -> dict:
	"""Return the composable index template for the exact index name."""
	base_template = {
		"index_patterns": [index_name],
		"priority": 100,
		"template": {
			"settings": {"number_of_shards": 1, "number_of_replicas": 0},
			"mappings": {
				"properties": {
					# Core log entry fields (flat schema)
					"doc_type": {"type": "keyword"},  # Always "log_entry"
					"timestamp": {"type": "date"},
					"level": {"type": "keyword"},
					"levelno": {"type": "integer"},
					"logger": {"type": "keyword"},
					"message": {"type": "text"},
					"area": {"type": "keyword"},
					"operation_id": {"type": "keyword"},
					"pathname": {"type": "keyword"},
					"lineno": {"type": "integer"},
					"funcname": {"type": "keyword"},
					"thread": {"type": "long"},
					"process": {"type": "integer"},
					"exception": {"type": "text"},
					"fields": {"type": "object", "dynamic": True},
				}
			}
		}
	}
	return base_template


def build_legacy_log_template(index_name: str) -> dict:
	"""Return the legacy template payload for clusters without composable templates."""
	template = build_log_index_template(index_name)
	return {
		"index_patterns": template["index_patterns"],
		"settings": template["template"]["settings"],
		"mappings": template["template"]["mappings"],
	}


def get_template_names(index_name: str) -> tuple[str, str]:
	"""Return deterministic template names based on the index name."""
	return (f"{index_name}-template", f"{index_name}-legacy-template")
