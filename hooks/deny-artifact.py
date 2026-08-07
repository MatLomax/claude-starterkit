#!/usr/bin/env python3
"""PreToolUse hook (matcher: Artifact): deny publishing artifacts to claude.ai.

Enforces "never publish artifacts": keep the design craft, but Write deliverables as local files.
A deny is a guardrail, so it holds under bypassPermissions mode.
"""
import json
import sys

sys.stdin.read()  # matcher already scoped us to the Artifact tool

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            "Publishing artifacts to claude.ai is disabled by user rule. Keep the design craft, but "
            "Write the deliverable as a local file (or scratch if throwaway) instead of the Artifact "
            "tool."
        ),
    }
}))
sys.exit(0)
