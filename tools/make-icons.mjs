// 生成 PWA 图标 —— 不依赖任何第三方库，PNG 由 Node 内置 zlib 手写编码。
// 用法: node tools/make-icons.mjs
import { deflateSync } from 'node:zlib';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SS = 4; // 超采样倍数，用来做抗锯齿

/* ---------- 颜色 ---------- */
const hex = h => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
const BG_TOP = hex('#241A47'), BG_BOT = hex('#0A0812');
const HUES = {
  rose: { base: '#FF4D6D', light: '#FF93A8' },
  sky:  { base: '#38BDF8', light: '#8ADBFC' },
  lime: { base: '#4ADE80', light: '#96EFB4' },
  iris: { base: '#A78BFA', light: '#CDBCFD' },
};
const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];

/* ---------- 画布 ---------- */
const canvas = size => ({ size, px: new Float64Array(size * size * 3) });

// 在 bbox 内逐像素判断，命中则用 colorAt(x,y) 上色
function paint(cv, x0, y0, w, h, inside, colorAt) {
  const X0 = Math.max(0, Math.floor(x0)), Y0 = Math.max(0, Math.floor(y0));
  const X1 = Math.min(cv.size, Math.ceil(x0 + w)), Y1 = Math.min(cv.size, Math.ceil(y0 + h));
  for (let y = Y0; y < Y1; y++) {
    for (let x = X0; x < X1; x++) {
      const cx = x + 0.5, cy = y + 0.5;
      if (!inside(cx, cy)) continue;
      const c = colorAt(cx, cy);
      const o = (y * cv.size + x) * 3;
      cv.px[o] = c[0]; cv.px[o + 1] = c[1]; cv.px[o + 2] = c[2];
    }
  }
}

const roundRect = (x0, y0, w, h, r) => (cx, cy) => {
  if (cx < x0 || cx > x0 + w || cy < y0 || cy > y0 + h) return false;
  const dx = Math.min(Math.max(cx, x0 + r), x0 + w - r);
  const dy = Math.min(Math.max(cy, y0 + r), y0 + h - r);
  return (cx - dx) ** 2 + (cy - dy) ** 2 <= r * r;
};
const circle = (ox, oy, r) => (cx, cy) => (cx - ox) ** 2 + (cy - oy) ** 2 <= r * r;

// 背景色（用于"挖掉"已画好的部分，做出缺口）
const bgAt = (_x, y, N) => mix(BG_TOP, BG_BOT, y / N);
const erase = (cv, N, x, y, w, h, inside) => paint(cv, x, y, w, h, inside, (px, py) => bgAt(px, py, N));

/* ---------- 元素 ---------- */
// 一块带切面高光与底部暗边的彩色石块
function drawTile(cv, x, y, s, hue) {
  const r = s * 0.21;
  paint(cv, x, y, s, s, roundRect(x, y, s, s, r), (_cx, cy) =>
    mix(hex(hue.light), hex(hue.base), Math.min(1, Math.max(0, (cy - y) / s) * 1.8)));

  // 顶部高光：贴边的一条细亮线，读作切面而不是进度条
  const hl = mix(hex(hue.light), [255, 255, 255], 0.5);
  paint(cv, x, y, s, s, roundRect(x + s * 0.13, y + s * 0.095, s * 0.74, s * 0.052, s * 0.026), () => hl);

  // 底部暗边：压出体积
  const shade = mix(hex(hue.base), [0, 0, 0], 0.42);
  paint(cv, x, y, s, s, roundRect(x + s * 0.13, y + s * 0.855, s * 0.74, s * 0.06, s * 0.03), () => shade);
}

// 一块小碎块
function drawChunk(cv, cx, cy, s, hue, lum) {
  const col = mix(hex(hue.light), hex(hue.base), lum);
  paint(cv, cx - s, cy - s, s * 2, s * 2, roundRect(cx - s / 2, cy - s / 2, s, s, s * 0.26), () => col);
  paint(cv, cx - s, cy - s, s * 2, s * 2,
    roundRect(cx - s * 0.37, cy - s * 0.36, s * 0.74, s * 0.10, s * 0.05),
    () => mix(col, [255, 255, 255], 0.4));
}

