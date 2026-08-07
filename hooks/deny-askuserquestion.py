#!/usr/bin/env python3
"""PreToolUse hook (matcher: AskUserQuestion): deny the question tool outright.

Enforces the user rule "never use the AskUserQuestion tool". A `deny` is a guardrail, so it
still fires under bypassPermissions mode (unlike a user-facing permission prompt). The reason
is shown to the model so it knows to ask in the plain message instead.
"""
import json
import sys

sys.stdin.read()  # drain stdin; the matcher already scoped us to AskUserQuestion

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            "AskUserQuestion is disabled by user rule. Ask in the plain message instead: "
            "one question at a time (never a pile), multiple-choice with one option marked "
            "(recommended), and no 'other' option — the user types their own answer if the "
            "supplied options don't fit."
        ),
    }
}))
sys.exit(0)
