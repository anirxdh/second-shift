"""Tighten narration pauses, normalize loudness, and build captions.

Reads video/assets/vo/raw_v2_speed1.1/S*.mp3 (+ ElevenLabs timestamps),
writes video/assets/vo/S*.mp3, durations.json, captions.json.

Usage: uv run python video/scripts/post_vo.py [--cap 0.38] [--target 110]
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_vo import SCENES, chunk  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
VO = ROOT / "video" / "assets" / "vo"
RAW = VO / "raw_v2_speed1.1"

args = sys.argv[1:]
CAP = float(args[args.index("--cap") + 1]) if "--cap" in args else 0.38
TARGET = float(args[args.index("--target") + 1]) if "--target" in args else 110.0
TAIL = 0.3  # silence kept at the end of each clip


def probe(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def silences(path: Path):
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
         "silencedetect=noise=-40dB:d=0.25", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", err)]
    return list(zip(starts, ends))


def cuts_for(path: Path, dur: float):
    cuts = []
    for s, e in silences(path):
        if s < 0.05:  # leading silence: trim to ~0.1s
            if e > 0.15:
                cuts.append((0.0, e - 0.1))
            continue
        if e >= dur - 0.02:  # trailing silence handled by apad
            cuts.append((s + 0.1, dur))
            continue
        if e - s > CAP:
            cuts.append((s + CAP / 2, e - CAP / 2))
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
    # Blocks can split mid-word, so flatten them before splitting on spaces.
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


def main() -> None:
    plan = {}
    for s in SCENES:
        src = RAW / f"{s}.mp3"
        d = probe(src)
        cuts = cuts_for(src, d)
        kept = d - sum(b - a for a, b in cuts)
        plan[s] = (src, d, cuts, kept)
    kept_total = sum(p[3] for p in plan.values()) + TAIL * len(plan)
    tempo = min(max(kept_total / TARGET, 1.0), 1.08)
    print(f"after pause cap {CAP}s: {kept_total:.1f}s; tempo {tempo:.3f} -> ~{kept_total / tempo:.1f}s")

    durs, caps = {}, {}
    for s, (src, d, cuts, kept) in plan.items():
        dst = VO / f"{s}.mp3"
        sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in cuts) or "0"
        af = (
            f"aselect='not({sel})',asetpts=N/SR/TB,"
            f"atempo={tempo:.4f},apad=pad_dur={TAIL},"
            "loudnorm=I=-16:TP=-1.5:LRA=11"
        )
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
             "-af", af, "-ar", "44100", "-ac", "1", "-b:a", "192k", str(dst)],
            check=True,
        )
        durs[s] = round(probe(dst), 3)

        # Captions: map ElevenLabs word timings through the same cuts + tempo.
        text_chunks = chunk(SCENES[s])
        words = words_from_timestamps(s)
        items = []
        if words and len(words) == len(SCENES[s].split()):
            def m(t):
                return max(0.0, (t - removed_before(t, cuts)) / tempo)
            i = 0
            for c in text_chunks:
                n = len(c.split())
                start, end = m(words[i][1]), m(words[i + n - 1][2])
                items.append({"text": c.replace("A C ", "AC "), "start": round(start, 2), "end": round(end, 2)})
                i += n
            # Hold each caption until the next one starts (no flicker gaps).
            for a, b in zip(items, items[1:]):
                a["end"] = round(max(a["end"], b["start"] - 0.02), 2)
            items[-1]["end"] = round(min(durs[s], items[-1]["end"] + 0.2), 2)
            src_kind = "elevenlabs-word-timestamps"
        else:
            lead, tail = 0.1, TAIL
            counts = [len(c.split()) for c in text_chunks]
            span = durs[s] - lead - tail
            t = lead
            for c, n in zip(text_chunks, counts):
                dt = span * n / sum(counts)
                items.append({"text": c.replace("A C ", "AC "), "start": round(t, 2), "end": round(t + dt, 2)})
                t += dt
            src_kind = "proportional-word-count"
        caps[s] = items
        print(s, durs[s], len(items), "captions via", src_kind)

    (VO / "durations.json").write_text(json.dumps(durs, indent=2))
    (VO / "captions.json").write_text(json.dumps(caps, indent=2))
    print(json.dumps(durs), "total", round(sum(durs.values()), 2))


if __name__ == "__main__":
    main()
