# Search APIs for OpenSearch

from typing import Any, Dict, Iterable, List, Optional, Tuple
from ..levels import normalize_level
from .client import IndexNotFoundError


def _normalize_level_terms(level: Optional[str]) -> Optional[List[str]]:
	normalized = normalize_level(level)
	if not normalized:
		return None
	terms = {normalized, normalized.upper()}
	if isinstance(level, str):
		raw = level.strip()
		if raw:
			terms.add(raw)
	return sorted(terms)


def _build_log_query(query=None, area=None, operation_id=None, level=None, since=None):
	filters = [
		{
			"bool": {
				"should": [
					{"term": {"doc_type": "log_entry"}},
					{"bool": {"must_not": {"exists": {"field": "doc_type"}}}},
				],
				"minimum_should_match": 1,
			}
		}
	]
	if area:
		filters.append({"term": {"area": area}})
	if operation_id:
		filters.append({"term": {"operation_id": operation_id}})
	level_terms = _normalize_level_terms(level)
	if level_terms:
		filters.append({"terms": {"level": level_terms}})
	if since:
		filters.append({"range": {"timestamp": {"gte": since}}})

	bool_query: Dict[str, Any] = {"filter": filters}
	if query:
		bool_query["must"] = [
			{
					"simple_query_string": {
						"query": query,
						"fields": [
							"message^2",
							"logger_name",
							"operation_id",
							"area",
							"features.*",
						],
						"default_operator": "and",
						"lenient": True,
					}
				}
			]
	return {"bool": bool_query}


