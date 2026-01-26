# Search APIs for OpenSearch

from typing import Any, Dict, Iterable, List, Optional

from ..time_utils import resolve_relative_time
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


def _build_time_range(since: Optional[str], until: Optional[str], since_inclusive: bool, until_inclusive: bool) -> Optional[Dict[str, Any]]:
	if not since and not until:
		return None
	since = resolve_relative_time(since)
	until = resolve_relative_time(until)
	range_query: Dict[str, Any] = {}
	if since:
		range_query["gte" if since_inclusive else "gt"] = since
	if until:
		range_query["lte" if until_inclusive else "lt"] = until
	return {"range": {"timestamp": range_query}}


def _build_log_query(query=None, area=None, operation_id=None, level=None, since=None, until=None, since_inclusive: bool = True, until_inclusive: bool = True):
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
	time_range = _build_time_range(since, until, since_inclusive, until_inclusive)
	if time_range:
		filters.append(time_range)

	bool_query: Dict[str, Any] = {"filter": filters}
	if query:
		bool_query["must"] = [
			{
					"simple_query_string": {
						"query": query,
						"fields": [
							"message^2",
							"logger",
							"operation_id",
							"area",
							"fields.*",
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
		"logger": doc.get("logger"),
		"area": doc.get("area"),
		"operation_id": doc.get("operation_id"),
		"pathname": doc.get("pathname"),
		"lineno": doc.get("lineno"),
		"exception": doc.get("exception"),
		"fields": doc.get("fields"),
	}


def normalize_log_entries(docs: Iterable[Dict[str, Any]], limit: Optional[int] = None) -> List[Dict[str, Any]]:
	"""Normalize log entries from OpenSearch documents."""
	entries: List[Dict[str, Any]] = []
	for doc in docs:
		entries.append(_normalize_entry(doc))
		if limit is not None and len(entries) >= limit:
			return entries[:limit]
	return entries


def search_logs(client, index, query=None, area=None, operation_id=None, level=None, since=None, until=None, limit=50):
	"""Search log entries with filters."""
	body = {
		"query": _build_log_query(
			query=query,
			area=area,
			operation_id=operation_id,
			level=level,
			since=since,
			until=until,
		),
		"sort": [{"timestamp": "desc"}, {"_id": "desc"}],
		"size": limit,
	}
	response = _require_response(client.search(index=index, body=body), "search", client=client, index=index)
	hits = response.get("hits", {}).get("hits", [])
	return _hits_to_docs(hits)


def get_last_errors(client, index, query=None, area=None, operation_id=None, since=None, until=None, limit=1):
	"""Get the most recent error/critical log entries."""
	base_query = _build_log_query(
		query=query,
		area=area,
		operation_id=operation_id,
		since=since,
		until=until,
	)
	base_query.get("bool", {}).get("filter", []).append(
		{"terms": {"level": ["error", "critical"]}}
	)
	body = {
		"query": base_query,
		"sort": [{"timestamp": "desc"}, {"_id": "desc"}],
		"size": limit,
	}
	response = _require_response(client.search(index=index, body=body), "get_last_errors", client=client, index=index)
	hits = response.get("hits", {}).get("hits", [])
	return _hits_to_docs(hits)


def _build_sort(sort_order: str) -> List[Dict[str, str]]:
	order = "asc" if sort_order == "asc" else "desc"
	return [{"timestamp": order}, {"_id": order}]


def search_logs_page(
	client,
	index,
	query=None,
	area=None,
	operation_id=None,
	level=None,
	since=None,
	until=None,
	limit=50,
	cursor=None,
	sort_order: str = "desc",
	since_inclusive: bool = True,
	until_inclusive: bool = True,
):
	"""Search log entries with pagination support."""
	body = {
		"query": _build_log_query(
			query=query,
			area=area,
			operation_id=operation_id,
			level=level,
			since=since,
			until=until,
			since_inclusive=since_inclusive,
			until_inclusive=until_inclusive,
		),
		"sort": _build_sort(sort_order),
		"size": limit,
	}
	if cursor:
		body["search_after"] = cursor
	response = _require_response(client.search(index=index, body=body), "search", client=client, index=index)
	hits = response.get("hits", {}).get("hits", [])
	docs = _hits_to_docs(hits)
	next_cursor = docs[-1]["sort"] if docs else cursor
	return docs, next_cursor


def get_operation_logs(client, index, operation_id, query=None, level=None, since=None, until=None, limit=100, cursor=None):
	"""Get logs for an operation in chronological order."""
	return search_logs_page(
		client=client,
		index=index,
		query=query,
		operation_id=operation_id,
		level=level,
		since=since,
		until=until,
		limit=limit,
		cursor=cursor,
		sort_order="asc",
	)


def tail_logs(client, index, query=None, operation_id=None, area=None, level=None, since=None, until=None, limit=20, search_after=None):
	"""Tail log entries for an operation.

	First call returns the most recent entries (newest first) and reverses for chronological display.
	Follow-up calls with search_after return only newer entries in ascending order.
	"""
	base_body = {
		"query": _build_log_query(
			query=query,
			area=area,
			operation_id=operation_id,
			level=level,
			since=since,
			until=until,
		),
		"size": limit,
	}

	if search_after:
		body = dict(base_body)
		body["sort"] = [{"timestamp": "asc"}, {"_id": "asc"}]
		body["search_after"] = search_after
		response = _require_response(client.search(index=index, body=body), "tail", client=client, index=index)
		hits = response.get("hits", {}).get("hits", [])
		docs = _hits_to_docs(hits)
		next_search_after = docs[-1]["sort"] if docs else search_after
		return docs, next_search_after

	body = dict(base_body)
	body["sort"] = [{"timestamp": "desc"}, {"_id": "desc"}]
	response = _require_response(client.search(index=index, body=body), "tail", client=client, index=index)
	hits = response.get("hits", {}).get("hits", [])
	docs = _hits_to_docs(hits)

	if docs:
		# Fetch is in DESC order (newest first)
		# Cursor points to newest fetched (first in DESC list) for follow-up polling
		next_search_after = docs[0]["sort"]
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
					"_source": [
						"timestamp",
						"level",
						"message",
						"logger",
						"exception",
						"fields",
						"operation_id",
						"area",
						"pathname",
						"lineno",
					]
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
		normalized_since = resolve_relative_time(since)
		query_filters.append({"range": {"timestamp": {"gte": normalized_since}}})

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


def list_recent_operations(client, index, area=None, since=None, until=None, limit=20, order_by: str = "last_activity", with_errors_only: bool = False):
	"""List recent operations ordered by last activity or error count."""
	base_query = _build_log_query(area=area, since=since, until=until)
	if order_by not in ("last_activity", "error_count"):
		order_by = "last_activity"

	body = {
		"query": base_query,
		"size": 0,
		"aggs": {
			"by_operation": {
				"terms": {"field": "operation_id", "size": limit, "order": {order_by: "desc"}},
				"aggs": {
					"area": {"terms": {"field": "area", "size": 1}},
					"time_range": {"stats": {"field": "timestamp"}},
					"by_level": {"terms": {"field": "level", "size": 10}},
					"error_count": {
						"filter": {
							"terms": {"level": ["error", "critical"]}
						}
					},
					"last_activity": {
						"max": {"field": "timestamp"}
					},
					"last_error": {
						"filter": {
							"terms": {"level": ["error", "critical"]}
						},
						"aggs": {
							"last_error_hit": {
								"top_hits": {
									"size": 1,
									"sort": [{"timestamp": "desc"}, {"_id": "desc"}],
									"_source": [
										"timestamp",
										"level",
										"message",
										"logger",
										"exception",
										"operation_id",
										"area",
										"pathname",
										"lineno",
									],
								}
							}
						}
					},
				}
			}
		}
	}

	try:
		response = _require_response(client.search(index=index, body=body), "list_recent_operations", client=client, index=index)
	except Exception:
		return []

	operations = []
	for bucket in response.get("aggregations", {}).get("by_operation", {}).get("buckets", []):
		area_buckets = bucket.get("area", {}).get("buckets", [])
		op_area = area_buckets[0]["key"] if area_buckets else None

		time_stats = bucket.get("time_range", {})
		start_time = time_stats.get("min_as_string")
		end_time = time_stats.get("max_as_string")

		duration_ms = None
		if time_stats.get("min") and time_stats.get("max"):
			duration_ms = int(time_stats["max"] - time_stats["min"])

		counts_by_level = {}
		for level_bucket in bucket.get("by_level", {}).get("buckets", []):
			counts_by_level[level_bucket["key"]] = level_bucket["doc_count"]

		error_count = bucket.get("error_count", {}).get("doc_count", 0)
		last_activity = bucket.get("last_activity", {}).get("value_as_string")

		last_error_hit = (
			bucket.get("last_error", {})
			.get("last_error_hit", {})
			.get("hits", {})
			.get("hits", [])
		)
		last_error = last_error_hit[0].get("_source") if last_error_hit else None

		op = {
			"operation_id": bucket["key"],
			"area": op_area,
			"start_time": start_time,
			"end_time": end_time,
			"duration_ms": duration_ms,
			"total_logs": bucket["doc_count"],
			"error_count": error_count,
			"log_levels": counts_by_level,
			"last_activity": last_activity,
			"last_error": last_error,
		}
		operations.append(op)

	if with_errors_only:
		operations = [op for op in operations if op["error_count"] > 0]

	return operations


def list_error_signatures(
	client,
	index,
	field: str = "exception",
	area=None,
	since=None,
	until=None,
	limit=20,
	min_count: int = 1,
	include_missing: bool = False,
):
	"""Aggregate error signatures by exception/message."""
	if not field:
		field = "exception"
	field_name = field if field.endswith(".keyword") else f"{field}.keyword"

	base_query = _build_log_query(area=area, since=since, until=until)
	base_filters = base_query.get("bool", {}).get("filter", [])
	base_filters.append({"terms": {"level": ["error", "critical"]}})
	if not include_missing:
		base_filters.append({"exists": {"field": field}})

	body = {
		"query": base_query,
		"size": 0,
		"aggs": {
			"by_signature": {
				"terms": {"field": field_name, "size": limit, "min_doc_count": min_count},
				"aggs": {
					"last_seen": {"max": {"field": "timestamp"}},
					"sample": {
						"top_hits": {
							"size": 1,
							"sort": [{"timestamp": "desc"}, {"_id": "desc"}],
							"_source": [
								"timestamp",
								"level",
								"message",
								"logger",
								"exception",
								"operation_id",
								"area",
								"pathname",
								"lineno",
							],
						}
					},
				}
			}
		}
	}

	try:
		response = _require_response(client.search(index=index, body=body), "list_error_signatures", client=client, index=index)
	except Exception:
		return []

	signatures = []
	for bucket in response.get("aggregations", {}).get("by_signature", {}).get("buckets", []):
		sample_hit = bucket.get("sample", {}).get("hits", {}).get("hits", [])
		sample = sample_hit[0].get("_source") if sample_hit else None
		signatures.append({
			"signature": bucket.get("key"),
			"count": bucket.get("doc_count", 0),
			"last_seen": bucket.get("last_seen", {}).get("value_as_string"),
			"sample": sample,
		})

	return signatures


def get_error_context(
	client,
	index,
	anchor_timestamp: str,
	operation_id=None,
	area=None,
	query=None,
	level=None,
	before: int = 20,
	after: int = 20,
):
	"""Fetch logs around an anchor timestamp."""
	before_count = max(int(before or 0), 0)
	after_count = max(int(after or 0), 0)
	before_limit = before_count + 1 if before_count >= 0 else 1

	before_docs, _ = search_logs_page(
		client=client,
		index=index,
		query=query,
		area=area,
		operation_id=operation_id,
		level=level,
		until=anchor_timestamp,
		limit=before_limit,
		sort_order="desc",
		until_inclusive=True,
	)
	after_docs, _ = search_logs_page(
		client=client,
		index=index,
		query=query,
		area=area,
		operation_id=operation_id,
		level=level,
		since=anchor_timestamp,
		limit=after_count,
		sort_order="asc",
		since_inclusive=False,
	)
	before_docs = list(reversed(before_docs))

	return before_docs + after_docs


def list_areas(client, index, since=None, min_operations=1):
	"""List all application areas with activity counts."""
	query_filters = []
	if since:
		normalized_since = resolve_relative_time(since)
		query_filters.append({"range": {"timestamp": {"gte": normalized_since}}})

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
