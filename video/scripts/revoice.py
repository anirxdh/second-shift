"""Re-voice the finished demo with another ElevenLabs voice (via fal), keeping the edit.

Each scene is generated, trimmed of edge silence, time-fitted to the original scene
length, placed at the original start time, and remuxed onto the silent video tracks.
  uv run python video/scripts/revoice.py NAME VOICE_ID
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
V = ROOT / "video"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_vo3 import SCENES  # noqa: E402

FAL_KEY = dotenv_values(ROOT / ".env").get("FAL_KEY")
DUR = json.loads((V / "assets/vo3/durations.json").read_text())
STARTS = {"S1": 0.25, "S2": 18.15, "S3": 28.35, "S4": 50.35, "S5": 65.538, "S6": 88.968}


def decoded(path: Path) -> float:
    out = subprocess.run(["ffmpeg", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True).stderr
    t = [l for l in out.split("time=")[1:]][-1].split()[0]
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def atempo_chain(f: float) -> str:
    parts = []
    while f > 2.0:
        parts.append("atempo=2.0"); f /= 2.0
    while f < 0.5:
        parts.append("atempo=0.5"); f /= 0.5
    parts.append(f"atempo={f:.4f}")
    return ",".join(parts)


def scene(name: str, voice: str, k: str, out: Path) -> str:
    r = requests.post("https://fal.run/fal-ai/elevenlabs/tts/multilingual-v2",
                      headers={"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"},
                      json={"text": SCENES[k], "voice": voice, "stability": 0.55, "similarity_boost": 0.8,
                            "style": 0.15, "speed": 1.0}, timeout=180)
    r.raise_for_status()
    raw = out / f"{k}.raw.mp3"
    raw.write_bytes(requests.get(r.json()["audio"]["url"], timeout=120).content)
    trimmed = out / f"{k}.trim.wav"
    trim = ("silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
            "silenceremove=start_periods=1:start_threshold=-45dB,areverse")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", trim, str(trimmed)], check=True)
    d = decoded(trimmed)
    fitted = out / f"{k}.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(trimmed), "-af", atempo_chain(d / DUR[k]), str(fitted)],
                   check=True)
    return f"{k}: {d:.2f}s -> {DUR[k]:.2f}s (x{d / DUR[k]:.2f})"


def main() -> None:
    name, voice = sys.argv[1], sys.argv[2]
    out = V / "assets" / f"vo_{name}"
    out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(6) as ex:
        for line in ex.map(lambda k: scene(name, voice, k, out), SCENES):
            print(name, line)
    ins, fl = [], []
    for i, k in enumerate(SCENES):
        ins += ["-i", str(out / f"{k}.wav")]
        ms = int(STARTS[k] * 1000)
        fl.append(f"[{i}:a]aresample=48000,adelay={ms}|{ms}[a{i}]")
    fl.append("".join(f"[a{i}]" for i in range(len(SCENES))) + f"amix=inputs={len(SCENES)}:normalize=0,loudnorm=I=-16:TP=-1.5[out]")
    audio = out / "audio.m4a"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fl), "-map", "[out]",
                    "-c:a", "aac", "-b:a", "192k", str(audio)], check=True)
    for vin, suffix in (("v_nosub", "-nosubs"), ("v_sub", "")):
        dst = V / f"second-shift-demo-{name}{suffix}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(V / "work" / f"{vin}.mp4"), "-i", str(audio),
                        "-map", "0:v", "-map", "1:a", "-c", "copy", "-shortest", "-movflags", "+faststart", str(dst)],
                       check=True)
        print(name, "wrote", dst.name)


if __name__ == "__main__":
    main()
