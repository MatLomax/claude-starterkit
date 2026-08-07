#!/usr/bin/env python3
"""UserPromptSubmit hook: correction-primer.

When the incoming user message reads as a CORRECTION or a QUESTION, inject a one-line reminder into
the model's context for that turn: acknowledge + state what it changes + STOP (don't start executing
off a correction or a bare question). Bypass-mode compatible: it only injects context, never prompts
or blocks.

Best-effort NUDGE, not a classifier. Precedence: a bare option-selection / ack stays silent; anything
question-shaped or correction-shaped injects (even if it also contains an action word like "do it" —
a correction that says HOW is still a correction); everything else (plain statements, clean
imperatives like "go build it") stays silent. False positives are cheap — the reminder just tells the
model to check for a go it can then act on. Any error exits 0 (never breaks a turn).
"""
import json
import re
import sys


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    text = (data.get("prompt") or "").strip()
    if not text:
        sys.exit(0)
    low = text.lower()

    # Bare option-selection / trivial ack — an ANSWER, not a correction: stay quiet.
    if re.fullmatch(r"[\s\d.,]+", low) or low in {
        "yes", "ok", "okay", "sure", "yep", "yeah", "y", "no", "nope", "lgtm",
    }:
        sys.exit(0)

    # Question-shaped or correction-shaped → inject (this wins over any action word inside).
    is_question = text.endswith("?") or bool(re.match(
        r"^(why|how|what|whats|when|where|which|who|can|could|would|should|is|are|isn'?t|"
        r"couldn'?t|wouldn'?t|shouldn'?t|do you|does|did you|have you|is there|any way)\b",
        low,
    ))
    is_correction = bool(re.match(
        r"^(no\b|not\b|nope|actually|instead|rather|wait\b|hang on|hmm|"
        r"that'?s (wrong|not|incorrect)|you should have|why did you|i said|i meant)",
        low,
    )) or ("should have" in low)

    if is_question or is_correction:
        print(
            "[correction-primer] This message reads as a correction/question, not a "
            "start-imperative. Acknowledge it, state precisely what it changes in the plan, "
            "and STOP — do not begin writing/editing unless it explicitly says go (go / do it / "
            "build it / change it now / ship it). Present-and-wait beats execute."
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
