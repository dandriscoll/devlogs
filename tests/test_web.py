from fastapi.testclient import TestClient
from devlogs.web.server import app

def test_search_endpoint():
    client = TestClient(app)
    resp = client.get("/api/search")
    assert resp.status_code == 200
    assert "results" in resp.json()

def test_ui_served():
    client = TestClient(app)
    resp = client.get("/ui/index.html")
    assert resp.status_code == 200
