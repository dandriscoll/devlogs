# OpenSearch index templates and mappings

def build_log_index_template(index_name: str) -> dict:
	"""Return the composable index template for the exact index name."""
	base_template = {
		"index_patterns": [index_name],
		"priority": 100,
		"template": {
			"settings": {"number_of_shards": 1},
			"mappings": {
				"properties": {
					# Core log entry fields (flat schema)
					"doc_type": {"type": "keyword"},  # Always "log_entry"
					"timestamp": {"type": "date"},
					"level": {"type": "keyword"},
					"levelno": {"type": "integer"},
					"logger_name": {"type": "keyword"},
					"message": {"type": "text"},
					"area": {"type": "keyword"},
					"operation_id": {"type": "keyword"},
					"pathname": {"type": "keyword"},
					"lineno": {"type": "integer"},
					"funcName": {"type": "keyword"},
					"thread": {"type": "long"},
					"process": {"type": "integer"},
					"exception": {"type": "text"},
					"features": {"type": "object", "dynamic": True},
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
