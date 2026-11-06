"""FR-18 意图识别测试：规则快路径（附录 D）+ LLM intent 字段解析 + 零 LLM 调用路由。"""
import json

import pytest

from app.agent import intent
from app.agent.nl2sql import NL2SQLResult, parse_response


class TestRuleLayer:
    @pytest.mark.parametrize(
        "q",
        [
            "删除所有订单",
            "帮我修改一下商品价格",
            "把客户数据清空",
            "插入一条新订单",
            "请删除 orders 表",
            "麻烦更新一下客户等级",
        ],
    )
    def test_write_detected(self, q):
        assert intent.detect(q) == "write"

    @pytest.mark.parametrize("q", ["你好", "谢谢", "再见", "在吗？", "早上好"])
    def test_chat_detected(self, q):
        assert intent.detect(q) == "chat"

    @pytest.mark.parametrize("q", ["你能做什么？", "怎么使用这个系统", "功能介绍"])
    def test_help_detected(self, q):
        assert intent.detect(q) == "help"

    @pytest.mark.parametrize(
        "q",
        [
            "帮我看看2025年各月销售额趋势",
            "2025 年退货订单有多少",
            "统计每月新增客户数",
            "删除量有多少",  # 动词+度量词 = 分析问句，不得误拦
            "2025 年各月销售额趋势",
            "请问销售额最高的品类是哪个",
        ],
    )
    def test_analysis_passthrough(self, q):
        assert intent.detect(q) is None

    def test_empty(self):
        assert intent.detect("") is None
        assert intent.detect("   ") is None


class TestParseResponse:
    def test_write_intent_forces_empty_sql(self):
        r = parse_response(
            '{"intent": "write", "sql": "DELETE FROM orders", "answer": "", '
            '"chart": {"chart_type": "bar", "title": "", "x": "", "y": []}}'
        )
        assert r.intent == "write" and r.sql == ""

    def test_query_intent_keeps_sql(self):
        r = parse_response(
            '{"intent": "query", "sql": "SELECT 1", "answer": "", '
            '"chart": {"chart_type": "bar", "title": "", "x": "", "y": []}}'
        )
        assert r.intent == "query" and r.sql == "SELECT 1"

    def test_missing_intent_defaults_query(self):
        r = parse_response(
            '{"sql": "SELECT 1", "answer": "", '
            '"chart": {"chart_type": "bar", "title": "", "x": "", "y": []}}'
        )
        assert r.intent == "query"


def _chat(client, auth_headers, question, sid=None):
    url = f"/api/sessions/{sid}/chat" if sid else "/api/chat"
    return client.post(url, json={"message": question}, headers=auth_headers)


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    text = text.replace("\r\n", "\n")
    for block in text.split("\n\n"):
        lines = block.strip().split("\n")
        event = next((l.split(": ", 1)[1] for l in lines if l.startswith("event:")), None)
        data = "\n".join(l.split(": ", 1)[1] for l in lines if l.startswith("data:"))
        if event and data:
            events.append((event, json.loads(data)))
    return events


@pytest.fixture()
def llm_counter(monkeypatch):
    """打桩 LLM 并计数调用次数。"""
    calls = {"n": 0}

    async def fake_generate(*a, **k):
        calls["n"] += 1
        return NL2SQLResult(sql="SELECT 1")

    async def fake_stream(*a, **k):
        calls["n"] += 1
        yield "x"

    monkeypatch.setattr("app.agent.nl2sql.generate_nl2sql", fake_generate)
    monkeypatch.setattr("app.agent.nl2sql.stream_answer", fake_stream)
    return calls


class TestChatRouting:
    def test_write_rule_path_zero_llm(self, client, auth_headers, llm_counter):
        resp = _chat(client, auth_headers, "删除所有订单")
        assert resp.status_code == 200
        events = parse_sse(resp.text)
        kinds = [e for e, _ in events]
        assert llm_counter["n"] == 0  # 零 LLM 调用
        assert set(kinds) == {"answer", "done"} and kinds[-1] == "done"
        answer = "".join(d["delta"] for e, d in events if e == "answer")
        assert "仅支持数据查询" in answer

    def test_greeting_rule_path_zero_llm(self, client, auth_headers, llm_counter):
        resp = _chat(client, auth_headers, "你好")
        events = parse_sse(resp.text)
        assert llm_counter["n"] == 0
        kinds = [e for e, _ in events]
        assert set(kinds) == {"answer", "done"}
        answer = "".join(d["delta"] for e, d in events if e == "answer")
        assert "数据分析助手" in answer

    def test_help_rule_path(self, client, auth_headers, llm_counter):
        resp = _chat(client, auth_headers, "你能做什么？")
        events = parse_sse(resp.text)
        assert llm_counter["n"] == 0
        answer = "".join(d["delta"] for e, d in events if e == "answer")
        assert "SQL" in answer

    def test_rule_path_persists_messages(self, client, auth_headers, llm_counter):
        _chat(client, auth_headers, "你好")
        sessions = client.get("/api/sessions", headers=auth_headers).json()
        detail = client.get(f"/api/sessions/{sessions[0]['id']}", headers=auth_headers).json()
        assert len(detail["messages"]) == 2
        assert detail["messages"][0]["role"] == "user"
        assert detail["messages"][1]["role"] == "assistant"

    def test_query_passes_to_llm(self, client, auth_headers, llm_counter):
        resp = _chat(client, auth_headers, "2025 年各月销售额趋势")
        events = parse_sse(resp.text)
        kinds = [e for e, _ in events]
        assert llm_counter["n"] >= 1  # 走管道，LLM 被调用
        assert "sql" in kinds and kinds[-1] == "done"

    def test_analysis_with_bang_help_not_blocked(self, client, auth_headers, llm_counter):
        """含"帮我"的分析问句不得误拦（附录 D #9）。"""
        resp = _chat(client, auth_headers, "帮我看看2025年各月销售额趋势")
        events = parse_sse(resp.text)
        assert llm_counter["n"] >= 1
        assert "sql" in [e for e, _ in events]
