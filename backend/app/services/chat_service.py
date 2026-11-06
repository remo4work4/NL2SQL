"""对话编排服务：NL2SQL 全流程 + SSE 事件流（需求文档 7.2 节协议）。

事件顺序: answer* → sql → result → chart → done
error 可出现在任意位置并终止流（code: SQL_UNSAFE / SQL_ERROR / LLM_ERROR）

性能设计：解读文本（真 token 流）与 SQL 结构化生成并行发起，
首字延迟 ≈ 解读流的首个 token（NFR-1 ≤5s），端到端 ≈ max(两路)。
"""
import asyncio
import json
import logging
import time

from app.agent import intent, nl2sql
from app.agent.nl2sql import LLMError
from app.agent.prompts import _all_tables, build_schema_digest, build_table_detail, history_from_messages
from app.core import rate_limit, retriever, semantic_meta, sql_safety
from app.core.config import settings
from app.core.database import connect_business_db
from app.services import session_service

logger = logging.getLogger("nl2sql.chat")

# schema 摘要缓存：每表详情（物理结构 + 语义元数据），TTL 过期重建。
# Phase 9 多实例：PG 无文件 mtime 可依，schema 变更后由 TTL 自然收敛。
# RAG 注入 = 按问题从缓存拼装选中表，不重复扫库。
_schema_cache: dict = {"ts": 0.0, "details": {}}


def _get_table_details() -> dict[str, str]:
    if time.time() - _schema_cache["ts"] > settings.schema_cache_ttl:
        conn = connect_business_db()
        try:
            meta_map = semantic_meta.load_tables()
            _schema_cache["details"] = {
                t: build_table_detail(conn, t, meta_map.get(t)) for t in _all_tables(conn)
            }
            _schema_cache["ts"] = time.time()
        finally:
            conn.close()
    return _schema_cache["details"]


def _get_schema_digests(question: str) -> tuple[str, str]:
    """返回 (注入摘要, 全量摘要)。

    RAG 启用且命中时注入仅含相关表；未命中/关闭时二者相同（全量，改造前行为）。
    全量摘要同时用于 FR-10 失败重试（RAG 漏表时天然兜底）。
    """
    details = _get_table_details()
    full = "\n".join(details.values())
    if not settings.rag_enabled:
        return full, full
    selected = retriever.retrieve_tables(question)
    if not selected:
        logger.info("RAG 未命中，兜底全量注入 %d 张表", len(details))
        return full, full
    return "\n".join(details[t] for t in selected), full


def _chunk_text(text: str, size: int = 8) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _evt(name: str, payload: dict) -> dict:
    """SSE 事件：data 手动 JSON 序列化（sse-starlette 对 dict 会用 str() 而非 JSON）。"""
    return {"event": name, "data": json.dumps(payload, ensure_ascii=False)}


async def _generate(*args, **kwargs):
    """带共享限流的 SQL 结构化生成（Phase 8：跨进程令牌桶）。"""
    async with rate_limit.llm_limiter():
        t0 = time.perf_counter()
        try:
            return await nl2sql.generate_nl2sql(*args, **kwargs)
        finally:
            q = args[2][:40] if len(args) > 2 else ""
            logger.info("SQL 生成完成，耗时 %.2fs，问题: %s", time.perf_counter() - t0, q)


async def _stream_answer(schema_digest: str, history: list[dict], question: str):
    """带共享限流的解读文本真流式（Phase 8：跨进程令牌桶）。"""
    async with rate_limit.llm_limiter():
        t0 = time.perf_counter()
        try:
            async for delta in nl2sql.stream_answer(schema_digest, history, question):
                yield delta
        finally:
            logger.info("解读流完成，耗时 %.2fs", time.perf_counter() - t0)


