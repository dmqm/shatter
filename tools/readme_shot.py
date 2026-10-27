"""生成 README 用的小截图（1x，约 60KB）。"""
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/?dev=1"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    page = browser.new_context(
        viewport={"width": 390, "height": 844}, device_scale_factor=1,
        is_mobile=True, has_touch=True,
    ).new_page()
    page.goto(URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(600)

    # 连点几团，凑出一个有连击的、棋盘还没被削光的画面
    for _ in range(3):
        g = page.evaluate("window.__shatter.bestGroup()")
        if not g:
            break
        pt = page.evaluate(
            """([c, i]) => {
                const sh = window.__shatter, S = sh.S;
                const r = document.getElementById('board').getBoundingClientRect();
                const t = sh.tileAt(c, i);
                return { x: r.left + S.boardX + c * S.tile + S.tile / 2,
                         y: r.top + t.py + S.tile / 2 };
            }""",
            [g[0][0], g[0][1]],
        )
        page.touchscreen.tap(pt["x"], pt["y"])
        page.wait_for_timeout(230)

    page.wait_for_timeout(120)
    page.screenshot(path="screenshot.png")
    print("screenshot.png  combo =", page.evaluate("window.__shatter.S.combo"))
    browser.close()
