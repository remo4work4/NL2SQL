"""UI 截图巡检：登录页 → 主界面（种子会话+图表）→ 提问流式 → 饼图。

用法（需先启动前端 5174）：
    .venv/Scripts/python scripts/screenshot_ui.py
截图输出到 %TEMP%/nl2sql-shots/。
"""
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOTS = Path(os.environ.get("TEMP", "/tmp")) / "nl2sql-shots"


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.goto("http://localhost:5174")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(SHOTS / "01-login.jpg"), type="jpeg", quality=75)

        page.fill('input[placeholder="用户名"]', "admin")
        page.fill('input[placeholder="密码"]', "admin123")
        page.click('button:has-text("进入系统")')
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)  # 会话加载 + 图表渲染
        page.screenshot(path=str(SHOTS / "02-main-seeded.jpg"), type="jpeg", quality=75)

        # 提问，观察流式与图表
        page.fill("textarea", "各品类销售额占比")
        page.keyboard.press("Enter")
        page.wait_for_timeout(700)
        page.screenshot(path=str(SHOTS / "03-streaming.jpg"), type="jpeg", quality=75)
        page.wait_for_timeout(5000)  # 等待流结束 + 饼图渲染
        page.screenshot(path=str(SHOTS / "04-pie-chart.jpg"), type="jpeg", quality=75)

        browser.close()
    print("screenshots ->", SHOTS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
