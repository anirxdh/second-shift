// Fullscreen 1920x1080 footage recorder with injected cursor dot + click ripple.
// CDP screencast (JPEG q95, timestamped) -> CFR 30fps H.264 CRF 18.
// usage: node rec3.js live|rel
const { chromium } = require('/Users/anirudh/.npm/_npx/5e2e484947874241/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const MODE = process.argv[2] || 'live';
const NAME = MODE === 'live' ? 'live' : 'reliability';
const BASE = MODE === 'live' ? 'http://localhost:8000' : 'http://localhost:8766';
const OUT = '/Users/anirudh/Desktop/MultiApp-Ai-Agent-hack/video/assets/footage4';
const WORK = `/Users/anirudh/Desktop/MultiApp-Ai-Agent-hack/video/record/work4_${NAME}`;
const W = 1920, H = 1080;
fs.rmSync(WORK, { recursive: true, force: true });
fs.mkdirSync(WORK, { recursive: true });
fs.mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const markers = [];
const clicks = [];
const mark = (label) => { const e = Date.now() / 1000; markers.push({ epoch: e, label }); console.log(`[${new Date().toISOString().slice(11, 19)}] ${label}`); };

const CURSOR_JS = `(() => {
  const install = () => {
    if (document.getElementById('__cur')) return;
    const st = document.createElement('style');
    st.textContent = \`
#__cur{position:fixed;inset:0;width:100vw;height:100vh;max-width:none;max-height:none;margin:0;padding:0;border:0;background:transparent;pointer-events:none;overflow:visible;z-index:2147483647;display:block}
#__dot{position:absolute;left:0;top:0;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;background:#D97757;border:2px solid #F0EEE6;box-shadow:0 0 0 1px rgba(20,20,19,.6),0 3px 10px rgba(0,0,0,.45);transition:transform .5s cubic-bezier(.22,.9,.3,1), scale .12s ease;will-change:transform}
#__dot.down{scale:.7}
.__rip{position:absolute;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;border:3px solid #D97757;box-shadow:0 0 14px rgba(217,119,87,.65);animation:__rip .6s cubic-bezier(.2,.8,.3,1) forwards}
@keyframes __rip{from{transform:scale(1);opacity:.95}to{transform:scale(4.4);opacity:0}}\`;
    document.head.appendChild(st);
    const layer = document.createElement('div'); layer.id = '__cur';
    try { layer.popover = 'manual'; } catch (e) {}
    const dot = document.createElement('div'); dot.id = '__dot';
    layer.appendChild(dot);
    document.body.appendChild(layer);
    const raise = () => { try { if (layer.matches(':popover-open')) layer.hidePopover(); layer.showPopover(); } catch (e) {} };
    window.__raiseCursor = raise;
    raise();
    dot.style.transform = 'translate(' + (innerWidth * 0.62) + 'px,' + (innerHeight * 0.55) + 'px)';
    addEventListener('mousemove', (e) => { dot.style.transform = 'translate(' + e.clientX + 'px,' + e.clientY + 'px)'; }, true);
    addEventListener('mousedown', (e) => { dot.classList.add('down'); const r = document.createElement('div'); r.className = '__rip'; r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px'; layer.appendChild(r); setTimeout(() => r.remove(), 800); }, true);
    addEventListener('mouseup', () => dot.classList.remove('down'), true);
    new MutationObserver((ms) => { for (const m of ms) if (m.target.tagName === 'DIALOG' && m.target.open) setTimeout(raise, 0); })
      .observe(document.documentElement, { attributes: true, subtree: true, attributeFilter: ['open'] });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install); else install();
})();`;

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
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 95, maxWidth: W, maxHeight: H, everyNthFrame: 1 });
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
    '-vf', `scale=${W}:${H}:flags=lanczos,fps=30,format=yuv420p`, '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-r', '30', '-movflags', '+faststart', outFile], { stdio: 'inherit' });
}

