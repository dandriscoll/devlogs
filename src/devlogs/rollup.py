# Aggregation/roll-up job for operations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence
from .levels import normalize_level


def _normalize_operation_id(value: Any) -> Optional[str]:
	if value is None:
		return None
	if isinstance(value, str):
		value = value.strip()
		return value or None
	try:
		text = str(value).strip()
	except Exception:
		return None
	return text or None


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

def _collect_all_child_docs(client, index_logs, since: Optional[str] = None) -> List[Dict[str, Any]]:
	docs: List[Dict[str, Any]] = []
	for hit in _iter_child_docs(client, index_logs, since=since):
		source = hit.get("_source", {})
		if source:
			docs.append(source)
	return docs

def _build_parent_map(docs: Sequence[Dict[str, Any]]) -> Dict[str, str]:
	parent_map: Dict[str, str] = {}
	for doc in docs:
		operation_id = _normalize_operation_id(doc.get("operation_id"))
		parent_operation_id = _normalize_operation_id(doc.get("parent_operation_id"))
		if operation_id and parent_operation_id and operation_id not in parent_map:
			parent_map[operation_id] = parent_operation_id
	return parent_map

def _resolve_root(operation_id: Optional[str], parent_map: Dict[str, str]) -> Optional[str]:
	if not operation_id:
		return None
	current = operation_id
	seen = set()
	while current in parent_map and current not in seen:
		seen.add(current)
		current = parent_map[current]
	return current

def _group_child_docs(docs: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
	parent_map = _build_parent_map(docs)
	groups: Dict[str, Dict[str, Any]] = {}
	for doc in docs:
		operation_id = _normalize_operation_id(doc.get("operation_id"))
		if not operation_id:
			continue
		root_id = _resolve_root(operation_id, parent_map) or operation_id
		group = groups.setdefault(root_id, {"docs": [], "operation_ids": set()})
		group["docs"].append(doc)
		group["operation_ids"].add(operation_id)
	return groups


def _format_rollup_line(doc: Dict[str, Any]) -> str:
	timestamp = doc.get("timestamp") or ""
	level = normalize_level(doc.get("level")) or ""
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


def _summarize_docs(docs: Sequence[Dict[str, Any]], root_operation_id: Optional[str] = None) -> Dict[str, Any]:
	counts_by_level: Dict[str, int] = {}
	error_count = 0
	start_time = None
	end_time = None
	last_message = None
	area = None
	parent_operation_id = None
	root_area = None
	lines: List[str] = []

	for doc in docs:
		level = normalize_level(doc.get("level"))
		if level:
			counts_by_level[level] = counts_by_level.get(level, 0) + 1
			if level in ("error", "critical"):
				error_count += 1
		doc_area = doc.get("area")
		if doc_area and area is None:
			area = doc_area
		doc_operation_id = _normalize_operation_id(doc.get("operation_id"))
		if root_operation_id and doc_operation_id == root_operation_id:
			if doc_area and root_area is None:
				root_area = doc_area
			doc_parent = _normalize_operation_id(doc.get("parent_operation_id"))
			if doc_parent is not None and parent_operation_id is None:
				parent_operation_id = doc_parent

		ts = _parse_timestamp(doc.get("timestamp"))
		if ts:
			if start_time is None or ts < start_time:
				start_time = ts
			if end_time is None or ts > end_time:
				end_time = ts
				last_message = doc.get("message")
		lines.append(_format_rollup_line(doc))

	rollup_message = "\n".join(line for line in lines if line)
	if root_area:
		area = root_area
	result = {
		"area": area,
		"start_time": _to_iso(start_time),
		"end_time": _to_iso(end_time),
		"counts_by_level": counts_by_level,
		"error_count": error_count,
		"last_message": last_message,
		"message": rollup_message or None,
		"timestamp": _to_iso(end_time or start_time),
	}
	if parent_operation_id:
		result["parent_operation_id"] = parent_operation_id
	return result


def _compact_child_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
	return {
		"timestamp": doc.get("timestamp"),
		"level": normalize_level(doc.get("level")),
		"logger_name": doc.get("logger_name"),
		"message": doc.get("message"),
		"area": doc.get("area"),
		"operation_id": _normalize_operation_id(doc.get("operation_id")),
		"parent_operation_id": _normalize_operation_id(doc.get("parent_operation_id")),
		"pathname": doc.get("pathname"),
		"lineno": doc.get("lineno"),
		"exception": doc.get("exception"),
		"features": doc.get("features"),
	}


def _rollup_group(client, index_logs, root_id: str, docs: Sequence[Dict[str, Any]], operation_ids: Sequence[str]) -> int:
	if not docs:
		return 0
	summary = _summarize_docs(docs, root_operation_id=root_id)
	entries = [_compact_child_doc(doc) for doc in docs]
	parent_doc = {
		"doc_type": "operation",
		"operation_id": root_id,
		"entries": entries,
		**summary,
	}

	client.index(
		index=index_logs,
		id=root_id,
		body=parent_doc,
		routing=root_id,
		refresh=False,
	)

	if operation_ids:
		client.delete_by_query(
			index=index_logs,
			body={
				"query": {
					"bool": {
						"filter": [
							{"term": {"doc_type": "log_entry"}},
							{"terms": {"operation_id": list(operation_ids)}},
						]
					}
				}
			},
			refresh=False,
			conflicts="proceed",
			slices="auto",
		)
	return len(docs)


def rollup_operation(client, index_logs, operation_id: str, refresh: bool = False) -> int:
	"""Aggregate child docs for the root operation, then delete children."""
	if refresh:
		try:
			client.indices.refresh(index=index_logs)
		except Exception:
			pass
	operation_id = _normalize_operation_id(operation_id)
	if not operation_id:
		return 0
	docs = _collect_all_child_docs(client, index_logs)
	if not docs:
		return 0
	parent_map = _build_parent_map(docs)
	root_id = _resolve_root(operation_id, parent_map) or operation_id
	groups = _group_child_docs(docs)
	group = groups.get(root_id)
	if not group:
		return 0
	operation_ids = sorted(group["operation_ids"])
	return _rollup_group(client, index_logs, root_id, group["docs"], operation_ids)


def rollup_operations(client, index_logs, since=None):
	"""Aggregate log entry children into parent operation docs, then delete children."""
	docs = _collect_all_child_docs(client, index_logs, since=since)
	if not docs:
		return 0, 0
	groups = _group_child_docs(docs)

	child_total = 0
	parent_total = 0
	for root_id in sorted(groups.keys()):
		group = groups[root_id]
		operation_ids = sorted(group["operation_ids"])
		rolled_children = _rollup_group(client, index_logs, root_id, group["docs"], operation_ids)
		if rolled_children:
			parent_total += 1
			child_total += rolled_children
	return child_total, parent_total
