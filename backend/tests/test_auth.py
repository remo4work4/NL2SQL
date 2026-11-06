"""认证接口测试（FR-15）。"""


def test_login_success(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "admin"
    assert body["token"]


def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401
    assert "用户名或密码错误" in resp.json()["detail"]


def test_login_unknown_user(client):
    resp = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert resp.status_code == 401


def test_me_with_token(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


def test_me_without_token_401(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_bad_token_401(client):
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer fake"}).status_code == 401


def test_logout_invalidates_token(client, auth_headers):
    resp = client.post("/api/auth/logout", headers=auth_headers)
    assert resp.status_code == 200
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 401


def test_protected_routes_require_token(client):
    assert client.get("/api/sessions").status_code == 401
    assert client.get("/api/db/schema").status_code == 401
    assert client.post("/api/chat", json={"message": "你好"}).status_code == 401
