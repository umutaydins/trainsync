// Renders the PWA icons in public/icons from the same shape as app/icon.svg (accent square with a
// white rising line), without an image library: a tiny rasterizer with 4x4 supersampling and a
// PNG encoder on node:zlib. Run after changing the icon: `node scripts/gen-icons.mjs`.
import { mkdirSync, writeFileSync } from "node:fs";
import { deflateSync } from "node:zlib";

const ACCENT = [0x2f, 0x6f, 0xde];
const WHITE = [0xff, 0xff, 0xff];
const LINE = [
  [7, 21],
  [13, 13],
  [18, 18],
  [25, 9],
];
const STROKE = 3;

function distanceToSegment(px, py, [ax, ay], [bx, by]) {
  const dx = bx - ax;
  const dy = by - ay;
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function insideRoundedRect(x, y, size, radius) {
  const cx = Math.min(Math.max(x, radius), size - radius);
  const cy = Math.min(Math.max(y, radius), size - radius);
  return Math.hypot(x - cx, y - cy) <= radius;
}

/**
 * `maskable`: full-bleed square (the OS applies its own mask) with the line scaled into the 80 %
 * safe zone; otherwise the rounded square of icon.svg on a transparent background.
 */
function render(size, maskable) {
  const scale = size / 32;
  const lineScale = maskable ? 0.72 : 1;
  const offset = maskable ? (32 - 32 * lineScale) / 2 : 0;
  const samples = 4;
  const pixels = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let bg = 0;
      let fg = 0;
      for (let sy = 0; sy < samples; sy++) {
        for (let sx = 0; sx < samples; sx++) {
          const u = (x + (sx + 0.5) / samples) / scale;
          const v = (y + (sy + 0.5) / samples) / scale;
          if (!maskable && !insideRoundedRect(u, v, 32, 8)) continue;
          bg++;
          const lu = (u - offset) / lineScale;
          const lv = (v - offset) / lineScale;
          let d = Infinity;
          for (let i = 0; i < LINE.length - 1; i++) d = Math.min(d, distanceToSegment(lu, lv, LINE[i], LINE[i + 1]));
          if (d <= STROKE / 2) fg++;
        }
      }
      const total = samples * samples;
      const i = (y * size + x) * 4;
      const mix = bg === 0 ? 0 : fg / bg;
      for (let c = 0; c < 3; c++) pixels[i + c] = Math.round(ACCENT[c] * (1 - mix) + WHITE[c] * mix);
      pixels[i + 3] = Math.round((bg / total) * 255);
    }
  }
  return png(size, pixels);
}

const CRC_TABLE = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(buffer) {
  let c = 0xffffffff;
  for (const byte of buffer) c = CRC_TABLE[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, crc]);
}

function png(size, rgba) {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header[8] = 8; // bit depth
  header[9] = 6; // RGBA
  const rows = Buffer.alloc(size * (size * 4 + 1));
  for (let y = 0; y < size; y++) rgba.copy(rows, y * (size * 4 + 1) + 1, y * size * 4, (y + 1) * size * 4);
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(rows, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

const out = new URL("../public/icons/", import.meta.url);
mkdirSync(out, { recursive: true });
const files = {
  "icon-192.png": render(192, false),
  "icon-512.png": render(512, false),
  "icon-maskable-512.png": render(512, true),
  // iOS draws its own rounded corners and ignores transparency: use the full-bleed variant.
  "apple-touch-icon.png": render(180, true),
};
for (const [name, data] of Object.entries(files)) {
  writeFileSync(new URL(name, out), data);
  console.log(`gen-icons: public/icons/${name} (${data.length} bytes)`);
}
