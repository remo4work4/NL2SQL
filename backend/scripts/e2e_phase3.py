"""Phase 3 前后端联调脚本（Playwright，真实后端 + 真实 LLM）。

前置：前端 5174（VITE_USE_MOCK=false）+ 后端 8001 均运行中。
用法：
    .venv/Scripts/python scripts/e2e_phase3.py

覆盖：登录 → 新建会话 → 提问（流式/SQL/图表）→ 多轮追问（FR-6）
      → 历史回看（FR-9，刷新恢复）→ 写操作拒绝 + 数据完整性 → 会话重命名 → 控制台错误。
"""
import json
import sys

import httpx
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5174"
API = "http://127.0.0.1:8001"


def orders_count() -> int:
    """业务库 orders 行数（数据完整性断言用）。"""
    with httpx.Client(timeout=30, trust_env=False) as client:
        login = client.post(f"{API}/api/auth/login", json={"username": "admin", "password": "admin123"})
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        tables = client.get(f"{API}/api/db/schema", headers=headers).json()
        return next(t["row_count"] for t in tables if t["table"] == "orders")


def main() -> int:
    errors: list[str] = []
    report: dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on(
            "console",
            lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None,
        )

        # ---- 1. 登录 ----
        page.goto(BASE)
        page.wait_for_load_state("networkidle")
        page.fill('input[placeholder="用户名"]', "admin")
        page.fill('input[placeholder="密码"]', "admin123")
        page.click('button:has-text("进入系统")')
        page.wait_for_timeout(2500)
        report["登录"] = "OK"

        # ---- 2. 新建会话（与历史会话隔离） ----
        page.click('button:has-text("新建会话")')
        page.wait_for_timeout(1500)
        report["新建会话"] = "OK"

        # ---- 3. 首轮提问（流式 + SQL + 图表） ----
        page.fill("textarea", "2025 年各月销售额趋势")
        page.keyboard.press("Enter")
        page.wait_for_selector(".ant-layout pre", timeout=90000)
        page.wait_for_function(
            "document.querySelectorAll('.ant-layout-sider:last-of-type canvas').length > 0",
            timeout=60000,
        )
        page.wait_for_timeout(3000)
        sql_text = page.evaluate("document.querySelector('.ant-layout pre')?.textContent || ''")
        has_result_table = page.evaluate(
            "document.querySelectorAll('.ant-layout-content .ant-table-row').length > 0"
        )
        canvas_pixels = page.evaluate(
            """() => {
                const canvas = document.querySelectorAll('.ant-layout-sider')[1]?.querySelector('canvas')
                if (!canvas) return 0
                const ctx = canvas.getContext('2d')
                const d = ctx.getImageData(0, 0, Math.min(canvas.width, 300), Math.min(canvas.height, 300)).data
                let n = 0
                for (let i = 3; i < d.length; i += 40) if (d[i] > 0) n++
                return n
            }"""
        )
        report["首轮提问"] = "OK"
        report["SQL 代码块"] = "OK" if "SELECT" in sql_text.upper() else f"FAIL: {sql_text[:60]}"
        report["结果表格"] = "OK" if has_result_table else "FAIL"
        report["图表渲染"] = "OK" if canvas_pixels > 0 else "FAIL"

        # ---- 4. 多轮追问（FR-6：指代上文"销售额"） ----
        page.fill("textarea", "那按地区看一下")
        page.keyboard.press("Enter")
        page.wait_for_function(
            "document.querySelectorAll('.ant-layout pre').length >= 2", timeout=90000
        )
        page.wait_for_timeout(3000)
        follow_sql = page.evaluate(
            "[...document.querySelectorAll('.ant-layout pre')].map(e => e.textContent).join(' ')"
        )
        follow_ok = "region" in follow_sql.lower()
        report["多轮追问（按地区）"] = "OK" if follow_ok else f"FAIL: {follow_sql[:100]}"

        # ---- 5. 历史回看（FR-9）：刷新后消息/图表恢复 ----
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(4000)
        restored = page.evaluate(
            """() => {
                const msgs = document.querySelectorAll('.ant-layout-content .ant-typography').length
                const pres = document.querySelectorAll('.ant-layout pre').length
                const canvas = document.querySelectorAll('.ant-layout-sider')[1]?.querySelector('canvas')
                const ctx = canvas?.getContext('2d')
                const d = ctx ? ctx.getImageData(0, 0, Math.min(canvas.width, 300), Math.min(canvas.height, 300)).data : null
                let n = 0
                if (d) for (let i = 3; i < d.length; i += 40) if (d[i] > 0) n++
                return { msgs, pres, chartPixels: n }
            }"""
        )
        report["历史回看"] = (
            "OK"
            if restored["msgs"] > 0 and restored["pres"] >= 2 and restored["chartPixels"] > 0
            else f"FAIL: {json.dumps(restored, ensure_ascii=False)}"
        )

        # ---- 6. 写操作请求：拒绝 + 数据完整性 ----
        before = orders_count()
        page.fill("textarea", "删除所有订单")
        page.keyboard.press("Enter")
        page.wait_for_timeout(15000)
        last_msg = page.evaluate(
            """() => {
                const items = [...document.querySelectorAll('.ant-layout-content .ant-typography')]
                return items[items.length - 1]?.textContent || ''
            }"""
        )
        refused = any(k in last_msg for k in ("抱歉", "无法", "仅支持", "不能"))
        after = orders_count()
        report["写操作被拒绝"] = "OK" if refused else f"FAIL: {last_msg[:80]}"
        report["数据完整性"] = (
            "OK" if after == before else f"FAIL: {before} -> {after}"
        )

        # ---- 7. 会话重命名（FR-12） ----
        page.hover(".session-item >> nth=0")
        page.wait_for_selector(".session-item >> nth=0 >> .session-actions button >> nth=0", timeout=5000)
        page.click(".session-item >> nth=0 >> .session-actions button >> nth=0")
        page.wait_for_selector(".ant-modal input", timeout=5000)
        page.fill(".ant-modal input", "联调测试会话")
        # 注意：antd 会给两个汉字的按钮自动加空格（"保 存"），has-text 需避开
        page.click('.ant-modal button:has-text("保")')
        page.wait_for_timeout(1200)
        renamed = page.evaluate(
            "document.querySelector('.session-item')?.textContent?.includes('联调测试会话')"
        )
        report["会话重命名"] = "OK" if renamed else "FAIL"

        # ---- 8. 控制台错误 ----
        report["控制台错误"] = "(无)" if not errors else "; ".join(errors[:5])

        browser.close()

    print("== Phase 3 联调结果 ==")
    all_ok = True
    for k, v in report.items():
        bad = isinstance(v, str) and v.startswith("FAIL")
        if bad:
            all_ok = False
        if k == "控制台错误" and v != "(无)":
            print(f"  {k:<16} WARN {v}")
        else:
            print(f"  {k:<16} {v}")
    print(f"\n结论: {'全部通过' if all_ok else '存在失败项'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
