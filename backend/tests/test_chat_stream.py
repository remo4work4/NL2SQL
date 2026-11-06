"""对话 SSE 流测试（协议 7.2 节；NL2SQL 生成用 monkeypatch 替换，不打真实 LLM）。

并行双流架构：解读文本由 stream_answer 流式产出，SQL 由 generate_nl2sql 结构化产出。
"""
import json

from app.agent.nl2sql import ChartSpec, LLMError, NL2SQLResult

GOOD = NL2SQLResult(
    sql="SELECT substr(order_date, 1, 7) AS month, SUM(amount) AS sales "
    "FROM orders GROUP BY month ORDER BY month",
    answer="",
    chart=ChartSpec(chart_type="line", title="月度趋势", x="month", y=["sales"]),
)

GOOD_ANSWER = "全年销售额合计 X 万元，12 月最高。"


def patch_agent(monkeypatch, generate, stream_text=GOOD_ANSWER):
    """打桩：generate_nl2sql + stream_answer。"""
    monkeypatch.setattr("app.agent.nl2sql.generate_nl2sql", generate)

    async def fake_stream(schema_digest, history, question):
        yield stream_text

    monkeypatch.setattr("app.agent.nl2sql.stream_answer", fake_stream)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    text = text.replace("\r\n", "\n")  # SSE 规范行分隔为 \r\n
    for block in text.split("\n\n"):
        lines = block.strip().split("\n")
        event = next((l.split(": ", 1)[1] for l in lines if l.startswith("event:")), None)
        data = "\n".join(l.split(": ", 1)[1] for l in lines if l.startswith("data:"))
        if event and data:
            events.append((event, json.loads(data)))
    return events


def _chat(client, auth_headers, question, sid=None):
    url = f"/api/sessions/{sid}/chat" if sid else "/api/chat"
    return client.post(url, json={"message": question}, headers=auth_headers)


def test_chat_stream_happy_path(client, auth_headers, monkeypatch):
    async def fake_generate(schema_digest, history, question, hint="", use_json_mode=True):
        return GOOD

    patch_agent(monkeypatch, fake_generate)

    resp = _chat(client, auth_headers, "2025 年各月销售额趋势")
    assert resp.status_code == 200, resp.text
    events = parse_sse(resp.text)
    kinds = [e for e, _ in events]

    # 协议顺序：answer* → sql → result → chart → done
    assert "answer" in kinds
    assert kinds.index("sql") < kinds.index("result") < kinds.index("chart") < kinds.index("done")
    assert "error" not in kinds

    answer = "".join(d["delta"] for e, d in events if e == "answer")
    assert answer == GOOD_ANSWER

    sql_event = next(d for e, d in events if e == "sql")
    assert "SELECT" in sql_event["sql"]

    result_event = next(d for e, d in events if e == "result")
    assert result_event["columns"] == ["month", "sales"]
    assert result_event["row_count"] > 0

    chart_event = next(d for e, d in events if e == "chart")
    assert chart_event["chart_type"] == "line"


def test_chat_persists_messages(client, auth_headers, monkeypatch):
    async def fake_generate(*args, **kwargs):
        return GOOD

    patch_agent(monkeypatch, fake_generate)

    resp = _chat(client, auth_headers, "问题一")
    assert resp.status_code == 200

    sessions = client.get("/api/sessions", headers=auth_headers).json()
    assert sessions, "自动创建会话失败"
    sid = sessions[0]["id"]
    detail = client.get(f"/api/sessions/{sid}", headers=auth_headers).json()
    assert len(detail["messages"]) == 2
    user_msg, assistant_msg = detail["messages"]
    assert user_msg["role"] == "user" and user_msg["content"] == "问题一"
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] == GOOD_ANSWER
    assert assistant_msg["sql"] == GOOD.sql
    assert assistant_msg["chart_spec"]["chart_type"] == "line"
    assert assistant_msg["result"]["row_count"] > 0
    assert assistant_msg["status"] == "done"


def test_chat_refusal_no_sql(client, auth_headers, monkeypatch):
    """拒绝回答（写操作请求）：仅 answer + done 事件，无 sql/result/chart。"""
    async def fake_generate(*args, **kwargs):
        return NL2SQLResult(sql="", answer="")

    patch_agent(monkeypatch, fake_generate, stream_text="抱歉，系统仅支持数据查询与分析。")

    resp = _chat(client, auth_headers, "删除所有订单")
    events = parse_sse(resp.text)
    kinds = [e for e, _ in events]
    assert "answer" in kinds and kinds[-1] == "done"
    assert "sql" not in kinds and "result" not in kinds and "chart" not in kinds


def test_chat_unsafe_sql_returns_error_event(client, auth_headers, monkeypatch):
    # 注：命令式写操作问句已被 FR-18 规则层零 LLM 拦截，
    # 此处用普通分析问句验证 SQL 白名单兜底（模拟 LLM 带出恶意 SQL）
    async def fake_generate(*args, **kwargs):
        return NL2SQLResult(
            sql="DELETE FROM orders",
            answer="",
            chart=ChartSpec(chart_type="bar", title="x", x="a", y=["b"]),
        )

    patch_agent(monkeypatch, fake_generate, stream_text="解读")

    resp = _chat(client, auth_headers, "分析一下销售数据")
    assert resp.status_code == 200
    events = parse_sse(resp.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "SQL_UNSAFE"


def test_chat_sql_error_retries_once(client, auth_headers, monkeypatch):
    """FR-10：首次 SQL 执行失败 → 回喂错误重新生成一次 → 第二次成功。"""
    calls = {"n": 0}

    async def fake_generate(schema_digest, history, question, hint="", use_json_mode=True):
        calls["n"] += 1
        if calls["n"] == 1:
            return NL2SQLResult(
                sql="SELECT * FROM no_such_table",
                answer="",
                chart=ChartSpec(chart_type="bar", title="x", x="a", y=["b"]),
            )
        assert "报错" in hint  # 第二次调用携带了错误提示
        return GOOD

    patch_agent(monkeypatch, fake_generate)

    resp = _chat(client, auth_headers, "测试修正")
    events = parse_sse(resp.text)
    assert calls["n"] == 2
    assert events[-1][0] == "done"


def test_chat_sql_error_unrecoverable(client, auth_headers, monkeypatch):
    async def fake_generate(*args, **kwargs):
        return NL2SQLResult(
            sql="SELECT * FROM no_such_table",
            answer="",
            chart=ChartSpec(chart_type="bar", title="x", x="a", y=["b"]),
        )

    patch_agent(monkeypatch, fake_generate)

    resp = _chat(client, auth_headers, "测试失败")
    events = parse_sse(resp.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "SQL_ERROR"


def test_chat_answer_stream_error(client, auth_headers, monkeypatch):
    """解读流失败 → LLM_ERROR 事件终止。"""
    async def fake_generate(*args, **kwargs):
        return GOOD

    async def fake_stream(schema_digest, history, question):
        raise LLMError("模型不可用")
        yield ""  # pragma: no cover

    monkeypatch.setattr("app.agent.nl2sql.generate_nl2sql", fake_generate)
    monkeypatch.setattr("app.agent.nl2sql.stream_answer", fake_stream)

    resp = _chat(client, auth_headers, "随便问")
    events = parse_sse(resp.text)
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "LLM_ERROR"


def test_chat_session_not_found(client, auth_headers):
    resp = _chat(client, auth_headers, "你好", sid="not-exist")
    assert resp.status_code == 404
