#!/usr/bin/env python3
"""PreToolUse hook (matcher: Write|Edit): deny a write carrying a NUL / stray control byte.

A NUL (0x00) or other stray control byte compiles fine and passes every automated gate, so only a
code read catches it — this stops it landing via a tool write in the first place. Scans the Write
`content` and the Edit `new_string`/`replace_all` payloads. A deny is a guardrail (holds under
bypassPermissions). Limit: a NUL written by a Bash-run script isn't visible here.

Allowed control chars: tab (0x09), newline (0x0a), carriage return (0x0d). Anything else in
C0 (0x00-0x1f) or the DEL/C1 range triggers a deny.
"""
import json
import sys

ALLOWED = {0x09, 0x0A, 0x0D}


def offending(text):
    if not isinstance(text, str):
        return None
    for ch in text:
        o = ord(ch)
        if (o < 0x20 and o not in ALLOWED) or o == 0x7F:
            return o
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    ti = data.get("tool_input") or {}
    for field in ("content", "new_string"):
        bad = offending(ti.get(field))
        if bad is not None:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"Write blocked: the content contains a stray control byte (0x{bad:02x}). Remove "
                    "it — NUL/control bytes pass every gate and only a code read catches them. Replace "
                    "each with the intended character (usually a space) and retry."
                ),
            }}))
            sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
