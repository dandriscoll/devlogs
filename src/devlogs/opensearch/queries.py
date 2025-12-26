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
					{"term": {"doc_type": "operation"}},
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
							"parent_operation_id",
							"area",
							"features.*",
						],
						"default_operator": "and",
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


def _looks_like_iso(value: str) -> bool:
	return "T" in value and ("Z" in value or "+" in value)


def _parse_rollup_line(line: str) -> Optional[Dict[str, Any]]:
	parts = line.split(" ", 3)
	if len(parts) < 4:
		return None
	timestamp, level, logger_name, message = parts
	level = normalize_level(level)
	if not _looks_like_iso(timestamp):
		return None
	if not level:
		return None
	return {
		"timestamp": timestamp,
		"level": level,
		"logger_name": logger_name,
		"message": message,
	}


def _normalize_entry(doc: Dict[str, Any]) -> Dict[str, Any]:
	return {
		"timestamp": doc.get("timestamp"),
		"level": normalize_level(doc.get("level")),
		"message": doc.get("message"),
		"logger_name": doc.get("logger_name"),
		"area": doc.get("area"),
		"operation_id": doc.get("operation_id"),
		"parent_operation_id": doc.get("parent_operation_id"),
		"pathname": doc.get("pathname"),
		"lineno": doc.get("lineno"),
		"exception": doc.get("exception"),
		"features": doc.get("features"),
	}


def _is_rollup_doc(doc: Dict[str, Any]) -> bool:
	return bool(doc.get("entries") or doc.get("counts_by_level") or doc.get("start_time") or doc.get("end_time"))


def _expand_doc(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
	doc_type = doc.get("doc_type")
	if doc_type == "operation" and doc.get("entries"):
		entries: List[Dict[str, Any]] = []
		for entry in doc.get("entries", []):
			normalized = _normalize_entry(entry)
			if not normalized.get("area"):
				normalized["area"] = doc.get("area")
			if not normalized.get("operation_id"):
				normalized["operation_id"] = doc.get("operation_id")
			if not normalized.get("parent_operation_id"):
				normalized["parent_operation_id"] = doc.get("parent_operation_id")
			entries.append(normalized)
		return entries
	if doc_type == "operation" and _is_rollup_doc(doc) and doc.get("message"):
		entries: List[Dict[str, Any]] = []
		for line in str(doc.get("message", "")).splitlines():
			parsed = _parse_rollup_line(line.strip())
			if parsed:
				parsed["area"] = doc.get("area")
				parsed["operation_id"] = doc.get("operation_id")
				parsed["parent_operation_id"] = doc.get("parent_operation_id")
				parsed["pathname"] = None
				parsed["lineno"] = None
				parsed["exception"] = None
				entries.append(parsed)
			elif line.strip():
				entry = _normalize_entry(doc)
				entry["message"] = line.strip()
				entries.append(entry)
		return entries
	return [_normalize_entry(doc)]


def normalize_log_entries(docs: Iterable[Dict[str, Any]], limit: Optional[int] = None) -> List[Dict[str, Any]]:
	entries: List[Dict[str, Any]] = []
	for doc in docs:
		entries.extend(_expand_doc(doc))
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

	On initial call (no search_after): fetches the most recent logs in descending order,
	then reverses them for chronological display.
	On subsequent calls: continues forward from the cursor in ascending order.
	"""
	is_initial = search_after is None
	body = {
		"query": _build_log_query(
			query=query,
			area=area,
			operation_id=operation_id,
			level=level,
			since=since,
		),
		"sort": [{"timestamp": "desc" if is_initial else "asc"}, {"_id": "desc" if is_initial else "asc"}],
		"size": limit,
	}
	if search_after:
		body["search_after"] = search_after
	response = _require_response(client.search(index=index, body=body), "tail", client=client, index=index)
	hits = response.get("hits", {}).get("hits", [])
	docs = _hits_to_docs(hits)

	if is_initial and docs:
		# Reverse to chronological order for display, use the last (most recent) as cursor
		docs = list(reversed(docs))
		next_search_after = docs[-1]["sort"]
	else:
		next_search_after = docs[-1]["sort"] if docs else search_after

	return docs, next_search_after


def get_operation_summary(client, index, operation_id):
	"""Get summary for an operation."""
	# Stub: build query dict
	return {}
