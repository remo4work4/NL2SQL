"""提示词：系统提示词（含 schema 摘要 + 规则 + few-shot）与用户提示词（历史 + 问题）。"""
import sqlite3

from app.core import semantic_meta
from app.core.config import settings

FEW_SHOT_EXAMPLES = """
示例（问题 → 输出 JSON）：
1. 问：2025 年各月销售额趋势
   {"intent": "query", "sql": "SELECT substr(order_date, 1, 7) AS month, SUM(amount) AS sales FROM orders WHERE order_date >= '2025-01-01' AND order_date < '2026-01-01' GROUP BY month ORDER BY month", "answer": "2025 年 12 月销售额最高……", "chart": {"chart_type": "line", "title": "2025 年各月销售额趋势", "x": "month", "y": ["sales"]}}
2. 问：各品类销售额占比
   {"intent": "query", "sql": "SELECT p.category, SUM(o.amount) AS sales FROM orders o JOIN products p ON o.product_id = p.id GROUP BY p.category ORDER BY sales DESC", "answer": "数码家电占比最高……", "chart": {"chart_type": "pie", "title": "各品类销售额占比", "x": "category", "y": ["sales"]}}
3. 问：各地区销售额对比
   {"intent": "query", "sql": "SELECT c.region, SUM(o.amount) AS sales FROM orders o JOIN customers c ON o.customer_id = c.id GROUP BY c.region ORDER BY sales DESC", "answer": "华东地区领先……", "chart": {"chart_type": "bar", "title": "各地区销售额对比", "x": "region", "y": ["sales"]}}
4. 问：销售额最高的 10 个商品
   {"intent": "query", "sql": "SELECT p.name, SUM(o.amount) AS sales FROM orders o JOIN products p ON o.product_id = p.id GROUP BY p.id, p.name ORDER BY sales DESC LIMIT 10", "answer": "销售额最高的是……", "chart": {"chart_type": "bar", "title": "销售额 Top10 商品", "x": "name", "y": ["sales"]}}
5. 问：删除所有订单
   {"intent": "write", "sql": "", "answer": "", "chart": {"chart_type": "bar", "title": "", "x": "", "y": []}}
""".strip()


def _all_tables(conn) -> list[str]:
    """业务库全部表名（PG information_schema，排除系统表）。"""
    return [
        row["table_name"]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
        ).fetchall()
    ]


def build_table_detail(conn, table: str, meta: semantic_meta.TableMeta | None) -> str:
    """单表描述：物理结构 + 语义元数据（业务名/字段注释/枚举/关联）+ 样例行。"""
    info = conn.execute(
        "SELECT column_name AS name, data_type AS type FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
        (table,),
    ).fetchall()
    count = conn.execute(f'SELECT COUNT(*) AS n FROM "{table}"').fetchone()["n"]
    cmap = meta.column_map if meta else {}
    header = f"表 {table}（{meta.biz_name}）" if meta and meta.biz_name else f"表 {table}"
    if meta and meta.description:
        header += f"：{meta.description}"
    lines = [f"{header}，共 {count} 行"]
    for r in info:
        c = cmap.get(r["name"])
        parts = [f"  - {r['name']} {r['type']}"]
        if c:
            parts.append(f"（{c['biz_name']}：{c['description']}）")
            if c.get("enum_values"):
                parts.append(f" 取值仅限：{'/'.join(c['enum_values'])}")
        lines.append("".join(parts))
    if meta and meta.relations:
        rel = "；".join(
            f"{r['from_column']} → {r['to_table']}.{r['to_column']}" for r in meta.relations
        )
        lines.append(f"  关联: {rel}")
    for r in conn.execute(f'SELECT * FROM "{table}" LIMIT 3').fetchall():
        sample = ", ".join(f"{k}={v}" for k, v in r.items())
        lines.append(f"  示例行: {sample}")
    return "\n".join(lines)


def build_schema_digest(conn, tables: list[str] | None = None) -> str:
    """表结构摘要：物理结构 + 语义元数据合并。

    tables=None 时输出全部表（全量兜底，改造前行为）；
    传入列表时只输出选中表（RAG 检索后按需注入）。
    """
    selected = tables if tables is not None else _all_tables(conn)
    meta_map = semantic_meta.load_tables()
    return "\n".join(
        build_table_detail(conn, t, meta_map.get(t)) for t in selected
    )


