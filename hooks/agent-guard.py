#!/usr/bin/env python3
"""PreToolUse hook (matcher: Agent): enforce sub-agent spawn rules.

Denies an Agent spawn that omits an explicit `model`, or that carries a `name:` (teammate/
mailbox agents are banned). A deny is a guardrail, so it holds under bypassPermissions mode.

Does NOT cover (stays prose): the Opus-4.8 pin / never-Opus-5 (the Agent tool takes a tier
shorthand — `opus`/`sonnet`/`haiku` — so this hook can't distinguish 4.8 from 5), nor
Workflow-internal agent() calls (they live inside the script, invisible to a PreToolUse hook).
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
    if ti.get("name"):
        deny("No teammate/mailbox agents: drop the `name:` param so the sub-agent runs to "
             "completion and self-terminates.")
    model = (ti.get("model") or "").strip()
    if not model:
        deny("Set an explicit `model` on every sub-agent (opus = claude-opus-4-8 for judgment; "
             "sonnet for mechanical work; haiku for trivial sweeps). Never inherit the session model.")
    sys.exit(0)


if __name__ == "__main__":
    main()
