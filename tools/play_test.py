"""《碎》的手机端交互验证：iPhone 视口 + 真实触摸事件，走一遍完整操作路径。"""
import sys
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/?dev=1"
OUT = "tools/shots"

failures = []
def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"   {detail}" if detail else ""))
    if not cond:
        failures.append(f"{name} {detail}")


def cell_point(page, col, idx):
    """把棋盘格 (col, idx) 换算成页面坐标"""
    return page.evaluate(
        """([c, i]) => {
            const sh = window.__shatter, S = sh.S;
            const r = document.getElementById('board').getBoundingClientRect();
            const t = sh.tileAt(c, i);
            return { x: r.left + S.boardX + c * S.tile + S.tile / 2,
                     y: r.top + t.py + S.tile / 2, n: sh.groupAt(c, i).length };
        }""",
        [col, idx],
    )


def state(page):
    return page.evaluate(
        """() => { const S = window.__shatter.S;
            return { score: S.score, wave: S.wave, combo: S.combo, phase: S.phase,
                     tiles: S.cols.reduce((a, c) => a + c.length, 0) }; }"""
    )


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844},      # iPhone 14 逻辑分辨率
        device_scale_factor=3,
        is_mobile=True,
        has_touch=True,
        user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"),
    )
    page = ctx.new_page()
    errors, logs = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))

    print("\n== 加载 ==")
    page.goto(URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(700)

    check("无 JS 报错", not errors, "; ".join(errors[:3]))
    check("棋盘 8 列", page.evaluate("window.__shatter.S.cols.length") == 8)
    full = page.evaluate("window.__shatter.COLS * window.__shatter.ROWS")
    rows = page.evaluate("window.__shatter.ROWS")
    print(f"        （本机算出 {rows} 行，满盘 {full} 块）")
    check("开局满盘", state(page)["tiles"] == full)
    check("棋盘高度吃满可用区", page.evaluate(
        "window.__shatter.S.boardH / document.getElementById('stage').clientHeight") > 0.90)
    check("竖屏无横向溢出", page.evaluate(
        "document.documentElement.scrollWidth <= window.innerWidth + 1"))
    check("有可消的团", page.evaluate("window.__shatter.allGroups().length > 0"))
    check("开局连击条是暗的", not page.evaluate(
        "document.getElementById('track').classList.contains('hot')"))
    page.screenshot(path=f"{OUT}/01-start.png")

    print("\n== 触摸消除 ==")
    g = page.evaluate("window.__shatter.bestGroup()")
    pt = cell_point(page, g[0][0], g[0][1])
    page.touchscreen.tap(pt["x"], pt["y"])
    page.wait_for_timeout(120)
    st = state(page)
    check("点一团后得分上涨", st["score"] > 0, f"score={st['score']}")
    check("该团确实 >=2 块", pt["n"] >= 2, f"n={pt['n']}")
    check("第一下倍率为 1", st["combo"] == 1)
    check("消除块数已减少", st["tiles"] < full, f"tiles={st['tiles']}")

    # 连点两下，触发连击倍率与音阶升调
    for _ in range(2):
        grp = page.evaluate("window.__shatter.bestGroup()")
        if not grp:
            break
        q = cell_point(page, grp[0][0], grp[0][1])
        page.touchscreen.tap(q["x"], q["y"])
        page.wait_for_timeout(200)

    st = state(page)
    check("连击倍率累加", st["combo"] >= 2, f"combo={st['combo']}")
    check("连击大字已显示", page.locator("#combo").inner_text().startswith("×"))
    check("连击条亮起", page.evaluate(
        "document.getElementById('track').classList.contains('hot')"))
    check("连击条文字正确", "连击 ×" in page.locator("#combos").inner_text(),
          page.locator("#combos").inner_text())
    w = page.evaluate("document.getElementById('fill').style.width")
    check("连击条有进度", w not in ("", "0%", "0.0%"), f"width={w}")
    page.screenshot(path=f"{OUT}/02-combo.png")

    print("\n== 连击会过期 ==")
    page.wait_for_timeout(1800)          # 超过 1.5s 窗口
    check("连击归零", state(page)["combo"] == 0)
    check("连击条熄灭", not page.evaluate(
        "document.getElementById('track').classList.contains('hot')"))
    check("连击条文案复位", page.locator("#combos").inner_text() == "连击 —")

    print("\n== 互动元件 ==")
    page.click("#btn-hint")
    page.wait_for_timeout(80)
    check("提示高亮生效", page.evaluate("window.__shatter.S.hintT") > 0)

    muted0 = page.evaluate("window.__shatter.S.muted")
    page.click("#btn-sound")
    page.wait_for_timeout(60)
    check("静音开关翻转", page.evaluate("window.__shatter.S.muted") != muted0)
    check("按钮文案同步", ("关" if not muted0 else "开") in page.locator("#btn-sound").inner_text())
    page.click("#btn-sound")  # 恢复

    print("\n== 打穿一波 -> 自动进入下一波（无失败条件）==")
    w0 = state(page)["wave"]
    page.click("#btn-hint")           # 故意在换波前点亮提示，验证它不会残留到新棋盘
    page.wait_for_timeout(80)
    page.evaluate("window.__shatter.autoSolve(600)")
    page.wait_for_function(
        "() => window.__shatter.S.phase === 'play' && !window.__shatter.S.settling",
        timeout=10000)
    st = state(page)
    check("波次推进", st["wave"] > w0, str(st))
    check("换波后提示不残留", page.evaluate("window.__shatter.S.hint") is None)
    check("换波后提示计时清零", page.evaluate("window.__shatter.S.hintT") == 0)
    check("新一波棋盘已铺满", st["tiles"] == full, f"tiles={st['tiles']}")
    check("回到可玩状态", st["phase"] == "play", f"phase={st['phase']}")
    page.wait_for_timeout(400)
    page.screenshot(path=f"{OUT}/03-next-wave.png")

    print("\n== 连续推 4 波 ===")
    for _ in range(4):
        page.wait_for_function(
            "() => window.__shatter.S.phase === 'play' && !window.__shatter.S.settling",
            timeout=10000)
        page.evaluate("window.__shatter.autoSolve(600)")
        page.wait_for_function("() => window.__shatter.S.phase === 'waveclear'", timeout=10000)
    page.wait_for_function(
        "() => window.__shatter.S.phase === 'play' && !window.__shatter.S.settling",
        timeout=10000)
    st = state(page)
    check("波次持续累加", st["wave"] >= w0 + 5, f"wave={st['wave']}")
    check("一直在可玩状态", st["phase"] == "play", f"phase={st['phase']}")
    check("棋盘始终铺满", st["tiles"] == full, f"tiles={st['tiles']}")
    check("颜色随波次变多", page.evaluate("window.__shatter.colorsFor(window.__shatter.S.wave)") >= 4,
          f"colors={page.evaluate('window.__shatter.colorsFor(window.__shatter.S.wave)')}")
    check("最高分已落盘", page.evaluate(
        "+(localStorage.getItem('shatter.best') || 0)") >= st["score"])
    check("HUD 最高分跟上", page.locator("#best").inner_text() != "0")

    print("\n== 重开 ==")
    page.click("#btn-restart")
    page.wait_for_timeout(300)
    st = state(page)
    check("分数归零", st["score"] == 0, str(st))
    check("回到第 1 波", st["wave"] == 1)
    check("棋盘重置", st["tiles"] == full)
    check("HUD 同步", page.locator("#score").inner_text() == "0")
    check("最高分保留", page.locator("#best").inner_text() != "0")

    print("\n== 第二次加载（service worker）==")
    err2 = []
    page.on("pageerror", lambda e: err2.append(str(e)))
    page.reload()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(700)
    check("重载后无报错", not err2, "; ".join(err2[:3]))
    check("重载后仍可玩", page.evaluate("window.__shatter.allGroups().length > 0"))
    check("service worker 已注册", page.evaluate(
        "navigator.serviceWorker.getRegistrations().then(r => r.length > 0)"))
    check("最高分跨会话保留", page.locator("#best").inner_text() != "0")
    page.screenshot(path=f"{OUT}/04-after-reload.png")

    if errors:
        print("\nJS 错误:")
        for e in errors:
            print("   ", e)
    if logs:
        print("\n控制台输出:")
        for l in logs[:15]:
            print("   ", l)

    browser.close()

print("\n" + "=" * 46)
if failures:
    print(f"{len(failures)} 项未通过:")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("全部通过")
