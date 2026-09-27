#!/usr/bin/env python3
"""PreCompact hook: keep a copy of the full pre-compaction transcript.

Compaction replaces the conversation with a summary. The summary carries the working state forward
(the ruleset's "# Compact instructions" section says what it must hold), but an exact detail it did
not keep (a query, a figure, a quoted message) is otherwise gone from the model's reach. This hook
copies the session transcript to `~/.claude/compact-transcripts/<timestamp>-<session_id>.jsonl`
before every compaction, so the post-compaction agent can search the original when it needs an
exact detail. The compact-resume hook (SessionStart, matcher `compact`) tells it where the copy is.

The copy is a reference, never injected into context. Only the newest KEEP copies are kept, across
all sessions. The hook never blocks a compaction: any failure is reported on stderr and it exits 0.
"""
import glob
import json
import os
import shutil
import sys
import time

KEEP = 10
DEST = os.path.join(os.path.expanduser("~"), ".claude", "compact-transcripts")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    src = data.get("transcript_path") or ""
    session = data.get("session_id") or "unknown"
    if not src or not os.path.isfile(src):
        print(f"compact-snapshot: no transcript at {src!r}", file=sys.stderr)
        return
    os.makedirs(DEST, exist_ok=True)
    dest = os.path.join(DEST, f"{time.strftime('%Y%m%d-%H%M%S')}-{session}.jsonl")
    shutil.copy2(src, dest)
    copies = sorted(glob.glob(os.path.join(DEST, "*.jsonl")), key=os.path.getmtime, reverse=True)
    for old in copies[KEEP:]:
        try:
            os.remove(old)
        except OSError:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"compact-snapshot: {e}", file=sys.stderr)
    sys.exit(0)
