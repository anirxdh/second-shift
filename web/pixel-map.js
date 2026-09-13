/* Second Shift · pixel-map.js
   A small pixel map of the five zones. Shows each technician's route for whatever
   the crew board is showing (Before / After, any plan) by reading the board's DOM.
   Toggle with the MAP button in the board header or the M key. Read-only. */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');

  const W = 180, H = 124; // logical pixels, drawn at 2x
  const ZONES = { North: [90, 24], West: [30, 64], Central: [90, 64], East: [150, 64], South: [90, 104] };
  const C = {
    night: '#0c0f1d', panel: '#141934', line: '#2e3768', line2: '#3d4784', text: '#eeebdc', muted: '#8d93b8',
    dim: '#5d6390', brand: '#d4ff3f', reassigned: '#5b8cff', retimed: '#ffb238', resched: '#ff5a64',
  };
  let travel = null;
  let open = false;
  let focus = -1; // row index
  let hovering = false;
  let cycle = 0;
  let vanT = 0;
  let raf = 0;
  let panel, cv, ctx, list, info;

  function build() {
    const head = $('.col-board .col-head');
    const seg = $('#view-toggle');
    if (!head || !seg) return false;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'px-map-btn';
    btn.id = 'px-map-btn';
    btn.title = 'Zone map (M)';
    btn.setAttribute('aria-expanded', 'false');
    btn.innerHTML = '<svg viewBox="0 0 8 8" shape-rendering="crispEdges" aria-hidden="true"><rect x="0" y="1" width="2" height="6" fill="currentColor"/><rect x="3" y="0" width="2" height="6" fill="currentColor" opacity=".55"/><rect x="6" y="1" width="2" height="6" fill="currentColor"/></svg>Map';
    head.insertBefore(btn, seg);
    btn.addEventListener('click', () => toggle());

    panel = document.createElement('div');
    panel.className = 'px-map';
    panel.hidden = true;
    panel.innerHTML = `<div class="px-map-head"><b>Zone map</b><span class="px-map-view"></span><button type="button" class="px-map-x" aria-label="Close map">x</button></div>
      <canvas width="${W * 2}" height="${H * 2}"></canvas>
      <div class="px-map-info"></div>
      <div class="px-map-list"></div>`;
    $('.col-board').appendChild(panel);
    cv = $('canvas', panel);
    ctx = cv.getContext('2d');
    ctx.imageSmoothingEnabled = false;
    list = $('.px-map-list', panel);
    info = $('.px-map-info', panel);
    $('.px-map-x', panel).addEventListener('click', () => toggle(false));
    list.addEventListener('mouseover', (e) => {
      const b = e.target.closest('[data-row]');
      if (!b) return;
      hovering = true;
      focus = Number(b.dataset.row);
      draw();
    });
    list.addEventListener('mouseleave', () => { hovering = false; });
    return true;
  }

  function toggle(force) {
    open = force === undefined ? !open : force;
    panel.hidden = !open;
    $('#px-map-btn').setAttribute('aria-expanded', String(open));
    if (open) {
      if (!travel) loadTravel();
      draw();
      loop();
    } else cancelAnimationFrame(raf);
  }

  async function loadTravel() {
    try {
      const r = await fetch('/api/state');
      const s = await r.json();
      travel = (s.company && s.company.travel) || null;
      draw();
    } catch (_) { /* map still draws without minutes */ }
  }

  /* read the board */
  function readBoard() {
    const rows = $$('#rows .row').map((row, i) => {
      const t = row.querySelector('.row-label');
      const title = (t && t.getAttribute('title')) || '';
      const m = /home zone (\w+)/.exec(title);
      return {
        i,
        name: (row.querySelector('.tech-name') || {}).textContent || `Tech ${i + 1}`,
        home: m ? m[1] : 'Central',
        out: row.classList.contains('is-out'),
        stops: [],
      };
    });
    $$('#layer .job').forEach((el) => {
      if (el.classList.contains('leaving')) return;
      const it = el.__item;
      if (!it || !it.job || it.ghost || it.kind === 'displaced') return;
      const r = rows[it.row];
      if (!r) return;
      r.stops.push({ zone: it.job.zone, start: it.start, id: it.job.id, kind: it.kind });
    });
    rows.forEach((r) => r.stops.sort((a, b) => a.start - b.start));
    return rows;
  }

  function mins(a, b) {
    return travel && travel[a] && travel[a][b] != null ? travel[a][b] : 0;
  }

  /* pixel drawing */
  function px(x, y, c, s = 1) { ctx.fillStyle = c; ctx.fillRect(Math.round(x) * 2, Math.round(y) * 2, s * 2, s * 2); }
  function line(x0, y0, x1, y1, c, dash = 0) {
    x0 = Math.round(x0); y0 = Math.round(y0); x1 = Math.round(x1); y1 = Math.round(y1);
    const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0);
    const sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
    let err = dx + dy, n = 0;
    for (;;) {
      if (!dash || (n % (dash * 2)) < dash) px(x0, y0, c);
      n++;
      if (x0 === x1 && y0 === y1) break;
      const e2 = 2 * err;
      if (e2 >= dy) { err += dy; x0 += sx; }
      if (e2 <= dx) { err += dx; y0 += sy; }
    }
  }
  function text(s, x, y, c, size = 8) {
    ctx.fillStyle = c;
    ctx.font = `${size * 2}px Silkscreen, monospace`;
    ctx.textBaseline = 'top';
    ctx.fillText(s, Math.round(x) * 2, Math.round(y) * 2);
  }

  function draw() {
    if (!open || !ctx) return;
    const rows = readBoard();
    const active = rows.filter((r) => !r.out && r.stops.length);
    if (!hovering) {
      if (!active.find((r) => r.i === focus)) focus = active.length ? active[0].i : -1;
    }
    ctx.clearRect(0, 0, cv.width, cv.height);
    // dot field
    for (let y = 2; y < H; y += 6) for (let x = 2; x < W; x += 6) px(x, y, '#1a2046');
    // roads (only between neighbours; 40-min pairs are the long way round)
    const names = Object.keys(ZONES);
    names.forEach((a, ai) => names.slice(ai + 1).forEach((b) => {
      const m = mins(a, b);
      if (travel && m >= 40) return;
      const [x0, y0] = ZONES[a], [x1, y1] = ZONES[b];
      line(x0, y0, x1, y1, C.line2, 2);
      if (m) text(String(m), (x0 + x1) / 2 + 2, (y0 + y1) / 2 - 3, C.dim, 5);
    }));
    // zone blocks
    names.forEach((z) => {
      const [x, y] = ZONES[z];
      for (let yy = -7; yy <= 7; yy++) for (let xx = -15; xx <= 15; xx++) {
        const edge = Math.abs(yy) === 7 || Math.abs(xx) === 15;
        if (edge) { if (!((Math.abs(yy) === 7) && (Math.abs(xx) === 15))) px(x + xx, y + yy, C.line2); }
        else if ((xx + yy) % 2 === 0) px(x + xx, y + yy, '#1b2143');
      }
    });
    // routes: everyone dim, the focused tech bright
    const f = rows.find((r) => r.i === focus);
    active.forEach((r, k) => {
      if (f && r.i === f.i) return;
      route(r, (k - active.length / 2) * 2, C.dim, false);
    });
    if (f) route(f, 0, C.brand, true);
    // zone labels last, on a dark plate so routes never cross the text
    names.forEach((z) => {
      const [x, y] = ZONES[z];
      ctx.font = '10px Silkscreen, monospace';
      const w = Math.ceil(ctx.measureText(z.toUpperCase()).width / 2) + 3;
      ctx.fillStyle = C.night;
      ctx.fillRect((x - Math.ceil(w / 2)) * 2, (y - 14) * 2, w * 2, 8 * 2);
      text(z.toUpperCase(), x - Math.ceil(w / 2) + 2, y - 13, (f && (f.home === z || f.stops.some((s) => s.zone === z))) ? C.text : C.muted, 5);
    });
    renderList(rows, f);
  }

  function route(r, off, color, hi) {
    const pts = [r.home, ...r.stops.map((s) => s.zone)].map((z) => {
      const p = ZONES[z] || ZONES.Central;
      return [p[0] + off, p[1] + off * 0.5];
    });
    for (let i = 1; i < pts.length; i++) line(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1], color, hi ? 0 : 1);
    // home marker
    const h = pts[0];
    px(h[0] - 1, h[1] - 1, hi ? C.text : C.dim, 3);
    r.stops.forEach((s, i) => {
      const p = pts[i + 1];
      const c = s.kind === 'reassigned' ? C.reassigned : s.kind === 'retimed' ? C.retimed : (hi ? C.text : C.dim);
      px(p[0] - 1 + i % 2, p[1] - 1 - (i % 3), c, 2);
    });
    if (hi && pts.length > 1 && !reduce.matches) {
      // a van walking the route, stepped
      const seg = Math.floor(vanT) % (pts.length - 1);
      const t = Math.floor((vanT % 1) * 8) / 8;
      const a = pts[seg], b = pts[seg + 1];
      const x = a[0] + (b[0] - a[0]) * t, y = a[1] + (b[1] - a[1]) * t;
      px(x - 3, y - 4, C.text, 2); px(x - 1, y - 4, C.text, 2); px(x + 1, y - 3, C.text, 2);
      px(x - 2, y - 2, C.night, 1); px(x + 1, y - 2, C.night, 1);
    }
  }

  function renderList(rows, f) {
    const sig = rows.map((r) => `${r.i}:${r.name}:${r.out}:${r.stops.length}`).join('|') + `#${f ? f.i : -1}`;
    if (list.__sig !== sig) {
      list.__sig = sig;
      list.innerHTML = rows.map((r) => `<button type="button" data-row="${r.i}" class="${f && f.i === r.i ? 'on' : ''} ${r.out ? 'out' : ''}">${r.name.split(' ')[0]}${r.out ? ' zz' : ` ${r.stops.length}`}</button>`).join('');
    }
    const view = ($('#view-toggle .on') || {}).textContent || '';
    $('.px-map-view', panel).textContent = view ? `${view} view` : '';
    if (!f) { info.textContent = 'No routes to show.'; return; }
    let drive = 0;
    const seq = [f.home, ...f.stops.map((s) => s.zone)];
    for (let i = 1; i < seq.length; i++) drive += mins(seq[i - 1], seq[i]);
    const moved = f.stops.filter((s) => s.kind === 'reassigned').length;
    info.innerHTML = `<b>${f.name}</b> from ${f.home} · ${f.stops.length} stop${f.stops.length === 1 ? '' : 's'}${travel ? ` · ${drive} min driving` : ''}${moved ? ` · <span class="nw">${moved} new</span>` : ''}`;
  }

  function loop() {
    cancelAnimationFrame(raf);
    let last = 0;
    let lastCycle = performance.now();
    const tick = (t) => {
      if (!open) return;
      if (t - last > 110) { // ~9 fps: stepped on purpose
        last = t;
        vanT += 0.125;
        if (!hovering && t - lastCycle > 3200) {
          lastCycle = t;
          const active = readBoard().filter((r) => !r.out && r.stops.length);
          if (active.length) {
            cycle = (active.findIndex((r) => r.i === focus) + 1) % active.length;
            focus = active[cycle].i;
            vanT = 0;
          }
        }
        draw();
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
  }

  function boot() {
    if (!build()) return;
    document.addEventListener('keydown', (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.target.closest && e.target.closest('input, textarea, select')) return;
      if (e.key.toLowerCase() === 'm') toggle();
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
