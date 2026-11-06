"""提问意图识别（FR-18，Phase 7）：规则快路径。

只拦高置信命令句式，命中时零 LLM 调用直接回复：
- write：命令式写操作（句首动词 / 帮我·请·麻烦 + 动词 / 把字句）
- chat：问候、致谢、告别
- help：询问系统能力/用法

分析类问句（"帮我看看趋势"、"统计每月新增客户数"、"退货订单有多少"）
一律放行，由 LLM 结构化输出的 intent 字段（query/write/chat/help）做第二层判定，
规则层宁可漏拦不可误拦。
"""
import re

WRITE_VERBS = "删除|删掉|清空|修改|更改|更新|插入|导入|写入|重建|重置|建表|删表|增加一条|增加一行|新增一条|新增一行"

# 动词后紧跟度量词（量/率/数/次数）视为分析问句而非写指令："删除量有多少"、"删除率统计"
_NOT_MEASURE = r"(?!\s*(量|率|数|次数))"

_PATTERNS: dict[str, re.Pattern] = {
    # 句首命令式："删除所有订单"、"更新一下客户等级"
    "write_start": re.compile(rf"^\s*(?:{WRITE_VERBS}){_NOT_MEASURE}"),
    # 请求式："帮我修改一下商品价格"、"麻烦清空数据"
    "write_ask": re.compile(rf"(?:帮我|请|麻烦|烦请).{{0,10}}(?:{WRITE_VERBS}){_NOT_MEASURE}"),
    # 把字句："把客户数据清空"
    "write_ba": re.compile(rf"^(?:把|将).{{0,20}}(?:{WRITE_VERBS}){_NOT_MEASURE}"),
    # 问候/致谢/告别（整句短句才拦）
    "greeting": re.compile(r"^\s*(你好|您好|hi|hello|hey|哈喽|嗨|在吗|早上好|下午好|晚上好)[!！？?。~～,\s]*$"),
    "thanks": re.compile(r"^\s*(谢谢|多谢|感谢|再见|拜拜)"),
    # 能力/用法咨询
    "help": re.compile(r"^\s*(你能做什么|你会什么|你会干什么|你能干什么|怎么使用|怎么用|使用说明|帮助|功能介绍|能干什么|能做什么)"),
}

INTENT_WRITE = "write"
INTENT_CHAT = "chat"
INTENT_HELP = "help"


def detect(question: str) -> str | None:
    """规则快路径：返回 write/chat/help，或 None（放行给 LLM 判定）。"""
    q = question.strip()
    if not q:
        return None
    if _PATTERNS["write_start"].search(q) or _PATTERNS["write_ask"].search(q) or _PATTERNS["write_ba"].search(q):
        return INTENT_WRITE
    if _PATTERNS["greeting"].search(q) or _PATTERNS["thanks"].search(q):
        return INTENT_CHAT
    if _PATTERNS["help"].search(q):
        return INTENT_HELP
    return None


# 规则拦截时的固定回复（不调 LLM，流式输出保持交互一致）
FIXED_REPLIES: dict[str, str] = {
    INTENT_WRITE: (
        "抱歉，系统仅支持数据查询与分析，不支持增删改、清空、导入等写操作。"
        "您可以这样问：2025 年各月销售额趋势、各品类销售额占比。"
    ),
    INTENT_CHAT: (
        "你好！我是智能数据分析助手，用自然语言提问即可查询销售数据并自动生成图表。"
        "试试问：各地区销售额对比，或：2025 年各月销售额趋势。"
    ),
    INTENT_HELP: (
        "我可以帮您把自然语言问题转换为 SQL 并生成图表，支持趋势、占比、对比、Top 排行等分析"
        "（柱状图/折线图/饼图），也支持追问与多轮对话。试试问：销售额最高的 10 个商品。"
    ),
}
