"""FR-21 多用户测试：注册、重复用户名校验、会话/消息 A/B 隔离、未登录 401。"""
import pytest


def _register(client, username: str, password: str):
    return client.post("/api/auth/register", json={"username": username, "password": password})


def _headers(resp) -> dict:
    return {"Authorization": f"Bearer {resp.json()['token']}"}


class TestRegister:
    def test_register_and_login(self, client):
        resp = _register(client, "alice", "alice123")
        assert resp.status_code == 200
        me = client.get("/api/auth/me", headers=_headers(resp))
        assert me.status_code == 200 and me.json()["username"] == "alice"

    def test_duplicate_username_conflict(self, client):
        assert _register(client, "bob", "bob1234").status_code == 200
        resp = _register(client, "bob", "otherpass")
        assert resp.status_code == 409
        assert "已存在" in resp.json()["detail"]

    def test_weak_password_rejected(self, client):
        # pydantic 层校验（422）或服务层校验（400）均为拒绝
        assert _register(client, "carol", "123").status_code in (400, 422)

    def test_admin_still_works(self, client, auth_headers):
        me = client.get("/api/auth/me", headers=auth_headers)
        assert me.json()["username"] == "admin"


class TestIsolation:
    def test_sessions_isolated_between_users(self, client):
        ha = _headers(_register(client, "userA", "passA123"))
        hb = _headers(_register(client, "userB", "passB123"))

        # A 建会话并发问（走意图规则快路径，无 LLM 依赖）
        sa = client.post("/api/sessions", json={}, headers=ha).json()
        assert client.post(f"/api/sessions/{sa['id']}/chat", json={"message": "你好"}, headers=ha).status_code == 200

        # B 的会话列表为空（看不到 A 的会话）
        assert client.get("/api/sessions", headers=hb).json() == []

        # B 对 A 的会话：读/改名/删/对话 全部 404（不泄露存在性）
        assert client.get(f"/api/sessions/{sa['id']}", headers=hb).status_code == 404
        assert client.patch(f"/api/sessions/{sa['id']}", json={"title": "改名"}, headers=hb).status_code == 404
        assert client.delete(f"/api/sessions/{sa['id']}", headers=hb).status_code == 404
        assert client.post(f"/api/sessions/{sa['id']}/chat", json={"message": "你好"}, headers=hb).status_code == 404

        # A 自己可见可操作
        detail = client.get(f"/api/sessions/{sa['id']}", headers=ha)
        assert detail.status_code == 200 and len(detail.json()["messages"]) == 2
        assert client.patch(f"/api/sessions/{sa['id']}", json={"title": "A的会话"}, headers=ha).status_code == 200

    def test_unauthenticated_401(self, client):
        assert client.get("/api/sessions").status_code == 401
        assert client.post("/api/chat", json={"message": "你好"}).status_code == 401
        assert client.get("/api/db/schema").status_code == 401
