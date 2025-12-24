# Aggregation/roll-up job for operations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence


def _parse_timestamp(value: Any) -> Optional[datetime]:
	if value is None:
		return None
	if isinstance(value, (int, float)):
		return datetime.fromtimestamp(value, tz=timezone.utc)
	if isinstance(value, str):
		clean = value.replace("Z", "+00:00")
		try:
			return datetime.fromisoformat(clean)
		except ValueError:
			return None
	return None


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
	if dt is None:
		return None
	return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _iter_child_docs(client, index_logs, since: Optional[str] = None) -> Iterable[Dict[str, Any]]:
	query = {"bool": {"filter": [{"term": {"doc_type": "log_entry"}}]}}
	if since:
		query["bool"]["filter"].append({"range": {"timestamp": {"gte": since}}})
	body = {
		"query": query,
		"sort": [{"timestamp": "asc"}, {"_id": "asc"}],
		"size": 500,
	}
	search_after = None
	while True:
		if search_after:
			body["search_after"] = search_after
		response = client.search(index=index_logs, body=body)
		hits = response.get("hits", {}).get("hits", [])
		if not hits:
			break
		for hit in hits:
			yield hit
		search_after = hits[-1].get("sort")


def _format_rollup_line(doc: Dict[str, Any]) -> str:
	timestamp = doc.get("timestamp") or ""
	level = doc.get("level") or ""
	logger_name = doc.get("logger_name") or ""
	message = doc.get("message") or ""
	line = f"{timestamp} {level} {logger_name} {message}".strip()
	return line


def _collect_child_docs(
	client,
	index_logs,
	operation_id: str,
	batch_size: int = 500,
) -> List[Dict[str, Any]]:
	body = {
		"query": {
			"bool": {
				"filter": [
					{"term": {"doc_type": "log_entry"}},
					{"term": {"operation_id": operation_id}},
				]
			}
		},
		"sort": [{"timestamp": "asc"}, {"_id": "asc"}],
		"size": batch_size,
	}
	search_after = None
	docs: List[Dict[str, Any]] = []
	while True:
		if search_after:
			body["search_after"] = search_after
		response = client.search(index=index_logs, body=body)
		hits = response.get("hits", {}).get("hits", [])
		if not hits:
			break
		for hit in hits:
			source = hit.get("_source", {})
			if source:
				docs.append(source)
		search_after = hits[-1].get("sort")
	return docs


def _summarize_docs(docs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
	counts_by_level: Dict[str, int] = {}
	error_count = 0
	start_time = None
	end_time = None
	last_message = None
	area = None
	lines: List[str] = []

	for doc in docs:
		level = doc.get("level")
		if level:
			counts_by_level[level] = counts_by_level.get(level, 0) + 1
			if level.upper() in ("ERROR", "CRITICAL"):
				error_count += 1
		doc_area = doc.get("area")
		if doc_area and area is None:
			area = doc_area

		ts = _parse_timestamp(doc.get("timestamp"))
		if ts:
			if start_time is None or ts < start_time:
				start_time = ts
			if end_time is None or ts > end_time:
				end_time = ts
				last_message = doc.get("message")
		lines.append(_format_rollup_line(doc))

	rollup_message = "\n".join(line for line in lines if line)
	return {
		"area": area,
		"start_time": _to_iso(start_time),
		"end_time": _to_iso(end_time),
		"counts_by_level": counts_by_level,
		"error_count": error_count,
		"last_message": last_message,
		"message": rollup_message or None,
		"timestamp": _to_iso(end_time or start_time),
	}


def rollup_operation(client, index_logs, operation_id: str, refresh: bool = False) -> bool:
	"""Aggregate child docs for a single operation into a parent, then delete children."""
	if refresh:
		try:
			client.indices.refresh(index=index_logs)
		except Exception:
			pass
	docs = _collect_child_docs(client, index_logs, operation_id)
	if not docs:
		return False
	summary = _summarize_docs(docs)
	parent_doc = {
		"doc_type": "operation",
		"operation_id": operation_id,
		**summary,
	}

	client.index(
		index=index_logs,
		id=operation_id,
		body=parent_doc,
		routing=operation_id,
		refresh=False,
	)

	client.delete_by_query(
		index=index_logs,
		body={
			"query": {
				"bool": {
					"filter": [
						{"term": {"doc_type": "log_entry"}},
						{"term": {"operation_id": operation_id}},
					]
				}
			}
		},
		routing=operation_id,
		refresh=False,
		conflicts="proceed",
		slices="auto",
	)
	return True


def rollup_operations(client, index_logs, since=None):
	"""Aggregate log entry children into parent operation docs, then delete children."""
	operations = set()
	for hit in _iter_child_docs(client, index_logs, since=since):
		source = hit.get("_source", {})
		operation_id = source.get("operation_id")
		if operation_id:
			operations.add(operation_id)

	for operation_id in sorted(operations):
		rollup_operation(client, index_logs, operation_id)
