"""NL2SQL 管道（方案 A：单次结构化输出）。

Qwen3 一次调用返回 {sql, answer, chart} 的 JSON：
- 优先用 response_format=json_object；端点不支持时降级为普通调用
- 输出解析失败时回喂错误重试一次
"""
import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.prompts import build_system_prompt, build_user_prompt
from app.core.config import settings
from app.llm.qwen import get_chat_model


class LLMError(Exception):
    """模型调用或输出解析失败。"""


class ChartSpec(BaseModel):
    chart_type: Literal["bar", "line", "pie"] = "bar"
    title: str = ""
    x: str = ""
    y: list[str] = Field(default_factory=list)


class NL2SQLResult(BaseModel):
    intent: Literal["query", "write", "chat", "help"] = "query"  # FR-18 意图（LLM 结构化输出）
    sql: str = ""  # 拒绝回答（写操作请求等）时为空字符串
    answer: str = ""
    chart: ChartSpec = Field(default_factory=ChartSpec)


def _extract_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise LLMError("模型输出中未找到 JSON 对象")
    return text[start : end + 1]


def parse_response(text: str) -> NL2SQLResult:
    try:
        data = json.loads(_extract_json(text))
        result = NL2SQLResult.model_validate(data)
    except (json.JSONDecodeError, ValueError) as e:
        raise LLMError(f"输出无法解析: {e}") from e
    if result.intent != "query" and result.sql:
        # 非查询意图不允许带出 SQL（FR-18 兜底）
        result.sql = ""
    if result.sql and not re.search(r"\bselect\b", result.sql, re.IGNORECASE):
        raise LLMError("生成的 SQL 不是查询语句")
    return result


async def generate_nl2sql(
    schema_digest: str,
    history: list[dict],
    question: str,
    hint: str = "",
    use_json_mode: bool = True,
    include_answer: bool = False,
) -> NL2SQLResult:
    """生成 SQL + 图表规格（answer 默认交由 stream_answer 流程，此处留空）。"""
    if not settings.dashscope_api_key:
        raise LLMError("未配置 DASHSCOPE_API_KEY（backend/.env）")

    llm = get_chat_model(use_json_mode)
    messages = [
        {"role": "system", "content": build_system_prompt(schema_digest, include_answer)},
        {"role": "user", "content": build_user_prompt(history, question, hint)},
    ]
    last_err: LLMError | None = None
    for _ in range(2):
        try:
            resp = await llm.ainvoke(messages)
        except Exception as e:
            # json 模式不被端点支持时降级重试一次
            if use_json_mode:
                return await generate_nl2sql(
                    schema_digest, history, question, hint, use_json_mode=False
                )
            raise LLMError(f"模型调用失败: {e}") from e
        try:
            return parse_response(str(resp.content))
        except LLMError as e:
            last_err = e
            messages.append({"role": "assistant", "content": str(resp.content)})
            messages.append(
                {
                    "role": "user",
                    "content": f"你的输出无法解析为 JSON（原因：{e}）。请重新输出，只输出一个合法 JSON 对象，不要任何多余文字或代码块标记。",
                }
            )
    raise LLMError(f"模型输出解析失败: {last_err}")


ANSWER_SYSTEM_PROMPT = """你是智能数据分析系统的分析助手。先判断用户意图：
- 数据查询：用 2-3 句中文给出解读，说明查询维度与预期结论，不要编造具体数字；
- 追问上一轮结果（如"针对这一结果进行分析"）：对话历史中附带每轮查询的结果摘要（列名/行数/示例数据），基于摘要给出具体分析，引用其中的真实数字，不要以无法获取结果为由拒绝；
- 写操作请求（增删改等）：礼貌说明系统仅支持数据查询与分析；
- 闲聊/无关话题：简短友好回应，可引导回数据分析场景；
- 功能/用法咨询：简要介绍系统能力并给出一个示例问题。
输出要求（必须遵守）：回答只包含分析文本本身（2~3 句纯文本中文）；不要输出 SQL、JSON、代码块或任何结构化标记；严禁在回答中提及"JSON""格式限制""无法输出"等关于输出格式的说明。"""


async def stream_answer(
    schema_digest: str, history: list[dict], question: str
):
    """流式生成解读文本（真 token 流，首字延迟关键路径）。

    用法: async for delta in stream_answer(...): ...
    """
    if not settings.dashscope_api_key:
        raise LLMError("未配置 DASHSCOPE_API_KEY（backend/.env）")
    messages = [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(history, question)},
    ]
    try:
        llm = get_chat_model(json_mode=False)
        async for chunk in llm.astream(messages):
            text = chunk.content
            if isinstance(text, str) and text:
                yield text
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"模型调用失败: {e}") from e
