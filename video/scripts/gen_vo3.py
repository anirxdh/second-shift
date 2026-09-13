"""Regenerate ALL six Second Shift narration scenes (vo3, kid-simple script).

Same voice / backend / model / voice settings as gen_vo.py (fal ElevenLabs
multilingual-v2, stability 0.55, similarity 0.8, style 0.15).

Usage:
  uv run python video/scripts/gen_vo3.py gen [S1 ...] [--speed 1.0]   # raw TTS -> vo3/raw/
  uv run python video/scripts/gen_vo3.py post [--cap 0.55]            # vo3/S*.mp3, durations, captions
Never prints key values.
"""
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_vo  # noqa: E402

ROOT = gen_vo.ROOT
VO3 = ROOT / "video" / "assets" / "vo3"
RAW = VO3 / "raw"

SCENES = {
    "S1": "It's six forty-five in the morning. Marco just called in sick. Four customers are waiting for him today. Who covers his jobs? Figuring that out by hand takes an hour. Second Shift does it in seconds.",
    "S2": "Someone posts in Slack: Marco is out. Second Shift reads it, then looks at every job and every calendar.",
    "S3": "It builds a new plan. Watch the trucks move. Wei can do Marco's big gas job, but he's busy. So Ana takes Wei's small job, and Wei takes Marco's. One job can't be saved today, so that customer is asked to pick a new time.",
    "S4": "Nothing changes until a person says yes. One click, and it updates the calendars and the job sheet, messages the team in Slack, and emails the customers.",
    "S5": "Then it double-checks every change. Thirty-six out of thirty-six. If it crashes halfway, it finishes without sending anything twice. And you can ask: what if Wei doesn't show up? It shows you, before it happens.",
    "S6": "Sick days, flat tires, no-shows. They'll keep happening. Now they take seconds to fix, not an hour. We can't predict the day. But we can be ready for it. Second Shift.",
}

TAIL = 0.3  # silence kept at the end of each clip
BREAK_BEFORE = {"in", "at", "for", "to", "from", "and", "but", "so", "which", "with",
                "on", "without", "of", "then", "before", "until", "that", "is", "a", "by"}


def decoded_duration(path: Path) -> float:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    times = re.findall(r"time=(\d+):(\d+):([\d.]+)", err)
    h, m, s = times[-1]
    return round(int(h) * 3600 + int(m) * 60 + float(s), 3)


def gen(targets, speed):
    RAW.mkdir(parents=True, exist_ok=True)
    gen_vo.OUT = RAW
    gen_vo.SCENES = {**gen_vo.SCENES, **SCENES}
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(lambda s: gen_vo.tts_fal(s, speed), targets))
    for s in targets:
        print(s, "raw decoded", decoded_duration(RAW / f"{s}.mp3"))


def silences(path: Path):
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
         "silencedetect=noise=-40dB:d=0.25", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", err)]
    return list(zip(starts, ends))


def cuts_for(path: Path, dur: float, cap: float):
    cuts = []
    for s, e in silences(path):
        if s < 0.05:  # leading silence: keep ~0.1s
            if e > 0.15:
                cuts.append((0.0, e - 0.1))
            continue
        if e >= dur - 0.05:  # trailing silence: apad adds TAIL back
            cuts.append((s + 0.1, dur + 1.0))
            continue
        if e - s > cap:
            cuts.append((s + cap / 2, e - cap / 2))
    return cuts


def removed_before(t: float, cuts) -> float:
    r = 0.0
    for a, b in cuts:
        if t >= b:
            r += b - a
        elif t > a:
            r += t - a
    return r


def words_from_timestamps(scene: str):
    p = RAW / f"{scene}.timestamps.json"
    if not p.exists():
        return None
    t = json.loads(p.read_text())
    blocks = t if isinstance(t, list) else [t]
    chars = [
        trip
        for blk in blocks
        for trip in zip(blk["characters"], blk["character_start_times_seconds"], blk["character_end_times_seconds"])
    ]
    words, cur, ws, we = [], "", None, None
    for c, a, b in chars:
        if c.isspace():
            if cur:
                words.append((cur, ws, we))
                cur = ""
        else:
            if not cur:
                ws = a
            cur += c
            we = b
    if cur:
        words.append((cur, ws, we))
    return words


