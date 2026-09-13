#!/usr/bin/env python3
"""Step 2 - compose the 16:9 video. Audio-anchored moviepy build.

Adapted from claude-code-video-toolkit templates/concept-explainer-short/build.py
(original kept next to this file as build_toolkit_original.py). Changes:
  * 1920x1080 via config.json, Second Shift palette + vendored brand fonts
  * scene video clips play ONCE then hold the last frame (no boomerang,
    which looks wrong on screen recordings); "fit": "contain" letterboxes
  * a scene can have several "shots" (image/video) splitting its duration
  * per-scene "kenburns": false for title/outro cards
  * square caption plates with a 4px hard shadow (brand: no border-radius)

Scene start times derive from the real MP3 durations (vo_durations.json from
prep.py), so narration and picture cannot drift. Run from this directory:
    uv run python prep.py && uv run python build.py [--only 01,02] [--out x.mp4]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
    vfx,
)
from moviepy.audio.fx.AudioFadeOut import AudioFadeOut
from moviepy.audio.fx.AudioLoop import AudioLoop
from moviepy.audio.fx.MultiplyVolume import MultiplyVolume

HERE = Path(__file__).resolve().parent
TEXT_CACHE = HERE / ".text_cache"
CONFIG = json.loads((HERE / "config.json").read_text())
FMT, PALETTE = CONFIG["format"], CONFIG["palette"]
FONTS = CONFIG.get("fonts", {})
CAPTIONS = CONFIG.get("captions", {})
TIMING = CONFIG.get("timing", {})
ENC = CONFIG.get("encode", {})

W, H, FPS = FMT["width"], FMT["height"], FMT["fps"]
START_PAD = TIMING.get("startPad", 0.0)
LEAD = TIMING.get("lead", 0.35)
TAIL = TIMING.get("tail", 0.6)
XFADE = TIMING.get("xfade", 0.3)
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}


def _rgb(h: str) -> tuple:
    return tuple(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))


def _font(key: str, size: int, weight: int | None = None):
    rel = FONTS.get(key)
    if rel:
        try:
            f = ImageFont.truetype(str((HERE / rel).resolve()), size)
            if weight:
                try:
                    f.set_variation_by_axes([weight])
                except Exception:
                    pass
            return f
        except OSError:
            pass
    return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", size)


def caption_png(txt: str) -> str:
    size = CAPTIONS.get("size", 46)
    fill = CAPTIONS.get("fill", PALETTE["text"])
    TEXT_CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"cap2|{txt}|{size}|{fill}".encode()).hexdigest()[:16]
    path = TEXT_CACHE / f"{key}.png"
    if path.exists():
        return str(path)
    font = _font("caption", size, FONTS.get("captionWeight"))
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = probe.textbbox((0, 0), txt, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    px, py, sh = 28, 16, 4
    bw, bh = tw + px * 2, th + py * 2
    img = Image.new("RGBA", (bw + sh, bh + sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((sh, sh, bw - 1 + sh, bh - 1 + sh), fill=(*_rgb(PALETTE["shadow"]), 255))
    d.rectangle((0, 0, bw - 1, bh - 1), fill=(*_rgb(PALETTE["panel"]), 238))
    d.text((px - bbox[0], py - bbox[1]), txt, font=font, fill=(*_rgb(fill), 255))
    max_w = int(W * 0.9)
    if img.width > max_w:
        img = img.resize((max_w, max(1, int(img.height * max_w / img.width))), Image.LANCZOS)
    img.save(path)
    return str(path)


def placeholder_png(label: str, hint: str) -> str:
    TEXT_CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"ph2|{label}|{hint}|{W}x{H}".encode()).hexdigest()[:16]
    path = TEXT_CACHE / f"{key}.png"
    if path.exists():
        return str(path)
    img = Image.new("RGB", (W, H), _rgb(PALETTE["ink"]))
    d = ImageDraw.Draw(img)
    for x in range(0, W, 16):  # faint dot field
        for y in range(0, H, 16):
            d.point((x, y), fill=_rgb(PALETTE["panel"]))
    f = _font("placeholder", 96)
    bb = d.textbbox((0, 0), label, font=f)
    d.text(((W - bb[2] + bb[0]) / 2, H * 0.40), label, font=f, fill=_rgb(PALETTE["brand"]))
    f2 = _font("caption", 30, 400)
    bb = d.textbbox((0, 0), hint, font=f2)
    d.text(((W - bb[2] + bb[0]) / 2, H * 0.52), hint, font=f2, fill=_rgb(PALETTE["slate"]))
    img.save(path)
    return str(path)


def still(img_path: str, duration: float, kenburns: bool, zoom_in: bool, fit: str):
    with Image.open(img_path) as im:
        iw, ih = im.size
    base = (min if fit == "contain" else max)(W / iw, H / ih)
    clip = ImageClip(img_path).with_duration(duration)
    if not kenburns:
        return clip.resized(base).with_position(("center", "center"))
    amp = 0.06
    if zoom_in:
        scale = lambda t: base * (1.0 + amp * (t / duration))
    else:
        scale = lambda t: base * (1.0 + amp * (1 - t / duration))
    return clip.resized(scale).with_position(("center", "center"))


def video_once(path: str, duration: float, fit: str, start: float = 0.0):
    """Play once from `start`; hold the last frame if the clip is short."""
    v = VideoFileClip(path).without_audio()
    v = v.subclipped(min(start, max(0, v.duration - 0.1)), None)
    scale = (min if fit == "contain" else max)(W / v.w, H / v.h)
    v = v.resized(scale)
    if v.duration >= duration:
        return v.subclipped(0, duration).with_position(("center", "center"))
    last = ImageClip(v.get_frame(max(0, v.duration - 1.0 / FPS))).with_duration(duration - v.duration)
    return concatenate_videoclips([v, last]).with_position(("center", "center"))


def scene_visual(s: dict, idx: int, dur: float, zoom_in: bool):
    """Return list of (clip, offset) for the scene's shots."""
    shots = s.get("shots") or [{"asset": s.get("asset"), **{k: s[k] for k in ("fit", "kenburns", "start") if k in s}}]
    fixed = sum(sh.get("seconds", 0) for sh in shots)
    flex = [sh for sh in shots if "seconds" not in sh]
    share = max(0.5, (dur - fixed) / len(flex)) if flex else 0
    out, t = [], 0.0
    for sh in shots:
        d = sh.get("seconds", share)
        if sh is shots[-1]:
            d = max(0.5, dur - t)
        asset = HERE / sh["asset"] if sh.get("asset") else None
        ext = asset.suffix.lower() if asset else ""
        if asset and asset.exists() and ext in VIDEO_EXTS:
            clip = video_once(str(asset), d, sh.get("fit", "contain"), sh.get("start", 0.0))
        elif asset and asset.exists() and ext in IMAGE_EXTS:
            clip = still(str(asset), d, sh.get("kenburns", True), zoom_in, sh.get("fit", "cover"))
            zoom_in = not zoom_in
        else:
            print(f"     [missing {sh.get('asset')} - placeholder card]")
            clip = still(placeholder_png(s["slug"].upper(), f"add {sh.get('asset')}"), d, False, zoom_in, "cover")
        out.append((clip, t))
        t += d
    return out, zoom_in


