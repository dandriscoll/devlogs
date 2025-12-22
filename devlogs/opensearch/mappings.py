# OpenSearch index templates and mappings

LOG_INDEX_TEMPLATE = {
	"index_patterns": ["devlogs-logs-*"],
	"settings": {"number_of_shards": 1},
	"mappings": {
		"properties": {
			"timestamp": {"type": "date"},
			"level": {"type": "keyword"},
			"logger_name": {"type": "keyword"},
			"message": {"type": "text"},
			"area": {"type": "keyword"},
			"operation_id": {"type": "keyword"},
		}
	}
}

OP_INDEX_TEMPLATE = {
	"index_patterns": ["devlogs-ops-*"],
	"settings": {"number_of_shards": 1},
	"mappings": {
		"properties": {
			"operation_id": {"type": "keyword"},
			"area": {"type": "keyword"},
			"start_time": {"type": "date"},
			"end_time": {"type": "date"},
			"counts_by_level": {"type": "object"},
			"error_count": {"type": "integer"},
			"last_message": {"type": "text"},
		}
	}
}
