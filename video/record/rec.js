// Screen footage recorder: CDP screencast (high-quality JPEG frames with timestamps) -> CFR 30fps mp4.
// usage: node rec.js live|rel <outName>
const { chromium } = require('/Users/anirudh/.npm/_npx/5e2e484947874241/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const MODE = process.argv[2] || 'live';
const NAME = process.argv[3] || MODE;
const BASE = MODE === 'live' ? 'http://localhost:8000' : 'http://localhost:8766';
const OUT = '/Users/anirudh/Desktop/MultiApp-Ai-Agent-hack/video/assets/footage';
const WORK = `/Users/anirudh/Desktop/MultiApp-Ai-Agent-hack/video/record/work_${NAME}`;
fs.rmSync(WORK, { recursive: true, force: true });
fs.mkdirSync(WORK, { recursive: true });
fs.mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let t0 = 0;
const markers = [];
const mark = (label) => { const t = (Date.now() / 1000) - t0; markers.push({ t: +t.toFixed(2), label }); console.log(`[${t.toFixed(1)}s] ${label}`); };

async function startRec(page) {
  const cdp = await page.context().newCDPSession(page);
  const frames = [];
  let n = 0;
  const pending = [];
  cdp.on('Page.screencastFrame', (f) => {
    const i = n++;
    const file = path.join(WORK, `f${String(i).padStart(6, '0')}.jpg`);
    frames.push({ file, ts: f.metadata.timestamp });
    pending.push(fs.promises.writeFile(file, Buffer.from(f.data, 'base64')));
    cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {});
  });
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 95, maxWidth: 1440, maxHeight: 900, everyNthFrame: 1 });
  return {
    async stop() {
      await cdp.send('Page.stopScreencast').catch(() => {});
      await Promise.all(pending);
      return frames;
    },
  };
}

function encode(frames, endTs, outFile) {
  const lines = ['ffconcat version 1.0'];
  const first = frames[0].ts;
  for (let i = 0; i < frames.length; i++) {
    const next = i + 1 < frames.length ? frames[i + 1].ts : endTs;
    const d = Math.max(0.001, next - frames[i].ts);
    lines.push(`file '${frames[i].file}'`);
    lines.push(`duration ${d.toFixed(4)}`);
  }
  lines.push(`file '${frames[frames.length - 1].file}'`);
  fs.writeFileSync(path.join(WORK, 'list.txt'), lines.join('\n'));
  console.log(`frames=${frames.length} span=${(endTs - first).toFixed(1)}s avgfps=${(frames.length / (endTs - first)).toFixed(1)}`);
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', path.join(WORK, 'list.txt'),
    '-vf', 'fps=30,format=yuv420p', '-c:v', 'libx264', '-preset', 'medium', '-crf', '14', '-r', '30', '-movflags', '+faststart', outFile], { stdio: 'inherit' });
}

async function smoothScroll(page, sel, to, ms) {
  await page.evaluate(({ sel, to, ms }) => new Promise((res) => {
    const el = document.querySelector(sel);
    if (!el) return res();
    const from = el.scrollTop;
    const target = typeof to === 'number' ? to : Math.min(el.scrollHeight - el.clientHeight, from + (document.querySelector(to)?.getBoundingClientRect().top || 0) - el.getBoundingClientRect().top - 12);
    const start = performance.now();
    const ease = (x) => (x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2);
    const tick = (now) => {
      const p = Math.min(1, (now - start) / ms);
      el.scrollTop = from + (target - from) * ease(p);
      if (p < 1) requestAnimationFrame(tick); else res();
    };
    requestAnimationFrame(tick);
  }), { sel, to, ms });
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, name) });
  mark(`screenshot ${name}`);
}

