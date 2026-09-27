#!/usr/bin/env python3
"""PostCompact hook (matcher: manual, asyncRewake): carry on after a manual /compact.

A manual /compact ends at the prompt, so the work stops until the user types again, although the
summary names the next step and says whether it is authorised. This hook runs in the background
with `asyncRewake: true` and exits 2, which wakes Claude with the message below: carry on from the
summary's Next step if it is authorised to start, otherwise say in one line what it is waiting on.

Auto-compaction already continues the interrupted turn by itself, so the hook acts only on a manual
compaction: the settings matcher is `manual`, and the `trigger` field is checked again here in case
the hook is wired without the matcher.
"""
import json
import sys

MESSAGE = (
    "[compact-continue] The conversation was just compacted with /compact. Carry on from the "
    "summary's Next step now if it is authorised to start. If it is waiting on the user's go or "
    "answer, or nothing is left to do, reply with one line naming what it is waiting on and stop."
)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    if data.get("trigger", "manual") != "manual":
        return 0
    print(MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        code = main()
    except Exception as e:
        print(f"compact-continue: {e}", file=sys.stderr)
        code = 0
    sys.exit(code)
