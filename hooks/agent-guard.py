#!/usr/bin/env python3
"""PreToolUse hook (matcher: Agent): enforce sub-agent spawn rules.

Denies an Agent spawn that omits an explicit `model`. A deny is a guardrail, so it holds under
bypassPermissions mode.

Does NOT cover (stays prose): the teammate / team-system pattern where agents are left open as
idle addressable mailboxes (the Agent tool has no live param that distinguishes it from a plain
named subagent that runs to completion and self-terminates); and Workflow-internal agent() calls
(they live inside the script, invisible here).
"""
import json
import sys


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    ti = data.get("tool_input") or {}
    model = (ti.get("model") or "").strip()
    if not model:
        deny("Set an explicit `model` on every sub-agent (opus = claude-opus-4-8 for judgment; "
             "sonnet for mechanical work; haiku for trivial sweeps). Never inherit the session model.")
    sys.exit(0)


if __name__ == "__main__":
    main()
