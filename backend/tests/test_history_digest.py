"""多轮追问上下文：助手消息附查询结果摘要（支撑「针对这一结果进行分析」类追问）。"""
from app.agent.prompts import _result_digest, history_from_messages


class TestResultDigest:
    def test_basic(self):
        digest = _result_digest(
            {"columns": ["region", "sales"], "rows": [["华东", 100], ["华北", 80]], "row_count": 6}
        )
        assert "共 6 行" in digest
        assert "region" in digest and "华东" in digest

    def test_truncates_to_max_len(self):
        digest = _result_digest(
            {"columns": ["a"], "rows": [["x" * 500]], "row_count": 1}, max_len=100
        )
        assert len(digest) <= 100

    def test_empty_result(self):
        assert _result_digest({}) == ""
        assert _result_digest(None) == ""


class TestHistoryWithDigest:
    def test_assistant_message_with_result_appends_digest(self):
        msgs = [
            {"role": "user", "content": "各地区销售额对比", "result": None},
            {
                "role": "assistant",
                "content": "华东地区领先……",
                "result": {
                    "columns": ["region", "sales"],
                    "rows": [["华东", 3000], ["华北", 2000]],
                    "row_count": 6,
                },
            },
        ]
        history = history_from_messages(msgs)
        assert history[0]["content"] == "各地区销售额对比"  # 用户消息不加摘要
        assert "[查询结果：共 6 行" in history[1]["content"]
        assert "华东" in history[1]["content"]

    def test_assistant_without_result_unchanged(self):
        msgs = [{"role": "assistant", "content": "普通回复", "result": None}]
        history = history_from_messages(msgs)
        assert history[0]["content"] == "普通回复"
        assert "查询结果" not in history[0]["content"]

    def test_empty_content_skipped(self):
        msgs = [{"role": "assistant", "content": "", "result": {"columns": [], "rows": [], "row_count": 0}}]
        assert history_from_messages(msgs) == []
