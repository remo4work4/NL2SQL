"""Phase 2 验收脚本：附录 A 的 10 条标准问句走完整链路（真实 Qwen3 + SSE）。

用法（后端 8001 已启动）：
    .venv/Scripts/python scripts/test_acceptance.py

验收标准（FR-2）：SQL 执行成功率 ≥ 80%。
"""
import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8001"

APPENDIX_A = [
    "2025 年各月销售额趋势",
    "各品类销售额占比",
    "销售额最高的 10 个商品",
    "各地区销售额对比",
    "2025 年第三季度订单量",
    "客单价最高的城市 Top5",
    "各客户等级的平均消费金额",
    "2025 年同比增长最快的品类",
    "2025 年 6 月每天的下单数",
    "全量数据的总销售额和总订单数",
]


def parse_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        lines = block.strip().split("\n")
        event = next((l.split(": ", 1)[1] for l in lines if l.startswith("event:")), None)
        data = "\n".join(l.split(": ", 1)[1] for l in lines if l.startswith("data:"))
        if event and data:
            try:
                events.append((event, json.loads(data)))
            except json.JSONDecodeError:
                pass
    return events


def run_question(client: httpx.Client, headers: dict, question: str) -> dict:
    t0 = time.time()
    text = ""
    with client.stream(
        "POST",
        f"{BASE}/api/chat",
        headers=headers,
        json={"message": question},
        timeout=120,
    ) as resp:
        if resp.status_code != 200:
            return {"question": question, "ok": False, "error": f"HTTP {resp.status_code}", "latency": time.time() - t0}
        for line in resp.iter_lines():
            text += line + "\n"  # 保留空行（SSE 事件块分隔）
    events = parse_events(text)
    kinds = [e for e, _ in events]
    sql = next((d.get("sql", "") for e, d in events if e == "sql"), "")
    result = next((d for e, d in events if e == "result"), {})
    chart = next((d for e, d in events if e == "chart"), {})
    error = next((d for e, d in events if e == "error"), None)
    ok = "done" in kinds and error is None and result.get("row_count", 0) > 0
    return {
        "question": question,
        "ok": ok,
        "sql": sql.replace("\n", " ")[:100],
        "rows": result.get("row_count", 0),
        "chart": chart.get("chart_type", "-"),
        "error": (error or {}).get("message", "")[:80],
        "latency": round(time.time() - t0, 1),
    }


def main() -> int:
    # trust_env=False：运行环境若有系统代理，localhost 请求必须绕过，否则可能 502
    with httpx.Client(timeout=30, trust_env=False) as client:
        login = client.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
        if login.status_code != 200:
            print(f"[失败] 登录失败: {login.status_code}")
            return 1
        headers = {"Authorization": f"Bearer {login.json()['token']}"}

        print(f"{'#':<3}{'问题':<24}{'结果':<6}{'行数':<7}{'图表':<6}{'耗时s':<7}SQL")
        passed = 0
        for i, q in enumerate(APPENDIX_A, 1):
            r = run_question(client, headers, q)
            mark = "OK" if r["ok"] else "FAIL"
            print(
                f"{i:<3}{q:<24}{mark:<6}{r['rows']:<7}{r['chart']:<6}{r['latency']:<7}{r['sql']}"
            )
            if r.get("error"):
                print(f"    错误: {r['error']}")
            passed += int(r["ok"])

    rate = passed / len(APPENDIX_A) * 100
    print(f"\n成功率: {passed}/{len(APPENDIX_A)} = {rate:.0f}% （验收标准 ≥ 80%）")
    return 0 if rate >= 80 else 1


if __name__ == "__main__":
    sys.exit(main())