function render(size, maskable) {
  const N = size * SS;
  const cv = canvas(N);

  paint(cv, 0, 0, N, N, () => true, (x, y) => bgAt(x, y, N));

  const k = maskable ? 0.66 : 0.80;
  const grid = N * k;
  const gap = grid * 0.062;
  const tile = (grid - gap) / 2;
  const ox = (N - grid) / 2, oy = (N - grid) / 2;

  const c0x = ox, c1x = ox + tile + gap;
  const r0y = oy, r1y = oy + tile + gap;

  // 三块完好
  drawTile(cv, c0x, r0y, tile, HUES.rose);
  drawTile(cv, c0x, r1y, tile, HUES.sky);
  drawTile(cv, c1x, r1y, tile, HUES.lime);

  // 右上角那块正在碎开：缺口全部啃在朝外的轮廓边缘（顶边/右边/右上角），
  // 这样读作"碎裂"而不是"打孔"，也不会啃到相邻的绿色块。
  drawTile(cv, c1x, r0y, tile, HUES.iris);
  const bites = [
    [c1x + tile * 0.30, r0y, tile * 0.235],                // 顶边
    [c1x + tile, r0y + tile * 0.34, tile * 0.255],         // 右边
    [c1x + tile * 0.97, r0y + tile * 0.02, tile * 0.21],   // 右上角
  ];
  for (const [bx, by, br] of bites) erase(cv, N, bx - br, by - br, br * 2, br * 2, circle(bx, by, br));

  // 飞散的碎块：绕象限中心一圈，填满留白
  const cx1 = c1x + tile / 2, cy1 = r0y + tile / 2;
  const bits = [
    [0.98, -0.72, 0.235], [1.02, 0.06, 0.20], [0.62, -1.00, 0.175],
    [0.16, -0.92, 0.145], [-0.62, -0.70, 0.20], [0.72, 0.86, 0.185],
    [0.24, 1.00, 0.135], [1.06, 0.62, 0.115], [-0.30, 0.96, 0.10],
  ];
  bits.forEach(([dx, dy, ds], i) =>
    drawChunk(cv, cx1 + dx * tile * 0.5, cy1 + dy * tile * 0.5, ds * tile, HUES.iris, (i % 4) / 4 * 0.75));

  // 超采样降采样
  const out = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let r = 0, g = 0, b = 0;
      for (let sy = 0; sy < SS; sy++) {
        for (let sx = 0; sx < SS; sx++) {
          const o = ((y * SS + sy) * N + (x * SS + sx)) * 3;
          r += cv.px[o]; g += cv.px[o + 1]; b += cv.px[o + 2];
        }
      }
      const n = SS * SS, o = (y * size + x) * 4;
      out[o] = Math.round(r / n); out[o + 1] = Math.round(g / n);
      out[o + 2] = Math.round(b / n); out[o + 3] = 255;
    }
  }
  return out;
}

/* ---------- PNG 编码 ---------- */
const CRC_TABLE = (() => {
  const t = new Int32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c;
  }
  return t;
})();

function crc32(buf) {
  let c = -1;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ -1) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
}

function encodePNG(rgba, size) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8;   // 位深
  ihdr[9] = 6;   // RGBA
  const raw = Buffer.alloc(size * (size * 4 + 1));
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0; // filter: None
    rgba.copy(raw, y * (size * 4 + 1) + 1, y * size * 4, (y + 1) * size * 4);
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

/* ---------- 输出 ---------- */
for (const [name, size, maskable] of [
  ['icon-192.png', 192, false],
  ['icon-512.png', 512, false],
  ['icon-maskable-512.png', 512, true],
]) {
  const png = encodePNG(render(size, maskable), size);
  writeFileSync(join(OUT, name), png);
  console.log(`${name.padEnd(24)} ${size}x${size}  ${(png.length / 1024).toFixed(1)} KB`);
}
