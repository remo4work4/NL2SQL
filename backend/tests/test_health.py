"""健康检查接口测试（Phase 0 验收）。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "nl2sql-backend"


def test_root_returns_service_info():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "nl2sql-backend"