def build_system_prompt(schema_digest: str, include_answer: bool = True) -> str:
    answer_line = (
        '"answer": "2-3句中文解读，包含关键数字"'
        if include_answer
        else '"answer": ""（固定为空字符串，解读文本由另一流程生成）'
    )
    return f"""你是智能数据分析系统的 NL2SQL 引擎，把用户的自然语言问题转换为 SQLite 查询并给出分析解读。

数据库 schema（SQLite）：
{schema_digest}

查询规则：
1. 先判断用户意图（intent 字段）：
   - query：数据分析查询，正常生成 SQL；
   - write：写操作请求（增删改、清空、导入等），sql 输出空字符串 ""，礼貌拒绝并说明系统仅支持数据查询与分析；
   - chat：闲聊/无关话题，sql 输出空字符串 ""，简短友好回应；若用户要求分析上一轮查询结果（如"针对这一结果进行分析"），也归为 chat 并输出空 sql，分析文本由另一流程基于历史中的结果摘要生成；
   - help：询问系统功能/用法，sql 输出空字符串 ""，介绍系统能力。
2. 只生成 SELECT 或 WITH 查询（PostgreSQL 方言），禁止任何写操作；表名与字段名必须来自 schema。
3. order_date 是 'YYYY-MM-DD' 格式文本；按月份聚合用 substr(order_date, 1, 7)；季度用 EXTRACT(QUARTER FROM order_date::date)。
4. amount 与 unit_price 单位是元；小数保留两位用 ROUND((x)::numeric, 2)（PG 的 round(double, int) 不存在，必须先转 numeric）。
5. 用户问"占比/比例"时优先输出饼图；问"趋势/变化"优先折线图；分组对比用柱状图。
6. 日期过滤必须用字符串比较，例如 order_date >= '2025-01-01' AND order_date < '2026-01-01'。

输出格式：只输出一个 JSON 对象，不要输出任何其他文字或代码块标记：
{{"intent": "query|write|chat|help", "sql": "SQL语句", {answer_line}, "chart": {{"chart_type": "bar|line|pie", "title": "图表标题", "x": "分类列名", "y": ["数值列名"]}}}}

chart 要求：chart_type 只能是 bar/line/pie；x 与 y 必须是 SQL 结果中的列名；y 至多 2 个数值列；answer 必须与 SQL 语义一致，不要编造数字。

{FEW_SHOT_EXAMPLES}"""


def build_user_prompt(history: list[dict], question: str, hint: str = "") -> str:
    """历史对话（最近 N 轮）+ 当前问题。history 元素: {role, content}。"""
    parts: list[str] = []
    if history:
        parts.append("对话历史（用于理解指代与追问上下文）：")
        for msg in history:
            role = "用户" if msg["role"] == "user" else "助手"
            content = (msg.get("content") or "").strip()
            if content:
                parts.append(f"{role}: {content}")
    parts.append(f"当前问题: {question}")
    if hint:
        parts.append(hint)
    parts.append("请按输出格式直接返回 JSON。")
    return "\n".join(parts)


def _result_digest(result: dict, max_len: int = 220) -> str:
    """查询结果摘要：列名 + 行数 + 前几行示例（供追问「针对这一结果分析」时引用真实数据）。"""
    if not result:
        return ""
    try:
        columns = result.get("columns") or []
        rows = result.get("rows") or []
        row_count = result.get("row_count", len(rows))
        parts = [f"查询结果：共 {row_count} 行，列为 {', '.join(str(c) for c in columns[:6])}"]
        samples = [
            ", ".join(str(v) for v in row[:6])
            for row in rows[:3]
        ]
        if samples:
            parts.append("前几行示例: " + "；".join(samples))
        digest = " ".join(parts)
        return digest[:max_len]
    except (TypeError, ValueError):
        return ""


def history_from_messages(messages: list[dict]) -> list[dict]:
    """把 DB 消息转为提示词用的精简历史（role/content 截断；助手消息附查询结果摘要）。"""
    out = []
    for msg in messages:
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if len(content) > 300:
            content = content[:300] + "…"
        if msg["role"] == "assistant" and msg.get("result"):
            digest = _result_digest(msg["result"])
            if digest:
                content = f"{content}\n[{digest}]"
        out.append({"role": msg["role"], "content": content})
    return out
