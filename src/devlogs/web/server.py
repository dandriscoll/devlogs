# Web server API endpoints for devlogs

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from typing import Optional, Tuple
import os

from ..config import load_config
from ..opensearch.client import (
	get_opensearch_client,
	check_connection,
	check_index,
	OpenSearchError,
)
from ..opensearch.queries import search_logs, tail_logs, normalize_log_entries

app = FastAPI()


@app.get("/")
def root():
	return RedirectResponse(url="/ui/")


def _try_client() -> Tuple[Optional[object], Optional[str]]:
	try:
		cfg = load_config()
		client = get_opensearch_client()
		check_connection(client)
		check_index(client, cfg.index)
		return client, None
	except OpenSearchError as exc:
		return None, str(exc)


@app.get("/api/search")
def search(q: Optional[str] = None, area: Optional[str] = None, level: Optional[str] = None, operation_id: Optional[str] = None, since: Optional[str] = None, limit: int = 50):
	client, error = _try_client()
	if not client:
		return {"results": [], "error": error}
	cfg = load_config()
	docs = search_logs(
		client,
		cfg.index,
		query=q,
		area=area,
		operation_id=operation_id,
		level=level,
		since=since,
		limit=limit,
	)
	results = normalize_log_entries(docs, limit=limit)
	return {"results": results}

@app.get("/api/tail")
def tail(operation_id: Optional[str] = None, area: Optional[str] = None, level: Optional[str] = None, since: Optional[str] = None, limit: int = 20):
	client, error = _try_client()
	if not client:
		return {"results": [], "error": error}
	cfg = load_config()
	docs, cursor = tail_logs(
		client,
		cfg.index,
		operation_id=operation_id,
		area=area,
		level=level,
		since=since,
		limit=limit,
	)
	results = normalize_log_entries(docs, limit=limit)
	return {"results": results, "cursor": cursor}

@app.get("/ui/{path:path}")
def serve_ui(path: str):
	static_dir = os.path.join(os.path.dirname(__file__), "static")
	file_path = os.path.join(static_dir, path)
	if not os.path.isfile(file_path):
		file_path = os.path.join(static_dir, "index.html")
	return FileResponse(file_path)
