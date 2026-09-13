#!/usr/bin/env python3
"""Step 1 - measure narration + build caption timing (no whisper, no torch).

Adapted from claude-code-video-toolkit templates/concept-explainer-short
(gen_vo.py writes vo_durations.json, gen_captions.py writes words_*.json).
Here the MP3s already exist, so this script:

  1. ffprobes every scene MP3 -> vo_durations.json   {"01": 13.84, ...}
  2. writes captions/words_{id}.json                  [{"text","start","end"}]
     - if alignment/{id}.json exists (ElevenLabs /with-timestamps response,
       either the whole response or just its "alignment" object), word times
       come from the real character alignment;
     - otherwise times are spread over the detected speech span
       (ffmpeg silencedetect) in proportion to characters, with extra weight
       for punctuation pauses. Good enough for phrase captions.

Run from this directory:   uv run python prep.py
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text())
CAP = CONFIG.get("captions", {})
MAX_WORDS = CAP.get("maxWords", 7)
MAX_CHARS = CAP.get("maxChars", 46)


def audio_path(s: dict) -> Path:
    return HERE / (s.get("audio") or f"audio/scenes/{s['id']}_{s['slug']}.mp3")


def ffprobe_dur(p: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(p)],
        capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def speech_span(p: Path, dur: float) -> tuple[float, float]:
    """First/last non-silent instant via silencedetect."""
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(p), "-af",
         "silencedetect=n=-38dB:d=0.12", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    s0, s1 = 0.0, dur
    if starts and starts[0] < 0.05 and ends:
        s0 = ends[0]
    if starts and starts[-1] > s0 and (len(ends) < len(starts) or ends[-1] >= dur - 0.05):
        s1 = starts[-1]
    if s1 - s0 < 0.5:
        s0, s1 = 0.0, dur
    return s0, s1


def word_times_proportional(words: list[str], s0: float, s1: float):
    def weight(w: str) -> float:
        base = len(w) + 1.0
        if w.endswith((".", "!", "?")):
            base += 7.0
        elif w.endswith((",", ":", ";")):
            base += 3.5
        return base
    ws = [weight(w) for w in words]
    total = sum(ws)
    t, out = s0, []
    for w, wt in zip(words, ws):
        d = (s1 - s0) * wt / total
        out.append((t, t + d))
        t += d
    return out


def word_times_alignment(words: list[str], text: str, al: dict):
    al = al.get("alignment", al)
    chars = al["characters"]
    cs, ce = al["character_start_times_seconds"], al["character_end_times_seconds"]
    spoken = "".join(chars)
    out, pos = [], 0
    for w in words:
        idx = spoken.find(w, pos)
        if idx < 0:  # fall back: next non-space char
            idx = pos
        end_idx = min(len(chars) - 1, idx + len(w) - 1)
        out.append((cs[min(idx, len(cs) - 1)], ce[end_idx]))
        pos = end_idx + 1
    return out


def chunk(words: list[str]):
    """Group words into caption chunks, breaking at punctuation when possible."""
    chunks, cur = [], []
    for i, w in enumerate(words):
        cand = cur + [i]
        txt = " ".join(words[j] for j in cand)
        if cur and (len(cand) > MAX_WORDS or len(txt) > MAX_CHARS):
            chunks.append(cur)
            cur = [i]
        else:
            cur = cand
        if w.endswith((".", "!", "?")) and len(cur) >= 2:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def main() -> None:
    scenes = json.loads((HERE / "scenes.json").read_text())["scenes"]
    durations: dict[str, float] = {}
    (HERE / "captions").mkdir(exist_ok=True)
    for s in scenes:
        ap = audio_path(s)
        if not ap.exists():
            print(f"  {s['id']} MISSING audio {ap.relative_to(HERE)}")
            continue
        dur = ffprobe_dur(ap)
        durations[s["id"]] = round(dur, 3)
        words = s["text"].split()
        al_path = HERE / (s.get("alignment") or f"alignment/{s['id']}.json")
        if s.get("captions_src"):  # "path/to/captions.json#KEY" -> ready-made phrase list
            fpath, _, key = s["captions_src"].partition("#")
            data = json.loads((HERE / fpath).read_text())
            caps = data[key] if key else data
            (HERE / "captions" / f"words_{s['id']}.json").write_text(json.dumps(caps, indent=1))
            print(f"  {s['id']} {s['slug']:12s} {dur:6.2f}s  {len(caps):2d} captions (from {s['captions_src']})")
            continue
        if al_path.exists():
            times = word_times_alignment(words, s["text"], json.loads(al_path.read_text()))
            src = "alignment"
        else:
            s0, s1 = speech_span(ap, dur)
            times = word_times_proportional(words, s0, s1)
            src = f"proportional {s0:.2f}-{s1:.2f}s"
        caps = []
        groups = chunk(words)
        for gi, g in enumerate(groups):
            start = times[g[0]][0]
            end = times[groups[gi + 1][0]][0] if gi + 1 < len(groups) else times[g[-1]][1]
            caps.append({"text": " ".join(words[j] for j in g),
                         "start": round(start, 3), "end": round(max(end, start + 0.3), 3)})
        (HERE / "captions" / f"words_{s['id']}.json").write_text(json.dumps(caps, indent=1))
        print(f"  {s['id']} {s['slug']:12s} {dur:6.2f}s  {len(caps):2d} captions ({src})")
    (HERE / "vo_durations.json").write_text(json.dumps(durations, indent=1))
    print(f"  total narration {sum(durations.values()):.2f}s -> vo_durations.json")


if __name__ == "__main__":
    main()
