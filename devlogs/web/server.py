# Web server API endpoints for devlogs

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from typing import Optional
import os

app = FastAPI()

@app.get("/api/search")
def search(q: Optional[str] = None, area: Optional[str] = None, level: Optional[str] = None, operation_id: Optional[str] = None, since: Optional[str] = None, limit: int = 50):
	# TODO: Call shared query logic
	return {"results": []}

@app.get("/api/tail")
def tail(operation_id: Optional[str] = None, area: Optional[str] = None, level: Optional[str] = None, since: Optional[str] = None, limit: int = 20):
	# TODO: Call shared tail logic
	return {"results": []}

@app.get("/ui/{path:path}")
def serve_ui(path: str):
	static_dir = os.path.join(os.path.dirname(__file__), "static")
	file_path = os.path.join(static_dir, path)
	if not os.path.isfile(file_path):
		file_path = os.path.join(static_dir, "index.html")
	return FileResponse(file_path)