def _split(seg, max_words):
    n = len(seg)
    if n <= max_words:
        return [seg]
    parts = -(-n // max_words)  # ceil
    size = n / parts
    cut = round(size)
    # nudge the cut onto a natural break word if one is within one word
    for off in (0, 1, -1):
        i = cut + off
        if 2 <= i <= n - 2 and i <= max_words and seg[i].lower().strip(",.:?") in BREAK_BEFORE:
            cut = i
            break
    cut = max(2, min(cut, max_words, n - 1))
    return [seg[:cut]] + _split(seg[cut:], max_words)


def chunk5(text: str, max_words: int = 5):
    words = text.split()
    segs, cur = [], []
    for w in words:
        cur.append(w)
        if w.endswith((".", "?", "!", ",", ":", ";")):
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    # merge a lone 1-word clause into its neighbour when the result still fits
    merged = []
    for seg in segs:
        if merged and (len(seg) == 1 or len(merged[-1]) == 1) and len(merged[-1]) + len(seg) <= max_words \
                and not merged[-1][-1].endswith((".", "?", "!")):
            merged[-1] = merged[-1] + seg
        else:
            merged.append(seg)
    out = []
    for seg in merged:
        out.extend(_split(seg, max_words))
    return [" ".join(c) for c in out]


def post(cap: float):
    durs, caps, words_out = {}, {}, {}
    for s, text in SCENES.items():
        src = RAW / f"{s}.mp3"
        d = decoded_duration(src)
        cuts = cuts_for(src, d, cap)
        dst = VO3 / f"{s}.mp3"
        sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in cuts) or "0"
        af = (f"aselect='not({sel})',asetpts=N/SR/TB,apad=pad_dur={TAIL},"
              "loudnorm=I=-16:TP=-1.5:LRA=11")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                        "-af", af, "-ar", "44100", "-ac", "1", "-b:a", "192k", str(dst)], check=True)
        durs[s] = decoded_duration(dst)

        def m(t):
            return round(max(0.0, t - removed_before(t, cuts)), 3)

        chunks = chunk5(text)
        words = words_from_timestamps(s)
        items = []
        if words and len(words) == len(text.split()):
            words_out[s] = [{"word": w, "start": m(a), "end": m(b)} for w, a, b in words]
            i = 0
            for c in chunks:
                n = len(c.split())
                items.append({"text": c, "start": round(m(words[i][1]), 2),
                              "end": round(m(words[i + n - 1][2]), 2)})
                i += n
            for a, b in zip(items, items[1:]):
                a["end"] = round(max(a["end"], b["start"] - 0.02), 2)
            items[-1]["end"] = round(min(durs[s], items[-1]["end"] + 0.25), 2)
            kind = "elevenlabs-word-timestamps"
        else:
            lead = 0.1
            counts = [len(c.split()) for c in chunks]
            span = durs[s] - lead - TAIL
            t = lead
            for c, n in zip(chunks, counts):
                dt = span * n / sum(counts)
                items.append({"text": c, "start": round(t, 2), "end": round(t + dt, 2)})
                t += dt
            kind = "proportional-word-count"
        caps[s] = items
        print(s, f"raw {d:.2f}s -> {durs[s]:.2f}s", len(items), "captions via", kind)

    (VO3 / "durations.json").write_text(json.dumps(durs, indent=2))
    (VO3 / "captions.json").write_text(json.dumps(caps, indent=2))
    if words_out:
        (VO3 / "words.json").write_text(json.dumps(words_out, indent=2))
    print(json.dumps(durs), "total", round(sum(durs.values()), 2))


if __name__ == "__main__":
    args = sys.argv[1:]
    mode = args.pop(0) if args else "gen"
    speed, cap = 1.0, 0.55
    if "--speed" in args:
        i = args.index("--speed"); speed = float(args[i + 1]); del args[i:i + 2]
    if "--cap" in args:
        i = args.index("--cap"); cap = float(args[i + 1]); del args[i:i + 2]
    VO3.mkdir(parents=True, exist_ok=True)
    if mode == "gen":
        gen(args or list(SCENES), speed)
    else:
        post(cap)