async def chat_event_stream(user_id: str, session_id: str, question: str):
    """按 SSE 协议产出事件 dict（sse-starlette 直接消费）。"""
    user_msg_id = session_service.add_message(user_id, session_id, "user", question)

    # ---- 0. 意图规则快路径（FR-18）：写操作/问候/帮助，零 LLM 调用直接回复 ----
    rule_intent = intent.detect(question)
    if rule_intent:
        fixed = intent.FIXED_REPLIES[rule_intent]
        for chunk in _chunk_text(fixed):
            yield _evt("answer", {"delta": chunk})
        assistant_id = session_service.add_message(user_id, session_id, "assistant", fixed, status="done")
        yield _evt("done", {"message_id": assistant_id})
        logger.info("意图规则拦截: %s | %s", rule_intent, question[:40])
        return

    history = history_from_messages(
        session_service.get_recent_messages(
            user_id, session_id, settings.memory_window * 2, exclude_id=user_msg_id
        )
    )
    schema_digest, schema_full = _get_schema_digests(question)

    # ---- 1. 解读流式 与 SQL 生成 并行 ----
    sql_task = asyncio.create_task(_generate(schema_digest, history, question))
    answer_parts: list[str] = []
    try:
        async for delta in _stream_answer(schema_digest, history, question):
            answer_parts.append(delta)
            yield _evt("answer", {"delta": delta})
    except LLMError as e:
        logger.warning("解读生成失败: %s", e)
        sql_task.cancel()
        yield _evt("error", {"code": "LLM_ERROR", "message": str(e)})
        session_service.add_message(
            user_id, session_id, "assistant", f"模型调用失败：{e}", status="error", error=str(e)
        )
        return
    answer = "".join(answer_parts).strip() or "查询完成。"

    try:
        result = await sql_task
    except LLMError as e:
        logger.warning("SQL 生成失败: %s", e)
        yield _evt("error", {"code": "LLM_ERROR", "message": str(e)})
        session_service.add_message(
            user_id, session_id, "assistant", answer, status="error", error=str(e)
        )
        return

    # ---- 1.5 拒绝回答（LLM 判为 write/chat/help 或未生成 SQL）：仅解读文本，无 SQL/结果/图表 ----
    logger.info("LLM 意图: %s", result.intent)
    if not result.sql.strip():
        assistant_id = session_service.add_message(
            user_id, session_id, "assistant", answer, status="done"
        )
        yield _evt("done", {"message_id": assistant_id})
        return

    # ---- 2. 安全校验 + 执行（FR-10：失败回喂修正一次） ----
    try:
        safe_sql = sql_safety.validate_sql(result.sql, settings.max_result_rows)
    except sql_safety.SQLUnsafeError as e:
        logger.warning("SQL 拦截: %s | %s", e, result.sql[:120])
        yield _evt("error", {"code": "SQL_UNSAFE", "message": str(e)})
        session_service.add_message(
            user_id,
            session_id,
            "assistant",
            answer,
            status="error",
            error=str(e),
            sql=result.sql,
        )
        return

    query_result = None
    try:
        query_result = sql_safety.execute_query(
            safe_sql, settings.max_result_rows, timeout=settings.sql_timeout
        )
    except sql_safety.SQLExecutionError as first_err:
        logger.warning("SQL 执行失败: %s | %s", first_err, safe_sql[:120])
        fixed = False
        for _ in range(max(settings.sql_retry_times, 0)):
            try:
                # 修正轮用全量 schema（RAG 漏表时兜底），提示词带上执行报错
                result = await _generate(
                    schema_full,
                    history,
                    question,
                    hint=f"上次生成的 SQL 执行报错：{first_err}。请修正 SQL 后重新输出完整 JSON。",
                )
                safe_sql = sql_safety.validate_sql(result.sql, settings.max_result_rows)
                query_result = sql_safety.execute_query(
                    safe_sql, settings.max_result_rows, timeout=settings.sql_timeout
                )
                fixed = True
                break
            except (sql_safety.SQLExecutionError, sql_safety.SQLUnsafeError) as e2:
                first_err = e2
            except LLMError:
                break
        if not fixed:
            yield _evt("error", {"code": "SQL_ERROR", "message": f"SQL 执行失败：{first_err}"})
            session_service.add_message(
                user_id,
                session_id,
                "assistant",
                answer,
                status="error",
                error=str(first_err),
                sql=result.sql,
            )
            return

    # ---- 3. 成功路径：事件 + 持久化 ----
    logger.info("查询成功: %d 行 | %s", query_result["row_count"], result.sql[:120])
    chart_payload = result.chart.model_dump()
    assistant_id = session_service.add_message(
        user_id,
        session_id,
        "assistant",
        answer,
        sql=result.sql,
        chart=chart_payload,
        result=query_result,
        status="done",
    )
    yield _evt("sql", {"sql": result.sql})
    yield _evt("result", query_result)
    yield _evt("chart", chart_payload)
    yield _evt("done", {"message_id": assistant_id})
