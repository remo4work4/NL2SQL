"""Phase 8 验收脚本：多进程并发压测（跨 worker 共享限流证据）。

前置：后端已用多 worker 启动（uvicorn --workers 2），Redis 运行中（REDIS_URL 已配）。
用法（backend/ 目录下）：
    .venv/Scripts/python scripts/test_concurrency.py --n 6 --concurrency 6

验收标准（FR-19）：
- 全部请求成功（突发并发下无 5xx/无锁冲突）
- 后端日志出现「限流等待」记录 = 全局配额（跨进程）真实生效
  （grep '限流等待' backend/data/logs/app.log，出现即通过）
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 允许脚本独立运行（import app）

import httpx

from app.core.config import settings

BASE = "http://127.0.0.1:8001"
QUESTIONS = [
    "2025 年各月销售额趋势",
    "各品类销售额占比",
    "销售额最高的 10 个商品",
    "各地区销售额对比",
    "2025 年第三季度订单量",
    "各客户等级的平均消费金额",
    "2025 年 6 月每天的下单数",
    "全量数据的总销售额和总订单数",
]


def parse_sse(text: str) -> list[tuple[str, dict]]:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 8 并发压测验收")
    parser.add_argument("--n", type=int, default=6, help="并发请求数")
    parser.add_argument("--concurrency", type=int, default=6, help="同时发起数")
    args = parser.parse_args()

    with httpx.Client(timeout=120, trust_env=False) as client:
        login = client.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": "admin123"})
        if login.status_code != 200:
            print(f"[失败] 登录失败: {login.status_code}")
            return 1
        headers = {"Authorization": f"Bearer {login.json()['token']}"}

        print(f"并发压测：{args.n} 个请求（同时发起 {args.concurrency}），全局并发上限 {settings.max_concurrent_llm}")
        t0 = time.time()
        with httpx.Client(timeout=120, trust_env=False) as c:
            results = []

            def one(i: int):
                t = time.time()
                r = c.post(f"{BASE}/api/chat", headers=headers, json={"message": QUESTIONS[i % len(QUESTIONS)]})
                events = parse_sse(r.content.decode("utf-8"))
                kinds = [e for e, _ in events]
                ok = r.status_code == 200 and "done" in kinds and "sql" in kinds
                results.append((i, ok, time.time() - t))

            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                list(pool.map(one, range(args.n)))

        total = time.time() - t0
        ok = sum(1 for _, s, _ in results if s)
        per = [t for _, _, t in results]
        print(f"成功 {ok}/{args.n}，总耗时 {total:.1f}s，单请求 {min(per):.1f}~{max(per):.1f}s")
        for i, s, t in results:
            if not s:
                print(f"  [失败] 请求 {i}")

        if ok != args.n:
            return 1

        print("判定：backend/data/logs/app.log 中出现「限流等待」行 = 跨 worker 全局配额生效（通过标准）")
        return 0


if __name__ == "__main__":
    sys.exit(main())
