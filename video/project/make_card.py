#!/usr/bin/env python3
"""Brand title / outro card as a 1920x1080 PNG (Second Shift night-dispatch look).

  uv run python video/project/make_card.py --out video/project/images/01_title.png \
      --clock "6:45 AM" --kicker "BAYSIDE HOME SERVICES" --title "SECOND SHIFT" \
      --sub "Marco called in sick. Four customers are waiting."

Every flag except --out is optional. Fonts come from web/fonts (OFL, vendored).
Use it in scenes.json with "kenburns": false (or true for a slow push-in).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "web" / "fonts"
W, H = 1920, 1080
NIGHT, PANEL, LINE = (12, 15, 29), (20, 25, 52), (46, 55, 104)
TEXT, MUTED, BRAND, SHADOW = (238, 235, 220), (141, 147, 184), (212, 255, 63), (5, 6, 13)


def font(name: str, size: int, weight: int | None = None):
    f = ImageFont.truetype(str(FONTS / name), size)
    if weight:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f


def tracked(d, y, text, f, fill, track=0.06, shadow=0, center=True):
    """Draw text with letter-spacing (em fraction) and optional hard shadow."""
    size = f.size
    widths = [d.textlength(c, font=f) for c in text]
    total = sum(widths) + track * size * (len(text) - 1)
    x = (W - total) / 2 if center else 160
    for c, w in zip(text, widths):
        if shadow:
            d.text((x + shadow, y + shadow), c, font=f, fill=SHADOW)
        d.text((x, y), c, font=f, fill=fill)
        x += w + track * size


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--kicker", default="")
    ap.add_argument("--sub", default="")
    ap.add_argument("--clock", default="")
    a = ap.parse_args()

    img = Image.new("RGB", (W, H), NIGHT)
    d = ImageDraw.Draw(img)
    for x in range(8, W, 16):          # faint 16px dot field
        for y in range(8, H, 16):
            d.rectangle((x, y, x + 1, y + 1), fill=(22, 27, 52))
    y = 300 if a.clock else 380
    if a.clock:
        fc = font("VT323-Regular.ttf", 150)
        tracked(d, y - 150, a.clock, fc, BRAND, track=0.02, shadow=4)
        y += 40
    if a.kicker:
        tracked(d, y, a.kicker.upper(), font("Silkscreen-Regular.ttf", 34), MUTED, track=0.08)
        y += 70
    if a.title:
        tracked(d, y, a.title.upper(), font("Silkscreen-Bold.ttf", 150), BRAND, track=0.06, shadow=8)
        y += 210
    if a.sub:
        fs = font("JetBrainsMono-Variable.ttf", 44, 500)
        tracked(d, y, a.sub, fs, TEXT, track=0.0)
    # 2px frame with notched corners + scanlines (5% black every other line)
    d.rectangle((40, 40, W - 41, H - 41), outline=LINE, width=4)
    for cx, cy in ((40, 40), (W - 44, 40), (40, H - 44), (W - 44, H - 44)):
        d.rectangle((cx, cy, cx + 3, cy + 3), fill=NIGHT)
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(over)
    for yy in range(0, H, 2):
        od.line([(0, yy), (W, yy)], fill=(0, 0, 0, 13))
    img = Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    img.save(a.out)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
