"""会话管理接口测试（FR-8/9/12）。"""


def test_session_crud(client, auth_headers):
    # 新建
    resp = client.post("/api/sessions", json={"title": "测试会话"}, headers=auth_headers)
    assert resp.status_code == 200
    sid = resp.json()["id"]

    # 列表
    resp = client.get("/api/sessions", headers=auth_headers)
    assert resp.status_code == 200
    assert any(s["id"] == sid for s in resp.json())

    # 详情（无消息）
    resp = client.get(f"/api/sessions/{sid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["messages"] == []

    # 重命名
    resp = client.patch(f"/api/sessions/{sid}", json={"title": "新名字"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "新名字"

    # 删除
    resp = client.delete(f"/api/sessions/{sid}", headers=auth_headers)
    assert resp.status_code == 200
    assert client.get(f"/api/sessions/{sid}", headers=auth_headers).status_code == 404


def test_session_not_found(client, auth_headers):
    assert client.get("/api/sessions/not-exist", headers=auth_headers).status_code == 404
    assert (
        client.patch("/api/sessions/not-exist", json={"title": "x"}, headers=auth_headers).status_code
        == 404
    )
    assert client.delete("/api/sessions/not-exist", headers=auth_headers).status_code == 404


def test_list_ordered_by_updated_at(client, auth_headers):
    s1 = client.post("/api/sessions", json={"title": "旧"}, headers=auth_headers).json()
    s2 = client.post("/api/sessions", json={"title": "新"}, headers=auth_headers).json()
    ids = [s["id"] for s in client.get("/api/sessions", headers=auth_headers).json()]
    # 后创建的 updated_at 更大，应排前面
    assert ids.index(s2["id"]) < ids.index(s1["id"])


def test_db_schema_endpoint(client, auth_headers):
    resp = client.get("/api/db/schema", headers=auth_headers)
    assert resp.status_code == 200
    tables = {t["table"] for t in resp.json()}
    assert {"customers", "products", "orders"} <= tables
