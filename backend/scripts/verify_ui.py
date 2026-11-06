"""UI 程序化巡检（无截图依赖）：验证深色主题、玻璃面板、图表真实渲染、无控制台报错。

用法（需先启动前端 5174）：
    .venv/Scripts/python scripts/verify_ui.py
"""
import json
import sys

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5174"


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on(
            "console",
            lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None,
        )

        page.goto(BASE)
        page.wait_for_load_state("networkidle")
        login = page.evaluate(
            """() => {
                const body = getComputedStyle(document.body)
                const card = document.querySelector('.ant-card')
                const cs = card ? getComputedStyle(card) : null
                return {
                    bodyBg: body.backgroundColor,
                    bodyBgHasRadial: body.backgroundImage.includes('radial-gradient'),
                    cardBg: cs?.backgroundColor,
                    cardBackdrop: cs?.backdropFilter,
                    cardRadius: cs?.borderRadius,
                }
            }"""
        )
        print("== 登录页 ==")
        print(json.dumps(login, ensure_ascii=False, indent=2))

        page.fill('input[placeholder="用户名"]', "admin")
        page.fill('input[placeholder="密码"]', "admin123")
        page.click('button:has-text("进入系统")')
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2500)

        main = page.evaluate(
            """() => {
                const siders = document.querySelectorAll('.ant-layout-sider')
                const content = document.querySelector('.ant-layout-content')
                const styles = (el) =>
                    el ? { bg: getComputedStyle(el).backgroundColor, backdrop: getComputedStyle(el).backdropFilter } : null
                return {
                    siderLeft: styles(siders[0]),
                    siderRight: styles(siders[1]),
                    content: styles(content),
                    sessionItems: document.querySelectorAll('.session-item').length,
                    hasSqlBlock: !!document.querySelector('.ant-layout pre'),
                    segmented: [...document.querySelectorAll('.ant-segmented-item-label')].map((e) => e.textContent),
                    canvases: document.querySelectorAll('canvas').length,
                }
            }"""
        )
        print("== 主界面 ==")
        print(json.dumps(main, ensure_ascii=False, indent=2))

        pixels = page.evaluate(
            """() => {
                const siders = document.querySelectorAll('.ant-layout-sider')
                const canvas = siders[1]?.querySelector('canvas')
                if (!canvas) return { found: false }
                const ctx = canvas.getContext('2d')
                const w = Math.min(canvas.width, 300)
                const h = Math.min(canvas.height, 300)
                const data = ctx.getImageData(0, 0, w, h).data
                let nonBlank = 0
                for (let i = 3; i < data.length; i += 40) if (data[i] > 0) nonBlank++
                return { found: true, width: canvas.width, height: canvas.height, nonBlank }
            }"""
        )
        print("== 图表画布（种子会话折线图） ==")
        print(json.dumps(pixels, ensure_ascii=False, indent=2))

        page.fill("textarea", "各品类销售额占比")
        page.keyboard.press("Enter")
        page.wait_for_timeout(6000)
        flow = page.evaluate(
            """() => {
                const texts = [...document.querySelectorAll('.ant-layout-content .ant-typography')]
                    .map((e) => e.textContent).join(' ')
                return {
                    answerRendered: texts.includes('数码家电'),
                    tableRows: document.querySelectorAll('.ant-layout-content .ant-table-row').length,
                }
            }"""
        )
        print("== 提问后（饼图流程） ==")
        print(json.dumps(flow, ensure_ascii=False, indent=2))

        print("== 控制台错误 ==")
        print("\n".join(errors) if errors else "(无)")

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
