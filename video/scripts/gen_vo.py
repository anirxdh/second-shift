"""Generate Second Shift narration with ElevenLabs, one MP3 per scene.

Usage: uv run python video/scripts/gen_vo.py [S3 S4 ...] [--speed 1.05]
Writes video/assets/vo/S1.mp3..S6.mp3, durations.json, captions.json.
Never prints key values.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "video" / "assets" / "vo"
OUT.mkdir(parents=True, exist_ok=True)

ENV = dotenv_values(ROOT / ".env")
KEY = ENV.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVENLABS_API_KEY")
VOICE = ENV.get("ELEVENLABS_NARRATOR_VOICE_ID") or os.environ.get("ELEVENLABS_NARRATOR_VOICE_ID")
assert KEY and VOICE, "missing ElevenLabs key or voice id"

SCENES = {
    "S1": "Six forty-five A.M. Marco, one of only two gas-certified HVAC techs at Bayside Home Services, just called in sick. Four customers are expecting him today, including a contract job at eleven. We can't predict the day. But we can be ready for it. This is Second Shift.",
    "S2": "Second Shift lives in the tools the crew already uses: Slack, Google Sheets, Google Calendar, and Gmail. An AI model reads the call-out. Everything after that is code. It reads every job, skill, and promised arrival window from Sheets, and everyone's real day from Calendar.",
    "S3": "A constraint solver re-plans the whole crew in milliseconds. Watch the chain move. Wei is the only other gas-certified tech, but he's booked. So his plumbing job goes to Ana, which frees Wei for the eleven o'clock contract. Rosa's A C repair goes to Priya, still inside her promised window. One job has no legal slot, so instead of faking it, that customer gets a reschedule request.",
    "S4": "An independent checker re-verifies every rule. The dispatcher sees exactly what will be written, and approves. Right before writing, Second Shift re-reads Calendar and Sheets, and stops if anything changed. Then it writes to all four apps through a ledger, so a retry never double-books or double-emails anyone.",
    "S5": "Then it reads everything back. Thirty-six of thirty-six checks passed, on real Google and Slack. We crash it mid-run on purpose, and it resumes without a single duplicate. Twenty-six reliability scenarios pass, and it understood fifteen of fifteen test messages, including a prompt injection.",
    "S6": "Plans break. Your day doesn't have to. Second Shift.",
}

MODEL = os.environ.get("VO_MODEL", "eleven_multilingual_v2")
HEADERS = {"xi-api-key": KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"}
# The ELEVENLABS_API_KEY in .env is an API key ID (ElevenLabs rejects it), so the
# default backend is fal.ai's hosted ElevenLabs multilingual v2 with the same voice ID.
BACKEND = os.environ.get("VO_BACKEND", "fal")
FAL_KEY = ENV.get("FAL_KEY") or os.environ.get("FAL_KEY")


def tts_fal(scene: str, speed: float) -> None:
    body = {
        "text": SCENES[scene],
        "voice": VOICE,
        "stability": 0.55,
        "similarity_boost": 0.8,
        "style": 0.15,
        "speed": speed,
        "timestamps": True,
    }
    r = requests.post(
        "https://fal.run/fal-ai/elevenlabs/tts/multilingual-v2",
        headers={"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"},
        json=body, timeout=180,
    )
    if r.status_code != 200:
        raise SystemExit(f"{scene}: fal HTTP {r.status_code} {r.text[:400]}")
    data = r.json()
    audio = requests.get(data["audio"]["url"], timeout=120)
    audio.raise_for_status()
    (OUT / f"{scene}.mp3").write_bytes(audio.content)
    if data.get("timestamps"):
        (OUT / f"{scene}.timestamps.json").write_text(json.dumps(data["timestamps"]))
    print(f"{scene}: wrote {len(audio.content)} bytes (fal eleven_multilingual_v2, speed={speed})")


def tts(scene: str, speed: float) -> None:
    if BACKEND == "fal":
        return tts_fal(scene, speed)
    body = {
        "text": SCENES[scene],
        "model_id": MODEL,
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.8,
            "style": 0.15,
            "use_speaker_boost": True,
            "speed": speed,
        },
    }
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}?output_format=mp3_44100_128"
    r = requests.post(url, headers=HEADERS, json=body, timeout=120)
    if r.status_code != 200:
        # Error body can be printed; it never contains the key.
        raise SystemExit(f"{scene}: HTTP {r.status_code} {r.text[:400]}")
    (OUT / f"{scene}.mp3").write_bytes(r.content)
    print(f"{scene}: wrote {len(r.content)} bytes (model={MODEL}, speed={speed})")


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return round(float(out), 3)


BREAK_BEFORE = {"in", "at", "for", "to", "from", "and", "but", "so", "which", "with",
                "including", "on", "through", "inside", "without", "of"}


def _split_long(seg: list[str], max_words: int) -> list[list[str]]:
    """Split an over-long clause near its middle, preferring a break word."""
    if len(seg) <= max_words:
        return [seg]
    mid = len(seg) // 2
    best = None
    for off in (0, 1, -1, 2, -2, 3, -3):
        i = mid + off
        if 2 <= i <= len(seg) - 2 and i <= max_words and len(seg) - i <= max_words * 4:
            if seg[i].lower().strip(",.") in BREAK_BEFORE:
                best = i
                break
    if best is None:
        best = min(mid, max_words)
    return _split_long(seg[:best], max_words) + _split_long(seg[best:], max_words)


def chunk(text: str, max_words: int = 8) -> list[str]:
    """Split on sentence/clause punctuation, then balance clauses over max_words."""
    words = text.split()
    segs, cur = [], []
    for w in words:
        cur.append(w)
        end_sentence = w.endswith((".", "?", "!"))
        end_clause = w.endswith((",", ":", ";"))
        if end_sentence or (end_clause and len(cur) >= 4):
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    out = []
    for seg in segs:
        out.extend(_split_long(seg, max_words))
    return [" ".join(c) for c in out]


def captions(durs: dict) -> dict:
    lead, tail = 0.15, 0.25  # small silence estimate at start/end of each clip
    result = {}
    for scene, text in SCENES.items():
        d = durs[scene]
        parts = chunk(text)
        counts = [len(p.split()) for p in parts]
        total = sum(counts)
        span = max(d - lead - tail, 0.5)
        t = lead
        items = []
        for p, n in zip(parts, counts):
            dt = span * n / total
            items.append({"text": p, "start": round(t, 2), "end": round(t + dt, 2)})
            t += dt
        result[scene] = items
    return result


def main() -> None:
    args = sys.argv[1:]
    speed = 1.0
    if "--speed" in args:
        i = args.index("--speed")
        speed = float(args[i + 1])
        del args[i : i + 2]
    targets = args or list(SCENES)
    for s in targets:
        tts(s, speed)
    durs = {s: duration(OUT / f"{s}.mp3") for s in SCENES if (OUT / f"{s}.mp3").exists()}
    (OUT / "durations.json").write_text(json.dumps(durs, indent=2))
    if len(durs) == len(SCENES):
        (OUT / "captions.json").write_text(json.dumps(captions(durs), indent=2))
    print(json.dumps(durs), "total", round(sum(durs.values()), 2))


if __name__ == "__main__":
    main()
