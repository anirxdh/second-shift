"""Warm-terminal re-palette of the Second Shift intro/outro stills (reuses fal_gen.gen).

Usage: uv run python video/scripts/fal_gen_warm.py [ids...] [--models=ultra]
Raw outputs go to video/work/fal2/<model>_<id>.png. Never prints key values.
Palette matches the re-skinned dashboard: near-black #141413, ivory #F0EEE6, coral #D97757.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fal_gen  # noqa: E402

fal_gen.WORK = fal_gen.ROOT / "video" / "work" / "fal2"
fal_gen.WORK.mkdir(parents=True, exist_ok=True)

fal_gen.STYLE = (
    "16-bit pixel art, detailed retro video game background art, crisp hard-edged pixels, "
    "limited warm palette: near-black and warm charcoal shadows, ivory and cream highlights, "
    "one warm coral-orange accent light (#D97757), soft amber glows, muted steel-blue dawn sky. "
    "No green, no purple, no neon. Calm, crafted, cinematic, quiet mood. "
    "Absolutely no text, no letters, no numbers, no words, no signs, no logos."
)

fal_gen.SCENES = {
    "1": (
        "16-bit pixel art. A quiet American suburban street at 6:45 AM dawn, wide cinematic view. Muted steel-blue "
        "sky just beginning to warm to pale cream and soft amber at the horizon, a few stars still visible. Small "
        "single-story houses with one or two warm lit windows, streetlamps still glowing amber, bare sidewalks. "
        "A white HVAC service van with a ladder rack parked at the curb in front of a house, a small coral-orange "
        "light on the van, no writing on the van. Long warm charcoal shadows, still and silent. "
        "Full-bleed image, no borders."
    ),
    "2": (
        "16-bit pixel art. Close-up of a smartphone lying face-up on a dark charcoal kitchen counter before sunrise. "
        "The phone screen lights up with an incoming message notification drawn only as simple glowing "
        "coral-orange bars, its warm light spilling onto the countertop. A plain, unmarked cream coffee mug and a "
        "ring of keys beside it. A window in the background shows a muted steel-blue dawn sky over rooftops. "
        "Full-bleed image filling the whole frame, no black borders, no letterboxing."
    ),
    "3": (
        "16-bit pixel art. Interior of a small field-service dispatch office at dawn. In the foreground, a "
        "dispatcher's desk with a monitor, a headset and a plain cream coffee mug, an empty office chair. On the "
        "wall, a large job board holding a neat grid of blank colored cards, plain solid rectangles with no "
        "writing, in muted steel blue, amber and ivory; about five of the cards glow alarm coral-red. Warm dawn "
        "light through window blinds, deep warm charcoal shadows. Full-bleed image, no borders."
    ),
    "4": (
        "16-bit pixel art. A calm night-shift dispatch console in a dark room, wide shot. A large retro monitor on "
        "a desk glowing with a tidy grid of small ivory and coral-orange blocks in neat rows, warm coral-orange "
        "light spilling across the desk, a keyboard and a mug. Through a big window behind, a crescent moon in a "
        "muted steel-blue sky over a sleeping town and a small parked service van under an amber streetlamp. "
        "Peaceful, everything under control. Full-bleed image, no borders."
    ),
}

if __name__ == "__main__":
    if not any(a.startswith("--models=") for a in sys.argv[1:]):
        sys.argv.append("--models=ultra")
    fal_gen.main()
