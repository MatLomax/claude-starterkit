#!/usr/bin/env python3
# icon-reminder.py — UserPromptSubmit hook. Fires a reminder when a prompt is about icons/glyphs,
# so the "never hand-draw an SVG icon; copy real library path data verbatim" rule surfaces exactly
# when it's relevant, instead of burning always-loaded CLAUDE.md budget. Prints nothing otherwise.
import json, re, sys

try:
    prompt = json.load(sys.stdin).get("prompt", "")
except Exception:
    sys.exit(0)

# icon/glyph/lucide/heroicon, or "svg" as a whole word (avoid matching e.g. "svgo" noise is fine).
if re.search(r"\b(icon|icons|glyph|glyphs|lucide|heroicon|heroicons)\b|\bsvg\b", prompt, re.I):
    print(
        "REMINDER (HARD): do NOT hand-author or invent an SVG icon from raw path commands — a model "
        "cannot draw a legible glyph. Copy the glyph's path data VERBATIM from the repo's icon library "
        "(Lucide/Heroicons/whatever it uses). If the exact concept isn't there, pick the nearest real "
        "glyph or compose from real library primitives — never a freehand <path>/<rect>/rotate() composite."
    )
sys.exit(0)