def _hits_to_docs(hits: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
	docs = []
	for hit in hits:
		source = hit.get("_source", {})
		doc = dict(source)
		doc["id"] = hit.get("_id")
		doc["sort"] = hit.get("sort")
		docs.append(doc)
	return docs


def _require_response(response: Any, context: str, client=None, index=None) -> Dict[str, Any]:
	if response is None:
		if client is not None and index is not None:
			if not client.indices.exists(index=index):
				raise IndexNotFoundError(
					f"Index '{index}' does not exist.\n"
					f"Run 'devlogs init' to create it."
				)
		raise ValueError(f"OpenSearch {context} returned None")
	if not isinstance(response, dict):
		raise ValueError(f"OpenSearch {context} returned {type(response).__name__}")
	return response


def _normalize_entry(doc: Dict[str, Any]) -> Dict[str, Any]:
	return {
		"timestamp": doc.get("timestamp"),
		"level": normalize_level(doc.get("level")),
		"message": doc.get("message"),
		"logger_name": doc.get("logger_name"),
		"area": doc.get("area"),
		"operation_id": doc.get("operation_id"),
		"pathname": doc.get("pathname"),
		"lineno": doc.get("lineno"),
		"exception": doc.get("exception"),
		"features": doc.get("features"),
	}


def normalize_log_entries(docs: Iterable[Dict[str, Any]], limit: Optional[int] = None) -> List[Dict[str, Any]]:
	"""Normalize log entries from OpenSearch documents."""
	entries: List[Dict[str, Any]] = []
	for doc in docs:
		entries.append(_normalize_entry(doc))
		if limit is not None and len(entries) >= limit:
			return entries[:limit]
	return entries


def search_logs(client, index, query=None, area=None, operation_id=None, level=None, since=None, limit=50):
	"""Search log entries with filters."""
	body = {
		"query": _build_log_query(
			query=query,
			area=area,
			operation_id=operation_id,
			level=level,
			since=since,
		),
		"sort": [{"timestamp": "desc"}, {"_id": "desc"}],
		"size": limit,
	}
	response = _require_response(client.search(index=index, body=body), "search", client=client, index=index)
	hits = response.get("hits", {}).get("hits", [])
	return _hits_to_docs(hits)


def tail_logs(client, index, query=None, operation_id=None, area=None, level=None, since=None, limit=20, search_after=None):
	"""Tail log entries for an operation.

	Always fetches in descending order (newest first), reverses for chronological display.
	Pagination continues from oldest fetched, going backwards in time.
	"""
	body = {
		"query": _build_log_query(
			query=query,
			area=area,
			operation_id=operation_id,
			level=level,
			since=since,
		),
		"sort": [{"timestamp": "desc"}, {"_id": "desc"}],
		"size": limit,
	}
	if search_after:
		body["search_after"] = search_after
	response = _require_response(client.search(index=index, body=body), "tail", client=client, index=index)
	hits = response.get("hits", {}).get("hits", [])
	docs = _hits_to_docs(hits)

	if docs:
		# Fetch is in DESC order (newest first)
		# Cursor points to oldest fetched (last in DESC list) for next page
		next_search_after = docs[-1]["sort"]
		# Reverse to chronological order for display (oldest first)
		docs = list(reversed(docs))
	else:
		next_search_after = search_after

	return docs, next_search_after


def get_operation_summary(client, index, operation_id):
	"""Get summary for an operation using aggregations."""
	body = {
		"query": {"term": {"operation_id": operation_id}},
		"size": 0,  # No documents, aggregations only
		"aggs": {
			"by_level": {
				"terms": {"field": "level", "size": 10}
			},
			"time_range": {
				"stats": {"field": "timestamp"}
			},
			"sample_logs": {
				"top_hits": {
					"size": 10,
					"sort": [{"timestamp": "asc"}],
					"_source": ["timestamp", "level", "message", "logger_name", "exception", "features"]
				}
			},
			"total_count": {
				"value_count": {"field": "timestamp"}
			}
		}
	}

	try:
		response = _require_response(client.search(index=index, body=body), "get_operation_summary", client=client, index=index)
	except Exception:
		return None

	aggs = response.get("aggregations", {})

	# Extract level counts
	counts_by_level = {}
	for bucket in aggs.get("by_level", {}).get("buckets", []):
		counts_by_level[bucket["key"]] = bucket["doc_count"]

	# Extract time range
	time_stats = aggs.get("time_range", {})
	start_time = time_stats.get("min_as_string")
	end_time = time_stats.get("max_as_string")

	# Extract sample logs
	sample_hits = aggs.get("sample_logs", {}).get("hits", {}).get("hits", [])
	sample_logs = [hit["_source"] for hit in sample_hits]

	# Calculate error count
	error_count = counts_by_level.get("error", 0) + counts_by_level.get("critical", 0)

	# Total count
	total_count = aggs.get("total_count", {}).get("value", 0)

	return {
		"operation_id": operation_id,
		"counts_by_level": counts_by_level,
		"error_count": error_count,
		"start_time": start_time,
		"end_time": end_time,
		"total_entries": total_count,
		"sample_logs": sample_logs
	}


def list_operations(client, index, area=None, since=None, limit=20, with_errors_only=False):
	"""List recent operations with summary stats."""
	query_filters = []
	if area:
		query_filters.append({"term": {"area": area}})
	if since:
		query_filters.append({"range": {"timestamp": {"gte": since}}})

	body = {
		"query": {"bool": {"filter": query_filters}} if query_filters else {"match_all": {}},
		"size": 0,
		"aggs": {
			"by_operation": {
				"terms": {"field": "operation_id", "size": limit},
				"aggs": {
					"area": {"terms": {"field": "area", "size": 1}},
					"time_range": {"stats": {"field": "timestamp"}},
					"by_level": {"terms": {"field": "level", "size": 10}},
					"error_count": {
						"filter": {
							"terms": {"level": ["error", "critical"]}
						}
					}
				}
			}
		}
	}

	try:
		response = _require_response(client.search(index=index, body=body), "list_operations", client=client, index=index)
	except Exception:
		return []

	# Parse aggregation results
	operations = []
	for bucket in response.get("aggregations", {}).get("by_operation", {}).get("buckets", []):
		area_buckets = bucket.get("area", {}).get("buckets", [])
		op_area = area_buckets[0]["key"] if area_buckets else None

		time_stats = bucket.get("time_range", {})
		start_time = time_stats.get("min_as_string")
		end_time = time_stats.get("max_as_string")

		# Calculate duration if we have both timestamps
		duration_ms = None
		if time_stats.get("min") and time_stats.get("max"):
			duration_ms = int(time_stats["max"] - time_stats["min"])

		counts_by_level = {}
		for level_bucket in bucket.get("by_level", {}).get("buckets", []):
			counts_by_level[level_bucket["key"]] = level_bucket["doc_count"]

		error_count = bucket.get("error_count", {}).get("doc_count", 0)

		op = {
			"operation_id": bucket["key"],
			"area": op_area,
			"start_time": start_time,
			"end_time": end_time,
			"duration_ms": duration_ms,
			"total_logs": bucket["doc_count"],
			"error_count": error_count,
			"log_levels": counts_by_level
		}
		operations.append(op)

	# Filter by error count if requested
	if with_errors_only:
		operations = [op for op in operations if op["error_count"] > 0]

	return operations


def list_areas(client, index, since=None, min_operations=1):
	"""List all application areas with activity counts."""
	query_filters = []
	if since:
		query_filters.append({"range": {"timestamp": {"gte": since}}})

	body = {
		"query": {"bool": {"filter": query_filters}} if query_filters else {"match_all": {}},
		"size": 0,
		"aggs": {
			"by_area": {
				"terms": {"field": "area", "size": 100},
				"aggs": {
					"operation_count": {
						"cardinality": {"field": "operation_id"}
					},
					"error_count": {
						"filter": {
							"terms": {"level": ["error", "critical"]}
						}
					},
					"last_activity": {
						"max": {"field": "timestamp"}
					}
				}
			}
		}
	}

	try:
		response = _require_response(client.search(index=index, body=body), "list_areas", client=client, index=index)
	except Exception:
		return []

	# Parse aggregation results
	areas = []
	for bucket in response.get("aggregations", {}).get("by_area", {}).get("buckets", []):
		operation_count = bucket.get("operation_count", {}).get("value", 0)

		# Filter by min_operations
		if operation_count < min_operations:
			continue

		area = {
			"area": bucket["key"],
			"operation_count": int(operation_count),
			"log_count": bucket["doc_count"],
			"error_count": bucket.get("error_count", {}).get("doc_count", 0),
			"last_activity": bucket.get("last_activity", {}).get("value_as_string")
		}
		areas.append(area)

	return areas