async function planMarco(page) {
  await page.evaluate(() => {
    const s = document.querySelector('#manual-tech');
    const o = Array.from(s.options).find((x) => /marco/i.test(x.textContent));
    s.value = o.value; s.dispatchEvent(new Event('change', { bubbles: true }));
    const sp = document.querySelector('#manual-span');
    sp.value = '0-1440'; sp.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await sleep(700);
  await page.click('#manual-btn');
  mark('clicked Plan (Marco Diaz, All day)');
  await page.waitForSelector('#actionbar .approve[data-action="approve"]', { timeout: 90000 });
  mark('plan ready');
}

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--hide-scrollbars', '--force-color-profile=srgb'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.on('pageerror', (e) => console.log('PAGEERROR', e.message));
  // The ledger keeps earlier plans and the UI auto-selects the newest on load. Hide plans created
  // before this take so the board opens on the fresh morning (Before, every job on its original tech).
  const START = Date.now() / 1000;
  await page.route(/\/api\/(state|plans)(\?.*)?$/, async (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    try {
      const resp = await route.fetch();
      let body = await resp.json();
      const keep = (arr) => arr.filter((p) => !p.created_at || p.created_at >= START - 2);
      if (Array.isArray(body)) body = keep(body);
      else if (body && Array.isArray(body.plans)) body.plans = keep(body.plans);
      await route.fulfill({ response: resp, json: body });
    } catch (e) { try { await route.continue(); } catch (_) {} }
  });
  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.waitForSelector('#layer .job', { timeout: 60000 });
  await sleep(2500);
  await sleep(2500);
  // move the mouse off-canvas so no hover tooltips appear
  await page.mouse.move(1439, 899);
  const rec = await startRec(page);
  t0 = Date.now() / 1000;
  mark('recording start (Before state)');

  if (MODE === 'live') {
    await sleep(1500);
    await shot(page, 'before.png');
    await sleep(8000); // S2: tools, reads Sheets + Calendar
    await planMarco(page);
    await sleep(6500); // vans drive to reassigned jobs
    await shot(page, 'after.png');
    await sleep(1500);
    await page.keyboard.press('b'); mark('B -> Before');
    await sleep(2500);
    await page.keyboard.press('b'); mark('B -> After');
    await sleep(3000);
    await page.keyboard.press('m'); mark('M map open');
    await sleep(2000);
    await shot(page, 'map.png');
    await sleep(2200);
    await page.keyboard.press('m'); mark('M map close');
    await sleep(1500);
    // S4: show changes and the writes grouped by app
    await smoothScroll(page, '#plan-scroll', 99999, 11000); mark('scrolled plan panel to bottom');
    await sleep(1500);
    await smoothScroll(page, '#plan-scroll', 0, 3000); mark('scrolled back to top');
    await sleep(1200);
    await shot(page, 'approve.png');
    await page.click('#actionbar .approve[data-action="approve"]'); mark('clicked Approve');
    await page.waitForSelector('#actionbar .ab-done', { timeout: 180000 });
    mark('writes done (ab-done visible)');
    await sleep(900);
    await shot(page, 'verified.png');
    await sleep(6000); // linger on 36/36 burst
    await smoothScroll(page, '#plan-scroll', '.trace', 4000); mark('scrolled to trace');
    await sleep(1500);
    await shot(page, 'trace.png');
    await sleep(5500);
  } else {
    await sleep(1200);
    await planMarco(page);
    await sleep(2500);
    await page.keyboard.press('l'); mark('L lab open');
    await page.waitForSelector('#lab-grid [data-lab="calcrash"]', { timeout: 10000 });
    await sleep(1600);
    await page.click('#lab-grid [data-lab="calcrash"]'); mark('armed calcrash');
    await sleep(1800);
    await page.keyboard.press('Escape'); mark('lab closed');
    await sleep(800);
    await page.click('#actionbar .approve[data-action="approve"]'); mark('clicked Approve');
    await page.waitForSelector('#actionbar .approve.resume', { timeout: 60000 });
    mark('crashed');
    await sleep(1800);
    await shot(page, 'crash.png');
    await sleep(1500);
    await page.click('#actionbar .approve.resume'); mark('clicked Resume');
    await page.waitForSelector('#actionbar .ab-done', { timeout: 60000 });
    mark('resumed done');
    await sleep(1000);
    await shot(page, 'resumed.png');
    await sleep(3500);
  }

  mark('recording stop');
  const endTs = Date.now() / 1000;
  const frames = await rec.stop();
  await browser.close();
  // screencast timestamps are epoch seconds; guard in case they are not
  const lastTs = frames[frames.length - 1].ts;
  const end = Math.abs(endTs - lastTs) < 120 ? endTs : lastTs + 1;
  const outFile = path.join(OUT, `${NAME}.mp4`);
  encode(frames, end, outFile);
  fs.writeFileSync(path.join(OUT, `${NAME}.markers.json`), JSON.stringify({ firstFrameTs: frames[0].ts, t0, markers }, null, 2));
  console.log('wrote', outFile);
})().catch((e) => { console.error('FAILED', e); process.exit(1); });
