#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash): git guardrails.

Denies:
  - broad staging: `git add -A|--all|-u|--update|.`, and `git commit -a|-am|--all`
    (stage only your own hunks — these sweep up other sessions' work);
  - whole-tree mutations: `git reset --hard`, `git checkout -- .`, `git restore .`,
    `git clean -f`, create-form `git stash` (path-scoped forms pass).

A deny is a guardrail, so it holds under bypassPermissions. (AI-attribution suppression is handled by
the native `attribution` setting in settings.json, not here.) The flag regexes are pragmatic — tune
at install if needed.
"""
import json
import re
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

    cmd = (data.get("tool_input") or {}).get("command") or ""

    # Broad staging.
    if re.search(r"\bgit\s+add\s+(?:-A|--all|-u|--update|\.)(?=\s|$|;|&|\|)", cmd):
        deny("Stage only your own changes: no `git add -A/./-u` (it sweeps up other sessions' "
             "work). Use `git add <the-paths-you-touched>`.")
    if re.search(r"\bgit\s+commit\b", cmd) and re.search(r"(?:^|\s)-{1,2}a(?:ll|m)?(?=\s|$)", cmd):
        deny("Stage only your own changes: no `git commit -a/-am/--all` (it commits every tracked "
             "change, including other sessions' work). Stage your paths, then plain `git commit`.")

    # Whole-tree mutations — path-scoped forms pass. Heuristic; tune at install.
    if re.search(r"\bgit\s+reset\b[^\n|;&]*--hard", cmd):
        deny("No whole-tree `git reset --hard` — it destroys other sessions' uncommitted work. "
             "Reset a specific path you own instead.")
    if re.search(r"\bgit\s+checkout\s+(?:--\s+)?(?:\.|:/)(?=\s|$|;|&|\|)", cmd):
        deny("No whole-tree `git checkout -- .` — it reverts other sessions' work. Check out a "
             "specific path you own instead.")
    if re.search(r"\bgit\s+restore\b[^\n|;&]*?\s(?:--\s+)?(?:\.|:/)(?=\s|$|;|&|\|)", cmd):
        deny("No whole-tree `git restore .` — it reverts other sessions' work. Restore a specific "
             "path you own instead.")
    if re.search(r"\bgit\s+clean\b[^\n|;&]*(?:-[a-z]*f|--force)", cmd):
        deny("No `git clean -f` — it deletes untracked files, including other sessions' scratch. "
             "Remove only your own files by name.")
    stash = re.search(r"\bgit\s+stash\b(.*)", cmd, re.S)
    if stash:
        rest = stash.group(1)
        first = (rest.strip().split() or [""])[0]
        safe = {"list", "show", "pop", "apply", "drop", "clear", "branch"}
        if first not in safe and " -- " not in rest:
            deny("No whole-tree `git stash` — it hides the entire working tree, including other "
                 "sessions' work. Scope it with `git stash push -- <your-paths>`, or don't stash.")

    sys.exit(0)


if __name__ == "__main__":
    main()
