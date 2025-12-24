# Search APIs for OpenSearch

from typing import Any, Dict, Iterable, List, Optional, Tuple


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
	if level:
		filters.append({"term": {"level": level}})
	if since:
		filters.append({"range": {"timestamp": {"gte": since}}})

	bool_query: Dict[str, Any] = {"filter": filters}
	if query:
		bool_query["must"] = [
			{
				"simple_query_string": {
					"query": query,
					"fields": ["message^2", "logger_name", "operation_id", "area"],
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


def _looks_like_iso(value: str) -> bool:
	return "T" in value and ("Z" in value or "+" in value)


def _parse_rollup_line(line: str) -> Optional[Dict[str, Any]]:
	parts = line.split(" ", 3)
	if len(parts) < 4:
		return None
	timestamp, level, logger_name, message = parts
	if not _looks_like_iso(timestamp):
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
		"level": doc.get("level"),
		"message": doc.get("message"),
		"logger_name": doc.get("logger_name"),
		"area": doc.get("area"),
		"operation_id": doc.get("operation_id"),
		"pathname": doc.get("pathname"),
		"lineno": doc.get("lineno"),
		"exception": doc.get("exception"),
	}


def _is_rollup_doc(doc: Dict[str, Any]) -> bool:
	return bool(doc.get("counts_by_level") or doc.get("start_time") or doc.get("end_time"))


def _expand_doc(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
	doc_type = doc.get("doc_type")
	if doc_type == "operation" and _is_rollup_doc(doc) and doc.get("message"):
		entries: List[Dict[str, Any]] = []
		for line in str(doc.get("message", "")).splitlines():
			parsed = _parse_rollup_line(line.strip())
			if parsed:
				parsed["area"] = doc.get("area")
				parsed["operation_id"] = doc.get("operation_id")
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
	response = client.search(index=index, body=body)
	hits = response.get("hits", {}).get("hits", [])
	return _hits_to_docs(hits)


def tail_logs(client, index, operation_id=None, area=None, level=None, since=None, limit=20, search_after=None):
	"""Tail log entries for an operation."""
	body = {
		"query": _build_log_query(
			area=area,
			operation_id=operation_id,
			level=level,
			since=since,
		),
		"sort": [{"timestamp": "asc"}, {"_id": "asc"}],
		"size": limit,
	}
	if search_after:
		body["search_after"] = search_after
	response = client.search(index=index, body=body)
	hits = response.get("hits", {}).get("hits", [])
	docs = _hits_to_docs(hits)
	next_search_after = docs[-1]["sort"] if docs else search_after
	return docs, next_search_after


def get_operation_summary(client, index, operation_id):
	"""Get summary for an operation."""
	# Stub: build query dict
	return {}
