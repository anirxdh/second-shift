/* Second Shift · pixel-fx.js
   Additive delight layer for the pixel theme. Reads the DOM that app.js renders;
   never calls into app.js and never changes its state.
   - vans drive to newly reassigned jobs when a plan lands (or on Before -> After)
   - a pixel burst when every read-back check passes
   - "C" toggles the CRT scanline overlay
   All motion is skipped under prefers-reduced-motion. */
(() => {
  'use strict';
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  const still = () => reduce.matches;
  const bootAt = Date.now();
  const booting = () => Date.now() - bootAt < 1500; // don't replay effects for a plan already on screen at load
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  /* ---------- CRT toggle (C) ---------- */
  try { if (localStorage.getItem('ss-crt') === 'off') document.body.classList.add('crt-off'); } catch (_) { /* storage blocked */ }
  document.addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.target.closest && e.target.closest('input, textarea, select')) return;
    if (e.key.toLowerCase() !== 'c') return;
    const off = document.body.classList.toggle('crt-off');
    try { localStorage.setItem('ss-crt', off ? 'off' : 'on'); } catch (_) { /* storage blocked */ }
  });

  /* ---------- vans ---------- */
  let lastSig = '';
  let vanTimer = 0;

  function reassignedJobs() {
    return $$('#layer .job.k-reassigned').filter((el) => !el.classList.contains('leaving'));
  }

  function scheduleVans() {
    clearTimeout(vanTimer);
    vanTimer = setTimeout(checkVans, 90);
  }

  function checkVans() {
    const jobs = reassignedJobs();
    const sig = jobs.map((el) => el.dataset.key).sort().join('|');
    if (sig === lastSig) return;
    const prev = new Set(lastSig ? lastSig.split('|') : []);
    lastSig = sig;
    if (!jobs.length || still() || booting()) return;
    const fresh = jobs.filter((el) => !prev.has(el.dataset.key));
    fresh.slice(0, 8).forEach((el, i) => setTimeout(() => driveTo(el), 380 + i * 160));
  }

  function driveTo(jobEl) {
    const body = $('#board-body');
    const layer = $('#layer');
    if (!body || !layer || !jobEl.isConnected) return;
    const row = Number(jobEl.style.getPropertyValue('--row'));
    const rowEl = $$('#rows .row')[row];
    if (!rowEl) return;
    const bodyRect = body.getBoundingClientRect();
    const layerRect = layer.getBoundingClientRect();
    const leftPct = parseFloat(jobEl.style.left) || 0;
    const jobX = layerRect.left - bodyRect.left + (leftPct / 100) * layerRect.width;
    const labelW = layerRect.left - bodyRect.left;
    const startX = Math.round(labelW - 30);
    const endX = Math.max(startX + 8, Math.round(jobX - 26));
    const y = Math.round(rowEl.offsetTop + rowEl.offsetHeight - 20);

    const van = document.createElement('div');
    van.className = 'px-van';
    van.style.left = '0px';
    van.style.top = `${y}px`;
    body.appendChild(van);

    const dist = endX - startX;
    const dur = Math.min(1400, 500 + dist * 1.1);
    const steps = Math.max(8, Math.round(dur / 55));
    const drive = van.animate([
      { transform: `translate(${startX}px, 0)`, opacity: 0 },
      { transform: `translate(${startX + 6}px, -2px)`, opacity: 1, offset: 0.08 },
      { transform: `translate(${Math.round(startX + dist * 0.5)}px, 0)`, opacity: 1, offset: 0.55 },
      { transform: `translate(${endX - 4}px, -2px)`, opacity: 1, offset: 0.85 },
      { transform: `translate(${endX}px, 0)`, opacity: 1 },
    ], { duration: dur, easing: `steps(${steps}, end)`, fill: 'forwards' });

    drive.onfinish = () => {
      if (jobEl.isConnected) {
        jobEl.classList.remove('px-arrive');
        void jobEl.offsetWidth;
        jobEl.classList.add('px-arrive');
        setTimeout(() => jobEl.classList.remove('px-arrive'), 1300);
      }
      puff(body, endX + 22, y + 4);
      const fade = van.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 360, delay: 260, easing: 'steps(3, end)', fill: 'forwards' });
      fade.onfinish = () => van.remove();
    };
  }

  function puff(parent, x, y) {
    const dirs = [[-6, -6], [6, -6], [8, 2], [-8, 2], [0, -9]];
    dirs.forEach(([dx, dy]) => {
      const p = document.createElement('i');
      p.className = 'px-puff';
      p.style.left = `${x}px`;
      p.style.top = `${y}px`;
      parent.appendChild(p);
      const a = p.animate([
        { transform: 'translate(0,0)', opacity: 1 },
        { transform: `translate(${dx * 2}px, ${dy * 2}px)`, opacity: 0 },
      ], { duration: 420, easing: 'steps(4, end)', fill: 'forwards' });
      a.onfinish = () => p.remove();
    });
  }

  /* ---------- all-checks-passed burst ---------- */
  let doneSeen = false;
  let lastBurst = 0;

  function checkDone() {
    const done = $('#actionbar .ab-done');
    const ok = done && !done.classList.contains('issues') && !done.classList.contains('bad');
    if (!ok) { doneSeen = false; return; }
    if (doneSeen) return;
    doneSeen = true;
    if (booting()) return;
    const big = $('.big', done);
    const m = big && /^(\d+)\/(\d+)$/.exec(big.textContent.trim());
    if (!m || m[1] !== m[2]) return;
    const now = Date.now();
    if (now - lastBurst < 4000) return;
    lastBurst = now;
    done.classList.add('px-win');
    setTimeout(() => done.classList.remove('px-win'), 1700);
    if (!still()) burst(done.getBoundingClientRect(), `${m[1]}/${m[2]} CHECKS CLEAR`);
  }

  function burst(rect, label) {
    const dpr = 1;
    const cv = document.createElement('canvas');
    cv.className = 'px-canvas';
    cv.width = Math.ceil(window.innerWidth * dpr / 2);
    cv.height = Math.ceil(window.innerHeight * dpr / 2);
    cv.style.width = '100vw';
    cv.style.height = '100vh';
    document.body.appendChild(cv);
    const ctx = cv.getContext('2d');
    const colors = ['#d97757', '#7ec77b', '#6a9bcc', '#e3b341', '#f0eee6', '#7ec77b'];
    const ox = (rect.left + rect.width * 0.22) / 2;
    const oy = (rect.top + rect.height * 0.3) / 2;
    const parts = [];
    for (let i = 0; i < 90; i++) {
      const ang = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 1.15;
      const sp = 2.2 + Math.random() * 4.2;
      parts.push({
        x: ox + (Math.random() - 0.5) * rect.width * 0.35,
        y: oy,
        vx: Math.cos(ang) * sp,
        vy: Math.sin(ang) * sp - 1.2,
        s: Math.random() < 0.3 ? 2 : 1,
        c: colors[i % colors.length],
        life: 55 + Math.random() * 35,
      });
    }
    let frame = 0;
    let last = 0;
    const tick = (t) => {
      if (t - last < 33) { requestAnimationFrame(tick); return; } // ~30fps: chunky, on purpose
      last = t;
      frame++;
      ctx.clearRect(0, 0, cv.width, cv.height);
      let alive = 0;
      for (const p of parts) {
        if (frame > p.life) continue;
        alive++;
        p.vy += 0.22;
        p.vx *= 0.985;
        p.x += p.vx;
        p.y += p.vy;
        const blink = frame > p.life - 12 && frame % 2;
        if (blink) continue;
        ctx.fillStyle = p.c;
        ctx.fillRect(Math.round(p.x), Math.round(p.y), p.s + 1, p.s + 1);
      }
      if (alive && frame < 110) requestAnimationFrame(tick);
      else cv.remove();
    };
    requestAnimationFrame(tick);
    setTimeout(() => cv.remove(), 5000); // failsafe if rAF is throttled in a background tab

    const tag = document.createElement('div');
    tag.className = 'px-banner';
    tag.textContent = label;
    tag.style.left = `${rect.left + rect.width / 2}px`;
    tag.style.top = `${Math.max(70, rect.top - 34)}px`;
    document.body.appendChild(tag);
    setTimeout(() => tag.remove(), 1700);
  }

  /* ---------- observers ---------- */
  function boot() {
    const layer = $('#layer');
    const bar = $('#actionbar');
    if (!layer || !bar) return;
    new MutationObserver(scheduleVans).observe(layer, { childList: true, subtree: false, attributes: true, attributeFilter: ['class'] });
    // the class attribute of each job changes on re-render; watch children too
    new MutationObserver(scheduleVans).observe(layer, { subtree: true, attributes: true, attributeFilter: ['class'] });
    new MutationObserver(checkDone).observe(bar, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
