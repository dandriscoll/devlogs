import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from types import SimpleNamespace

from devlogs.web import server


def _set_client_ready(monkeypatch, index_name="devlogs-test"):
	monkeypatch.setattr(server, "_try_client", lambda: (object(), None))
	monkeypatch.setattr(server, "load_config", lambda: SimpleNamespace(index_logs=index_name))

def test_search_endpoint(monkeypatch):
	_set_client_ready(monkeypatch)
	monkeypatch.setattr(server, "search_logs", lambda *args, **kwargs: [])
	client = TestClient(server.app)
	resp = client.get("/api/search")
	assert resp.status_code == 200
	assert resp.json()["results"] == []

def test_ui_served():
	client = TestClient(server.app)
	resp = client.get("/ui/index.html")
	assert resp.status_code == 200


def test_search_returns_flat_docs(monkeypatch):
	_set_client_ready(monkeypatch)
	flat_doc = {
		"doc_type": "log_entry",
		"operation_id": "op-2",
		"area": "jobs",
		"timestamp": "2024-02-01T09:30:00Z",
		"level": "info",
		"logger_name": "svc",
		"message": "hello",
		"pathname": "worker.py",
		"lineno": 12,
		"exception": None,
	}

	monkeypatch.setattr(server, "search_logs", lambda *args, **kwargs: [flat_doc])
	client = TestClient(server.app)
	resp = client.get("/api/search?operation_id=op-2")
	assert resp.status_code == 200
	results = resp.json()["results"]
	assert len(results) == 1
	assert results[0]["operation_id"] == "op-2"
	assert results[0]["message"] == "hello"
	assert results[0]["logger_name"] == "svc"


def test_tail_endpoint_returns_cursor(monkeypatch):
	_set_client_ready(monkeypatch)
	flat_doc = {
		"doc_type": "log_entry",
		"operation_id": "op-3",
		"area": "api",
		"timestamp": "2024-02-01T09:40:00Z",
		"level": "warning",
		"logger_name": "svc",
		"message": "slow response",
	}
	monkeypatch.setattr(server, "tail_logs", lambda *args, **kwargs: ([flat_doc], ["2024-02-01T09:40:00Z", "x"]))
	client = TestClient(server.app)
	resp = client.get("/api/tail?operation_id=op-3")
	assert resp.status_code == 200
	data = resp.json()
	assert data["cursor"] == ["2024-02-01T09:40:00Z", "x"]
	assert len(data["results"]) == 1
	assert data["results"][0]["message"] == "slow response"


def test_search_returns_error_when_unavailable(monkeypatch):
	monkeypatch.setattr(server, "_try_client", lambda: (None, "offline"))
	client = TestClient(server.app)
	resp = client.get("/api/search")
	assert resp.status_code == 200
	data = resp.json()
	assert data["results"] == []
	assert data["error"] == "offline"
