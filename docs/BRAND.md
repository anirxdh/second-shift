# Second Shift: brand sheet

**Idea.** A night-shift dispatch console. Think of the arcade cabinet in the back of a 24-hour depot: dark room, one lit screen, a crew board that glows when the plan changes. Crafted and calm, never cartoonish. Every pixel choice has to help the dispatcher read the board faster.

## Wordmark

`SECOND SHIFT` set in **Silkscreen Bold**, all caps, letter-spacing 0.06em, lime on night, with a 2px hard drop shadow in `--ss-shadow`. The mark to its left is a 16x16 pixel crescent moon over a van (the second shift). Never set the wordmark in a smooth font, never add gradients, never round it.

## Color tokens

```css
--ss-night:    #0c0f1d;  /* page background */
--ss-panel:    #141934;  /* columns, cards */
--ss-panel-2:  #1b2143;  /* raised: headers, inputs */
--ss-panel-3:  #232a52;  /* hover / selected */
--ss-line:     #2e3768;  /* 2px pixel borders */
--ss-grid:     rgba(130, 150, 255, 0.07); /* board grid + dot field */
--ss-text:     #eeebdc;  /* phosphor white */
--ss-muted:    #8d93b8;  /* secondary text */
--ss-dim:      #5d6390;  /* disabled, ticks */
--ss-shadow:   #05060d;  /* hard drop shadows */
--ss-brand:    #d4ff3f;  /* lime: brand, focus, primary action, clock */

/* semantic: fixed meaning everywhere (board, legend, pills, trace, mail) */
--ss-reassigned: #5b8cff;  /* job moved to another tech */
--ss-retimed:    #ffb238;  /* moved inside the promised window */
--ss-resched:    #ff5a64;  /* needs reschedule / error */
--ss-verified:   #3ff0a6;  /* written and read back */
--ss-out:        #6a6f93;  /* technician out (hatched) */
--ss-busy:       #a58bff;  /* calendar busy (dithered) */
--ss-window:     #f4e7a1;  /* promised arrival band */
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
