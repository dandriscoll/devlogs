# Aggregation/roll-up job for operations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


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
	response = client.search(
		index=index_logs,
		body={
			"query": query,
			"sort": [{"timestamp": "asc"}, {"_id": "asc"}],
			"size": 500,
		},
		scroll="1m",
	)
	scroll_id = response.get("_scroll_id")
	hits = response.get("hits", {}).get("hits", [])
	while hits:
		for hit in hits:
			yield hit
		response = client.scroll(scroll_id=scroll_id, scroll="1m")
		scroll_id = response.get("_scroll_id")
		hits = response.get("hits", {}).get("hits", [])
	if scroll_id:
		client.clear_scroll(scroll_id=scroll_id)


def rollup_operations(client, index_logs, since=None):
	"""Aggregate log entry children into parent operation docs, then delete children."""
	by_operation: Dict[str, List[Dict[str, Any]]] = {}
	for hit in _iter_child_docs(client, index_logs, since=since):
		source = hit.get("_source", {})
		operation_id = source.get("operation_id")
		if not operation_id:
			continue
		by_operation.setdefault(operation_id, []).append(source)

	for operation_id, docs in by_operation.items():
		counts_by_level: Dict[str, int] = {}
		error_count = 0
		start_time = None
		end_time = None
		last_message = None
		area = None

		for doc in docs:
			level = doc.get("level")
			if level:
				counts_by_level[level] = counts_by_level.get(level, 0) + 1
				if level.upper() == "ERROR":
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

		parent_doc = {
			"doc_type": "operation",
			"operation_id": operation_id,
			"area": area,
			"start_time": _to_iso(start_time),
			"end_time": _to_iso(end_time),
			"counts_by_level": counts_by_level,
			"error_count": error_count,
			"last_message": last_message,
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
