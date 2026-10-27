"""量真正的技术指标：能不能把棋盘清干净。

上一轮数据证明"得分"跟操作水平几乎无关（贪心和随机乱点得分重合），因为只要
一直点到最后没有可消的团，总分基本由棋盘决定。真正区分水平的是**剩下多少块**
——会玩的人能把同色块并成大团消掉，乱点的人会留一堆消不动的孤块。

所以每个波次的目标应该是"剩余块数 <= 限额"，而不是"得分 >= 目标"。

这里量的是：以贪心解剩余块数为锚点，另外两种解法比它多剩多少块。
  多剩 0 块   = 和贪心一样干净（上限，人类很难达到）
  多剩 N 块   = 就是 slack 该取多大才能"放过会玩的人、卡住乱点的人"
"""
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8765/?dev=1"
TRIALS = 40
WAVES = 14

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    page = browser.new_context(
        viewport={"width": 390, "height": 844}, device_scale_factor=2,
        is_mobile=True, has_touch=True,
    ).new_page()
    page.goto(URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(500)

    rows = page.evaluate(
        """([WAVES, TRIALS]) => {
        const sh = window.__shatter, S = sh.S;
        let seed = 5150;
        const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);

        const snap = () => S.cols.map(col => col.map(t => t.color));
        const restore = s => {
            S.cols = s.map((col, c) => col.map((color, i) => ({
                color, py: S.boardY + (sh.ROWS - 1 - i) * S.tile, vy: 0, squash: 0 })));
        };
        const play = pick => {
            let guard = 0;
            while (guard++ < 600) {
                const gs = sh.allGroups();
                if (!gs.length) break;
                const g = pick(gs);
                const kill = {};
                for (const [c, i] of g) (kill[c] || (kill[c] = [])).push(i);
                for (const c in kill) {
                    const ks = new Set(kill[c]);
                    S.cols[c] = S.cols[c].filter((_, i) => !ks.has(i));
                }
            }
            return S.cols.reduce((a, c) => a + c.length, 0);
        };

        const pickers = {
            greedy: () => sh.bestGroup(),
            half: gs => {
                const s = gs.slice().sort((a, b) => b.length - a.length);
                const pool = s.slice(0, Math.max(1, Math.ceil(s.length * 0.5)));
                return pool[(rnd() * pool.length) | 0];
            },
            rand: gs => gs[(rnd() * gs.length) | 0],
        };

        const med = a => { const b = a.slice().sort((x, y) => x - y); return b[b.length >> 1]; };
        const total = sh.COLS * sh.ROWS;

        const out = [];
        for (let wave = 1; wave <= WAVES; wave++) {
            const L = { greedy: [], half: [], rand: [] };
            for (let t = 0; t < TRIALS; t++) {
                S.wave = wave; S.score = 0; S.waveScore = 0;
                sh.spawnWave(false);
                const base = snap();
                for (const k in pickers) {
                    restore(base);
                    L[k].push(play(pickers[k]));
                }
            }
            const g = med(L.greedy);
            out.push({
                wave, colors: sh.colorsFor(wave), total,
                greedy: g, half: med(L.half), rand: med(L.rand),
                dHalf: med(L.half) - g, dRand: med(L.rand) - g,
            });
        }
        return out;
    }""",
        [WAVES, TRIALS],
    )
    browser.close()

print(f"{'波':>3} {'色':>3} {'总块':>5} {'认真剩余':>9} {'会玩剩余':>9} {'乱点剩余':>9} "
      f"{'会玩多剩':>9} {'乱点多剩':>9}")
print("-" * 78)
for r in rows:
    print(f"{r['wave']:>3} {r['colors']:>3} {r['total']:>5} {r['greedy']:>9} "
          f"{r['half']:>9} {r['rand']:>9} {r['dHalf']:>+9} {r['dRand']:>+9}")

print()
dh = [r["dHalf"] for r in rows]
dr = [r["dRand"] for r in rows]
print(f"会玩多剩: 最小 {min(dh):+d}  中位 {sorted(dh)[len(dh)//2]:+d}  最大 {max(dh):+d}")
print(f"乱点多剩: 最小 {min(dr):+d}  中位 {sorted(dr)[len(dr)//2]:+d}  最大 {max(dr):+d}")
print()
print("=> slack 取在两者之间，就能'放过会玩的人、卡住乱点的人'")
print(f"   建议 slack 随波次收紧，从 {max(1, min(dr) - 1)} 收到 {max(0, max(dh)) } 附近")
