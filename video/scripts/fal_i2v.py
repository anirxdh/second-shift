"""Optional image-to-video for scene 1. Hard-capped at ~6 minutes; first model to finish wins.
Usage: uv run python video/scripts/fal_i2v.py <image_url>
"""
import json
import sys
import time
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
KEY = dotenv_values(ROOT / ".env").get("FAL_KEY")
H = {"Authorization": f"Key {KEY}", "Content-Type": "application/json"}
WORK = ROOT / "video" / "work" / "fal"
CAP = 360

PROMPT = (
    "Slow, gentle camera push-in along a quiet suburban street at dawn. The sky brightens very slightly, "
    "streetlamps glow softly, a light breeze barely moves the bare tree branches. The parked van stays still. "
    "No people, no cars moving, no text. Calm, still, cinematic pixel-art animation."
)
NEG = "text, letters, people, fast motion, camera shake, blur, distortion, morphing"

MODELS = {
    "kling25": ("fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
                lambda u: {"prompt": PROMPT, "image_url": u, "duration": "5", "negative_prompt": NEG}),
    "kling21": ("fal-ai/kling-video/v2.1/standard/image-to-video",
                lambda u: {"prompt": PROMPT, "image_url": u, "duration": "5", "negative_prompt": NEG}),
}


def main():
    img = sys.argv[1]
    t0 = time.time()
    pending = {}
    for k, (model, build) in MODELS.items():
        r = requests.post(f"https://queue.fal.run/{model}", headers=H, json=build(img), timeout=60)
        if r.status_code >= 300:
            print(json.dumps({"model": k, "submit_error": r.status_code, "err": r.text[:300]}), flush=True)
            continue
        d = r.json()
        pending[k] = d
        print(json.dumps({"model": k, "submitted": d.get("request_id")}), flush=True)
    while pending and time.time() - t0 < CAP:
        time.sleep(8)
        for k, d in list(pending.items()):
            s = requests.get(d["status_url"], headers=H, timeout=30).json()
            st = s.get("status")
            if st == "COMPLETED":
                res = requests.get(d["response_url"], headers=H, timeout=60).json()
                url = (res.get("video") or {}).get("url")
                if not url:
                    print(json.dumps({"model": k, "no_video": str(res)[:300]}), flush=True)
                    pending.pop(k)
                    continue
                out = WORK / f"i2v_{k}.mp4"
                out.write_bytes(requests.get(url, timeout=120).content)
                print(json.dumps({"model": k, "ok": True, "file": str(out), "url": url,
                                  "secs": round(time.time() - t0), "prompt": PROMPT}), flush=True)
                return
            if st not in ("IN_QUEUE", "IN_PROGRESS"):
                print(json.dumps({"model": k, "status": s}), flush=True)
                pending.pop(k)
        print(json.dumps({"t": round(time.time() - t0), "pending": list(pending)}), flush=True)
    print(json.dumps({"timeout_or_failed": True, "secs": round(time.time() - t0)}), flush=True)


if __name__ == "__main__":
    main()
