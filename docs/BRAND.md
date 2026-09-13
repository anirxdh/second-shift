# Second Shift: brand sheet

> Palette v2 (2026-09-13): warm terminal. Near-black ground, ivory text, a coral accent in the spirit of Claude's warmth; semantic colors unchanged in meaning.

**Idea.** A night-shift dispatch console. Think of the arcade cabinet in the back of a 24-hour depot: dark room, one lit screen, a crew board that glows when the plan changes. Crafted and calm, never cartoonish. Every pixel choice has to help the dispatcher read the board faster.

## Wordmark

`SECOND SHIFT` set in **Silkscreen Bold**, all caps, letter-spacing 0.06em, lime on night, with a 2px hard drop shadow in `--ss-shadow`. The mark to its left is a 16x16 pixel crescent moon over a van (the second shift). Never set the wordmark in a smooth font, never add gradients, never round it.

## Color tokens

```css
--ss-night:    #141413;  /* page background */
--ss-panel:    #1c1b19;  /* columns, cards */
--ss-panel-2:  #24221f;  /* raised: headers, inputs */
--ss-panel-3:  #2d2a26;  /* hover / selected */
--ss-line:     #3a3631;  /* 2px pixel borders */
--ss-grid:     rgba(240, 238, 230, 0.07); /* board grid + dot field */
--ss-text:     #f0eee6;  /* phosphor white */
--ss-muted:    #a29d91;  /* secondary text */
--ss-dim:      #6f6a60;  /* disabled, ticks */
--ss-shadow:   #050505;  /* hard drop shadows */
--ss-brand:    #d97757;  /* lime: brand, focus, primary action, clock */

/* semantic: fixed meaning everywhere (board, legend, pills, trace, mail) */
--ss-reassigned: #6a9bcc;  /* job moved to another tech */
--ss-retimed:    #e3b341;  /* moved inside the promised window */
--ss-resched:    #f0506e;  /* needs reschedule / error */
--ss-verified:   #7ec77b;  /* written and read back */
--ss-out:        #6f6a60;  /* technician out (hatched) */
--ss-busy:       #b392f0;  /* calendar busy (dithered) */
--ss-window:     #f2dfb0;  /* promised arrival band */
```

Rules: lime is the only brand color and is never used for a status. Mint means verified and nothing else. Semantic colors always appear with a second cue (hatch, dither, badge text, icon) so the board still reads for color-blind viewers.

## Typography

| Role | Face | Use |
|---|---|---|
| Wordmark, labels, tags, buttons | Silkscreen (400/700) | ALL CAPS, 9 to 12px, tracking 0.04 to 0.08em |
| Headings | Pixelify Sans (500 to 700) | 12 to 20px |
| Body, data, trace | JetBrains Mono (400 to 700) | 11.5 to 13px, never below 10px |
| Clock, big numbers, timestamps | VT323 | 13 to 42px; the clock is lime with a phosphor glow. Pixel faces made 3 and 8 look alike, so numbers are always VT323 |

All fonts are OFL and vendored in `web/fonts/`. No runtime CDN.

## Pixel rules

- **Grid unit: 2px.** Borders, offsets, and shadows are multiples of 2. No border-radius anywhere.
- **Stepped borders.** Panels and buttons get a 2px outline built from four box-shadows so the corners are notched, plus a 4px hard drop shadow (no blur).
- **Icons** are 16x16 pixel sprites (`shape-rendering: crispEdges`), 1 color plus optional highlight.
- **Dithering** marks states that are "not a job": calendar busy is a 2px checkerboard, technician out is a 45-degree hatch. Background is a faint 16px dot field.
- **CRT overlay**: 1px scanlines at 5% black over the whole app. Off in reduced motion only if it causes issues; it never animates.

## Motion

- Easing is `steps(n)`: small UI uses `steps(2)` to `steps(4)`, travel uses `steps(12)`. Nothing eases smoothly except scrolling.
- Durations: press 80ms, hover 120ms, reveal 240ms, job travel 800ms, celebration 1200ms.
- Buttons press **down** 2px and lose their shadow. Hover brightens the border to lime.
- Delight moments are rare and earned: vans drive to reassigned jobs when a plan lands; a pixel burst fires when every read-back check passes.
- `prefers-reduced-motion: reduce`: no travel, no bursts, no blinking, no bobbing. State changes still happen instantly.
