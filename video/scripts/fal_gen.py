"""Generate pixel-art scene images on fal for the Second Shift video (S1 + S6).

Usage: uv run python video/scripts/fal_gen.py [ids...] [--models ultra,recraft]
Writes raw outputs to video/work/fal/<model>_<id>.png and a prompts.json log.
Never prints key values.
"""
import json
import sys
import time
import concurrent.futures as cf
from pathlib import Path

import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
KEY = dotenv_values(ROOT / ".env").get("FAL_KEY")
assert KEY, "FAL_KEY missing"
WORK = ROOT / "video" / "work" / "fal"
WORK.mkdir(parents=True, exist_ok=True)

STYLE = (
    "16-bit pixel art, detailed retro video game background art, crisp hard-edged pixels, "
    "limited palette: deep indigo-navy night blues, muted slate purple shadows, soft phosphor-cream highlights, "
    "one acid lime-green accent light, small warm amber glows. Calm, crafted, cinematic, quiet mood. "
    "Absolutely no text, no letters, no numbers, no words, no signs, no logos."
)

SCENES = {
    "1": (
        "16-bit pixel art. A quiet American suburban street at 6:45 AM dawn, wide cinematic view. Pale lavender and navy sky "
        "just beginning to brighten at the horizon, a few stars still visible. Small single-story houses with "
        "one or two warm lit windows, streetlamps still glowing, bare sidewalks. A white HVAC service van with "
        "a ladder rack parked at the curb in front of a house, no writing on the van. Long cool shadows, still and silent. Full-bleed image, no borders."
    ),
    "2": (
        "16-bit pixel art. Close-up of a smartphone lying face-up on a dark kitchen counter before sunrise. "
        "The phone screen lights up with an incoming message notification drawn only as simple glowing "
        "lime-green bars, its light spilling onto the countertop. A plain, unmarked coffee mug and a ring of "
        "keys beside it. A window in the background shows a cool blue dawn sky over rooftops. "
        "Full-bleed image filling the whole frame, no black borders, no letterboxing."
    ),
    "3": (
        "16-bit pixel art. Interior of a small field-service dispatch office at dawn. In the foreground, a "
        "dispatcher's desk with a monitor, a headset and a plain coffee mug, an empty office chair. On the wall, "
        "a large job board holding a neat grid of blank colored cards, plain solid rectangles with no writing, "
        "in blue, amber and mint green; about five of the cards glow alarm red. Dawn light through window "
        "blinds, moody navy shadows. Full-bleed image, no borders."
    ),
    "4": (
        "16-bit pixel art. A calm night-shift dispatch console in a dark room, wide shot. A large retro monitor on a desk glowing "
        "with a tidy grid of small colored blocks in neat rows, lime-green light spilling across the desk, a "
        "keyboard and a mug. Through a big window behind, a crescent moon over a sleeping town and a small parked "
        "service van under a streetlamp. Peaceful, everything under control. Full-bleed image, no borders."
    ),
}

# Brand palette hints for Recraft (rgb).
BRAND_RGB = [
    (12, 15, 29), (20, 25, 52), (35, 42, 82), (46, 55, 104), (238, 235, 220),
    (212, 255, 63), (91, 140, 255), (255, 178, 56), (255, 90, 100), (63, 240, 166),
]

MODELS = {
    "ultra": ("fal-ai/flux-pro/v1.1-ultra", lambda p: {
        "prompt": p, "aspect_ratio": "16:9", "num_images": 1, "output_format": "png",
        "safety_tolerance": "5", "enable_safety_checker": False,
    }),
    "recraft": ("fal-ai/recraft/v3/text-to-image", lambda p: {
        "prompt": p[:990], "image_size": "landscape_16_9", "style": "digital_illustration/pixel_art",
        "colors": [{"r": r, "g": g, "b": b} for r, g, b in BRAND_RGB],
    }),
    "flux11": ("fal-ai/flux-pro/v1.1", lambda p: {
        "prompt": p, "image_size": {"width": 1920, "height": 1088}, "num_images": 1,
        "output_format": "png", "safety_tolerance": "5", "enable_safety_checker": False,
    }),
    "dev": ("fal-ai/flux/dev", lambda p: {
        "prompt": p, "image_size": "landscape_16_9", "num_images": 1, "num_inference_steps": 28,
        "enable_safety_checker": False,
    }),
}


def prompt_for(sid, model_key):
    scene = SCENES[sid]
    if model_key == "recraft":
        # Recraft's style param already supplies the pixel look; keep palette words short.
        return scene + " Deep navy night palette with lime-green and amber accents. No text, no letters."
    return scene + " " + STYLE


def gen(sid, model_key):
    model, build = MODELS[model_key]
    prompt = prompt_for(sid, model_key)
    t0 = time.time()
    r = requests.post(
        f"https://fal.run/{model}",
        headers={"Authorization": f"Key {KEY}", "Content-Type": "application/json"},
        json=build(prompt), timeout=240,
    )
    if r.status_code != 200:
        return {"id": sid, "model": model, "ok": False, "status": r.status_code, "err": r.text[:300]}
    data = r.json()
    url = data["images"][0]["url"]
    img = requests.get(url, timeout=120).content
    ext = "png" if img[:4] == b"\x89PNG" else ("webp" if img[8:12] == b"WEBP" else "jpg")
    out = WORK / f"{model_key}_{sid}.{ext}"
    out.write_bytes(img)
    return {"id": sid, "model": model, "ok": True, "file": str(out), "url": url, "prompt": prompt,
            "secs": round(time.time() - t0, 1), "w": data["images"][0].get("width"),
            "h": data["images"][0].get("height")}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    models = ["ultra", "recraft"]
    for a in sys.argv[1:]:
        if a.startswith("--models="):
            models = a.split("=", 1)[1].split(",")
    ids = args or list(SCENES)
    jobs = [(s, m) for s in ids for m in models]
    log_path = WORK / "prompts.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(gen, s, m): (s, m) for s, m in jobs}
        for f in cf.as_completed(futs):
            try:
                res = f.result()
            except Exception as e:  # network etc.
                s, m = futs[f]
                res = {"id": s, "model": m, "ok": False, "err": repr(e)[:300]}
            print(json.dumps({k: v for k, v in res.items() if k != "prompt"}), flush=True)
            log.append(res)
    log_path.write_text(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
