#!/usr/bin/env python3
"""UserPromptSubmit hook: commit-style-primer.

When the user's message asks for a commit / PR and the repo under cwd has a `.git/COMMIT_STYLE.md`,
inject that style into context at the START of the turn — so the commit message is composed to match
it, with no need to scan `git log` to re-derive the convention.

Context injection only: no prompt, no block; bypassPermissions-compatible. Fires on the request
(not the commit command), which is the right moment — before the message is written.
"""
import json
import os
import re
import sys


def find_commit_style(start):
    d = os.path.abspath(start or ".")
    for _ in range(40):
        p = os.path.join(d, ".git", "COMMIT_STYLE.md")
        if os.path.isfile(p):
            return p
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    text = (data.get("prompt") or "").lower()
    if not re.search(r"\b(commit|committing|pull request|\bpr\b|push)\b", text):
        sys.exit(0)

    path = find_commit_style(data.get("cwd") or ".")
    if not path:
        sys.exit(0)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            style = f.read()
    except Exception:
        sys.exit(0)

    print(
        "[commit-style] This repo defines a commit style at .git/COMMIT_STYLE.md — it is the SSOT: "
        "follow it and do NOT scan `git log` to re-derive it. Contents follow:\n\n" + style
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