def build(only: set[str] | None, out_name: str | None) -> None:
    scenes = json.loads((HERE / "scenes.json").read_text())["scenes"]
    if only:
        scenes = [s for s in scenes if s["id"] in only]
    durations = json.loads((HERE / "vo_durations.json").read_text())
    clips: list = [ColorClip((W, H), color=_rgb(PALETTE["ink"]))]
    audio: list = []
    cursor, zoom_in = START_PAD, True
    print("-- audio-anchored timeline --")
    for idx, s in enumerate(scenes):
        vo = durations.get(s["id"])
        if vo is None:
            sys.exit(f"no duration for scene {s['id']} - run prep.py (is the MP3 there?)")
        lead, tail = s.get("lead", LEAD), s.get("tail", TAIL)
        start, dur = cursor, lead + vo + tail
        print(f"  {s['id']} {s['slug']:12s} {start:7.2f} -> {start + dur:7.2f}  (vo {vo:.2f}s)")
        shots, zoom_in = scene_visual(s, idx, dur, zoom_in)
        for n, (clip, off) in enumerate(shots):
            fx = []
            if n == 0:
                fx.append(vfx.FadeIn(XFADE))
            if n == len(shots) - 1:
                fx.append(vfx.FadeOut(XFADE))
            clips.append(clip.with_start(start + off).with_effects(fx))
        ap = HERE / (s.get("audio") or f"audio/scenes/{s['id']}_{s['slug']}.mp3")
        audio.append(AudioFileClip(str(ap)).with_start(start + lead))
        wf = HERE / "captions" / f"words_{s['id']}.json"
        if CAPTIONS.get("enabled", True) and s.get("captions", True) and wf.exists():
            for ch in json.loads(wf.read_text()):
                img = caption_png(ch["text"])
                with Image.open(img) as im:
                    ch_h = im.height
                clips.append(ImageClip(img)
                             .with_duration(max(0.25, ch["end"] - ch["start"]))
                             .with_start(start + lead + ch["start"])
                             .with_position(("center", CAPTIONS.get("y", 930) - ch_h // 2)))
        cursor = start + dur
    total = cursor + 0.2
    clips[0] = clips[0].with_duration(total)
    print(f"  total: {total:.2f}s")
    mc = CONFIG.get("music", {})
    mp = HERE / mc.get("file", "audio/music.mp3")
    if mp.exists():
        audio.insert(0, AudioFileClip(str(mp)).with_effects([
            AudioLoop(duration=total), MultiplyVolume(mc.get("volume", 0.1)), AudioFadeOut(2.0)]))
    final = CompositeVideoClip(clips, size=(W, H)).with_duration(total).with_audio(CompositeAudioClip(audio))
    out = HERE / (out_name or CONFIG.get("output", "out/second_shift.mp4"))
    out.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(str(out), fps=FPS, codec="libx264", audio_codec="aac",
                          audio_bitrate="192k", preset=ENC.get("preset", "veryfast"),
                          threads=ENC.get("threads", 8),
                          ffmpeg_params=["-crf", str(ENC.get("crf", "20")), "-pix_fmt", "yuv420p",
                                         "-movflags", "+faststart"])
    print(f"wrote {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated scene ids, e.g. 01,02")
    ap.add_argument("--out", help="output path relative to this dir")
    a = ap.parse_args()
    build(set(a.only.split(",")) if a.only else None, a.out)
