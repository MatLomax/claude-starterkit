#!/usr/bin/env python3
"""Stop hook: tie-break-guard.

Blocks the turn from ending when the assistant's final message DEFERS bookkeeping it already
owes — "want me to log it?", "still need to verify", "haven't verified" — and re-prompts the
model to just do it, then report. Enforces the Definition-of-Done tie-break: recording a gap /
verifying a fact is never the "action" a question withholds.

Bypass-mode compatible (Stop hooks fire regardless of permission mode). Loop-safe: it never
bounces a turn more than once (respects `stop_hook_active`), so if the model genuinely means
"I'll verify X as the next step", it rephrases and the turn ends.
"""
import json
import re
import sys


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # Already forced one continue this turn — don't loop.
    if data.get("stop_hook_active"):
        sys.exit(0)

    msg = (data.get("last_assistant_message") or "").lower()
    if not msg:
        sys.exit(0)

    triggers = [
        r"want me to log", r"should i log", r"shall i log", r"do you want me to log",
        r"want me to (check|verify|confirm|record|track)",
        r"still need to verify", r"haven'?t verified", r"left to verify",
        r"need(s)? verifying", r"here'?s what i still need to",
    ]
    if any(re.search(t, msg) for t in triggers):
        print(json.dumps({
            "decision": "block",
            "reason": (
                "You deferred bookkeeping you already owe (logging a gap / verifying a fact). "
                "That is never the 'action' a question withholds — do it now: log the gap or run "
                "the verification yourself, THEN report the result. Don't ask 'want me to log it?' "
                "or hand back an unverified claim. If you genuinely meant a real next step, restate "
                "it without the deferral phrasing."
            ),
        }))
    sys.exit(0)


if __name__ == "__main__":
    main()
