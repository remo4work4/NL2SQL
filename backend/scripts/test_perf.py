"""Phase 4 性能摸底（NFR-1）：多轮全链路延迟统计。

用法（后端 8001 已启动）：
    .venv/Scripts/python scripts/test_perf.py [--rounds 3]

指标：端到端延迟（P50/P95/均值）与首字延迟（首个 answer 事件）。
验收标准（NFR-1）：端到端 P95 ≤ 20s；首字延迟 ≤ 5s。
"""
import argparse
import json
import statistics
import sys
import time

import httpx

BASE = "http://127.0.0.1:8001"

QUESTIONS = [
    "2025 年各月销售额趋势",
    "各品类销售额占比",
    "销售额最高的 10 个商品",
    "各地区销售额对比",
    "各客户等级的平均消费金额",
]


def measure(client: httpx.Client, headers: dict, question: str) -> tuple[float, float]:
    """返回 (首字延迟, 端到端延迟)。"""
    t0 = time.perf_counter()
    first_delta = None
    with client.stream(
        "POST", f"{BASE}/api/chat", headers=headers, json={"message": question}, timeout=120
    ) as resp:
        for line in resp.iter_lines():
            if first_delta is None and line.startswith("data:") and '"delta"' in line:
                first_delta = time.perf_counter()
            if line.startswith("event:") and line.split(": ", 1)[1].strip() == "done":
                break
    end = time.perf_counter()
    return first_delta - t0, end - t0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()

    with httpx.Client(timeout=30, trust_env=False) as client:
        login = client.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
        headers = {"Authorization": f"Bearer {login.json()['token']}"}

        firsts: list[float] = []
        totals: list[float] = []
        for r in range(args.rounds):
            for q in QUESTIONS:
                f, t = measure(client, headers, q)
                firsts.append(f)
                totals.append(t)
                print(f"第{r + 1}轮 {q:<20} 首字 {f:5.2f}s  端到端 {t:5.2f}s")

    def stat(vals):
        vals = sorted(vals)
        p50 = vals[len(vals) // 2]
        p95 = vals[int(len(vals) * 0.95)]
        return f"均值 {statistics.mean(vals):.2f}s / P50 {p50:.2f}s / P95 {p95:.2f}s"

    print(f"\n样本 {len(totals)} 个")
    print(f"首字延迟: {stat(firsts)}")
    print(f"端到端:   {stat(totals)}")
    p95_total = sorted(totals)[int(len(totals) * 0.95)]
    p95_first = sorted(firsts)[int(len(firsts) * 0.95)]
    ok = p95_total <= 20 and p95_first <= 5
    print(f"\n结论: {'通过（NFR-1）' if ok else '未达标'}（端到端 P95 ≤ 20s / 首字 ≤ 5s）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
