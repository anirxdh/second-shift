"""Regenerate S5 + S6 narration (vo2) with the exact gen_vo.py voice/model/settings.

Usage: uv run python video/scripts/gen_vo2.py [S5 S6] [--speed 1.1] [--tag raw]
Writes raw fal ElevenLabs MP3 + timestamps to video/assets/vo2/<tag>/.
Never prints key values.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_vo  # noqa: E402  (same voice, fal multilingual-v2, stability/similarity/style)

NEW = {
    "S5": "Then it reads everything back. Thirty-six of thirty-six checks passed, on real Google and Slack. Crash it mid-run, and it resumes without a single duplicate. And you can ask it, what if Wei doesn't show up? It simulates the day before it happens, and names your single points of failure.",
    "S6": "We can't predict the day. We can be ready for it. Second Shift.",
}

args = sys.argv[1:]
speed = 1.1
tag = "raw"
if "--speed" in args:
    i = args.index("--speed"); speed = float(args[i + 1]); del args[i:i + 2]
if "--tag" in args:
    i = args.index("--tag"); tag = args[i + 1]; del args[i:i + 2]
targets = args or list(NEW)

out = gen_vo.ROOT / "video" / "assets" / "vo2" / tag
out.mkdir(parents=True, exist_ok=True)
gen_vo.OUT = out
gen_vo.SCENES = {**gen_vo.SCENES, **NEW}
for s in targets:
    gen_vo.tts_fal(s, speed)
