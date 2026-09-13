"""Overlay the real-app screenshots (Slack, Gmail, Calendar, Sheets) as a popping
2x2 grid during the "updates the calendars ... emails the customers" line.

  uv run python video/scripts/splice_apps.py IN.mp4 SUBS.srt OUT.mp4
Screenshots: video/assets/apps/app_1..app_4.png in the order Slack, Gmail, Calendar, Sheets.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import os
APPS = Path(os.environ.get("APPS_DIR", str(ROOT / "video" / "assets" / "apps")))
LABELS = ["SLACK", "GMAIL", "GOOGLE CALENDAR", "GOOGLE SHEETS"]
FONT = ROOT / "web" / "fonts"


def srt_times(path: Path) -> list[tuple[float, float, str]]:
    out = []
    blocks = re.split(r"\n\s*\n", path.read_text().strip())
    for b in blocks:
        lines = b.strip().splitlines()
        m = next((re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", l) for l in lines if "-->" in l), None)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        t0 = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        t1 = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        text = " ".join(l for l in lines if "-->" not in l and not l.strip().isdigit())
        out.append((t0, t1, text.lower()))
    return out


def window(caps: list[tuple[float, float, str]]) -> tuple[float, float]:
    start = next(t0 for t0, _, s in caps if "one click" in s or "updates the calendar" in s or "calendars" in s)
    end = next((t1 for t0, t1, s in caps if t0 >= start and ("customers" in s and "email" in s or "emails the" in s)), start + 8)
    return start, max(end + 0.8, start + 6.5)


def main() -> None:
    src, srt, dst = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    shots = [APPS / f"app_{i}.png" for i in range(1, 5)]
    shots = [s for s in shots if s.exists()]
    if not shots:
        sys.exit("no screenshots in video/assets/apps")
    t0, t1 = window(srt_times(srt))
    font = next((str(p) for p in FONT.glob("Silkscreen*.ttf")), None) or "/System/Library/Fonts/Menlo.ttc"
    W, H, TW, TH, GAP = 1920, 1080, 900, 480, 30
    pos = [(60, 70), (60 + TW + GAP, 70), (60, 70 + TH + GAP), (60 + TW + GAP, 70 + TH + GAP)]
    inputs = ["-i", str(src)]
    for s in shots:
        inputs += ["-loop", "1", "-t", f"{t1 + 1:.2f}", "-i", str(s)]
    f = [f"[0:v]drawbox=x=0:y=0:w={W}:h={H}:color=0x141413@0.82:t=fill:enable='between(t,{t0:.2f},{t1:.2f})'[bg]"]
    last = "bg"
    for i, _ in enumerate(shots):
        ts = t0 + 0.15 + i * 0.55
        x, y = pos[i]
        f.append(f"[{i + 1}:v]scale={TW}:{TH}:force_original_aspect_ratio=decrease,pad={TW}:{TH}:(ow-iw)/2:(oh-ih)/2:color=0x1c1b19,"
                 f"drawbox=x=0:y=0:w={TW}:h={TH}:color=0xD97757:t=4,"
                 f"drawtext=fontfile='{font}':text='{LABELS[i]} UPDATED':x=16:y={TH}-44:fontsize=26:fontcolor=0xF0EEE6:box=1:boxcolor=0x141413@0.85:boxborderw=10,"
                 f"format=rgba,fade=t=in:st={ts:.2f}:d=0.25:alpha=1[s{i}]")
        f.append(f"[{last}][s{i}]overlay=x={x}:y={y}:enable='between(t,{ts:.2f},{t1:.2f})'[v{i}]")
        last = f"v{i}"
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(f), "-map", f"[{last}]", "-map", "0:a?",
           "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "copy", str(dst)]
    subprocess.run(cmd, check=True)
    print(f"apps overlay {t0:.2f}s-{t1:.2f}s -> {dst}")


if __name__ == "__main__":
    main()