async function smoothScroll(page, sel, to, ms) {
  await page.evaluate(({ sel, to, ms }) => new Promise((res) => {
    const el = document.querySelector(sel);
    if (!el) return res();
    const from = el.scrollTop;
    const target = typeof to === 'number' ? Math.min(to, el.scrollHeight - el.clientHeight) : Math.min(el.scrollHeight - el.clientHeight, from + (document.querySelector(to)?.getBoundingClientRect().top || 0) - el.getBoundingClientRect().top - 12);
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

let shotN = 0;
async function shot(page, name) {
  shotN++;
  const file = `${NAME}_${String(shotN).padStart(2, '0')}_${name}.png`;
  await page.screenshot({ path: path.join(OUT, file) });
  mark(`screenshot ${file}`);
}

// glide the (CSS-eased) cursor dot to an element, then optionally click with a ripple
async function glide(page, sel, { click = true, dx = 0, dy = 0, wait = 600, label = sel } = {}) {
  const el = page.locator(sel).first();
  const b = await el.boundingBox();
  if (!b) throw new Error(`no box for ${sel}`);
  const x = Math.round(b.x + b.width / 2 + dx), y = Math.round(b.y + b.height / 2 + dy);
  await page.mouse.move(x, y);
  await sleep(wait);
  if (click) { clicks.push({ epoch: Date.now() / 1000, x, y, label }); await page.mouse.down(); await sleep(110); await page.mouse.up(); }
}
async function assertHeader(page, take) {
  const r = await page.evaluate(() => {
    const b = document.querySelector('#whatif-btn');
    const h = document.querySelector('.col-board h2');
    if (!b || !h) return { ok: false, why: 'missing element', b: !!b, h: !!h };
    const pos = getComputedStyle(b).position;
    const bb = b.getBoundingClientRect();
    const rg = document.createRange(); rg.selectNodeContents(h); const tb = rg.getBoundingClientRect();
    const overlap = !(bb.left >= tb.right || bb.right <= tb.left || bb.top >= tb.bottom || bb.bottom <= tb.top);
    const ok = pos === 'static' && bb.left >= tb.right && !overlap;
    return { ok, pos, overlap, btn: [bb.left, bb.top, bb.right, bb.bottom].map(Math.round), title: [tb.left, tb.top, tb.right, tb.bottom].map(Math.round) };
  });
  console.log('HEADER CHECK', take, JSON.stringify(r));
  fs.writeFileSync(path.join(OUT, `${NAME}.headercheck.json`), JSON.stringify(r, null, 2));
  if (!r.ok) { console.error('HEADER CHECK FAILED -- aborting take'); process.exit(3); }
}
async function park(page, x, y) { await page.mouse.move(x, y); await sleep(550); }
async function blur(page) { await page.evaluate(() => document.activeElement && document.activeElement.blur && document.activeElement.blur()); }

async function pickTech(page, re) {
  await glide(page, '#manual-tech', { click: false, wait: 650 });
  await page.evaluate((src) => {
    const s = document.querySelector('#manual-tech');
    const o = Array.from(s.options).find((x) => new RegExp(src, 'i').test(x.textContent));
    s.value = o.value; s.dispatchEvent(new Event('change', { bubbles: true }));
  }, re);
  await sleep(500);
}

async function planMarco(page) {
  await pickTech(page, 'marco');
  await glide(page, '#manual-span', { click: false, wait: 550 });
  await page.evaluate(() => { const sp = document.querySelector('#manual-span'); sp.value = '0-1440'; sp.dispatchEvent(new Event('change', { bubbles: true })); });
  await sleep(450);
  mark('picked Marco Diaz, All day');
  await glide(page, '#manual-btn', { label: 'Plan' });
  mark('clicked Plan (Marco Diaz, All day)');
  await page.waitForSelector('#actionbar .approve[data-action="approve"]', { timeout: 120000 });
  mark('plan ready (board animates, vans drive)');
}

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--hide-scrollbars', '--force-color-profile=srgb'] });
  const context = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  await context.addInitScript(CURSOR_JS);
  const page = await context.newPage();
  page.on('pageerror', (e) => console.log('PAGEERROR', e.message));
  // Hide plans created before this take so the board opens on the fresh morning.
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
  await sleep(4000);
  await assertHeader(page, NAME);
  const rec = await startRec(page);
  mark('recording start (Before state, page loaded)');

  if (MODE === 'live') {
    await sleep(1200);
    await shot(page, 'start');
    await sleep(1800);
    await planMarco(page);
    await park(page, 330, 900);
    await sleep(2500);
    await shot(page, 'plan_after');
    await sleep(3000);
    await blur(page);
    await page.keyboard.press('b'); mark('B -> Before');
    await sleep(900);
    await shot(page, 'before');
    await sleep(1100);
    await page.keyboard.press('b'); mark('B -> After (vans drive again)');
    await sleep(2500);
    await shot(page, 'after_again');
    await sleep(2500);
    await page.keyboard.press('m'); mark('M zone map open');
    await sleep(3000);
    await shot(page, 'map');
    await sleep(3000);
    await page.keyboard.press('m'); mark('M zone map close');
    await sleep(1200);
    await glide(page, '#plan-scroll', { click: false, wait: 500 });
    mark('scroll plan panel start');
    await smoothScroll(page, '#plan-scroll', 99999, 5000); mark('plan panel scrolled to bottom');
    await shot(page, 'plan_panel_bottom');
    await sleep(800);
    await smoothScroll(page, '#plan-scroll', 0, 1500); mark('plan panel back to top');
    await sleep(600);
    await shot(page, 'approve_ready');
    await glide(page, '#actionbar .approve[data-action="approve"]', { wait: 700, label: 'Approve' });
    mark('clicked Approve (writes start)');
    await park(page, 330, 900);
    await page.waitForSelector('#actionbar .ab-done', { timeout: 240000 });
    mark('writes done: 36/36 burst');
    await sleep(700);
    await shot(page, 'verified_36');
    await sleep(3000);
    await smoothScroll(page, '#plan-scroll', '.trace', 2500); mark('scrolled to verification trace');
    await sleep(700);
    await shot(page, 'trace');
    await sleep(2300);
    // WHAT-IF
    await pickTech(page, 'wei');
    mark('picked Wei Chen');
    await glide(page, '#whatif-btn', { label: 'What if?' });
    mark('clicked What if?');
    await park(page, 330, 900);
    await page.waitForFunction(() => { const b = document.querySelector('#whatif-btn'); return b && !b.disabled && b.textContent.trim() === 'What if?'; }, null, { timeout: 120000, polling: 200 });
    mark('what-if ready');
    await sleep(2000);
    await shot(page, 'whatif_wei');
    await sleep(3000);
    await glide(page, '#scan-btn', { label: 'Risk scan' });
    mark('clicked Risk scan');
    await page.waitForSelector('#scan-body .scan-table, #scan-body .scan-verdict', { timeout: 120000 });
    mark('risk scan results');
    await page.evaluate(() => window.__raiseCursor && window.__raiseCursor());
    await sleep(2000);
    await shot(page, 'risk_scan');
    await sleep(3000);
    await glide(page, '#scan-dialog form[method="dialog"] button', { label: 'Close risk scan' });
    mark('closed risk scan');
    await sleep(1800);
  } else {
    await sleep(1500);
    await shot(page, 'start');
    await planMarco(page);
    await park(page, 330, 900);
    await sleep(2500);
    await shot(page, 'plan');
    await blur(page);
    await page.keyboard.press('l'); mark('L lab open');
    await page.waitForSelector('#lab-grid [data-lab="calcrash"]', { timeout: 10000 });
    await sleep(1400);
    await page.evaluate(() => window.__raiseCursor && window.__raiseCursor());
    await glide(page, '#lab-grid [data-lab="calcrash"]', { wait: 700, label: 'Arm crash after a Calendar write' });
    mark('armed crash after a Calendar write');
    await sleep(1400);
    await shot(page, 'lab_armed');
    await sleep(600);
    await page.keyboard.press('Escape'); mark('lab closed');
    await sleep(900);
    await glide(page, '#actionbar .approve[data-action="approve"]', { wait: 700, label: 'Approve' });
    mark('clicked Approve');
    await page.waitForSelector('#actionbar .approve.resume', { timeout: 90000 });
    mark('crashed banner');
    await sleep(1200);
    await shot(page, 'crashed');
    await sleep(1800);
    await glide(page, '#actionbar .approve.resume', { wait: 700, label: 'Resume' });
    mark('clicked Resume');
    await park(page, 330, 900);
    await page.waitForSelector('#actionbar .ab-done', { timeout: 90000 });
    mark('resumed: 36/36');
    await sleep(900);
    await shot(page, 'resumed_36');
    await sleep(2600);
  }

  mark('recording stop');
  const endTs = Date.now() / 1000;
  const frames = await rec.stop();
  await browser.close();
  const lastTs = frames[frames.length - 1].ts;
  const end = Math.abs(endTs - lastTs) < 120 ? endTs : lastTs + 1;
  const first = frames[0].ts;
  const tFix = Math.abs(endTs - lastTs) < 120 ? 0 : null;
  const outFile = path.join(OUT, `${NAME}.mp4`);
  encode(frames, end, outFile);
  const mk = markers.map((m) => ({ t: tFix === null ? null : +(m.epoch - first).toFixed(2), label: m.label }));
  fs.writeFileSync(path.join(OUT, `${NAME}.markers.json`), JSON.stringify({ video: outFile, firstFrameEpoch: first, videoSize: [W, H], markers: mk, clicks: clicks.map((c) => ({ t: +(c.epoch - first).toFixed(2), x: c.x, y: c.y, label: c.label })) }, null, 2));
  console.log('wrote', outFile);
})().catch((e) => { console.error('FAILED', e); process.exit(1); });
