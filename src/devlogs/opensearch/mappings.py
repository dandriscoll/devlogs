# OpenSearch index templates and mappings

LOG_INDEX_TEMPLATE = {
	"index_patterns": ["devlogs-*"],
	"template": {
		"settings": {"number_of_shards": 1},
		"mappings": {
			"properties": {
				"doc_type": {
					"type": "join",
					"relations": {
						"operation": "log_entry"
					}
				},
				"timestamp": {"type": "date"},
				"level": {"type": "keyword"},
				"logger_name": {"type": "keyword"},
				"message": {"type": "text"},
				"area": {"type": "keyword"},
				"operation_id": {"type": "keyword"},
				"features": {"type": "object", "dynamic": True},
				"start_time": {"type": "date"},
				"end_time": {"type": "date"},
				"counts_by_level": {"type": "object"},
				"error_count": {"type": "integer"},
				"last_message": {"type": "text"},
			}
		}
	}
}
