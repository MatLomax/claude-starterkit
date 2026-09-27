#!/usr/bin/env python3
"""SessionStart hook (matcher: compact): tell the post-compaction agent how to treat what it holds.

Printed to stdout, which Claude Code adds to the resumed session's context:
- the summary's "Established facts" were verified by the agent that wrote it, and are trusted as if
  the session had not been compacted (an explicit exception to "verify a record before relying on
  it");
- where the full pre-compaction transcript copy is (saved by compact-snapshot.py), as an
  optional reference to search for an exact detail the summary did not keep. It is not loaded.
"""
import glob
import json
import os
import sys

DEST = os.path.join(os.path.expanduser("~"), ".claude", "compact-transcripts")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    session = data.get("session_id") or ""
    copies = glob.glob(os.path.join(DEST, f"*-{session}.jsonl")) if session else []
    latest = max(copies, key=os.path.getmtime) if copies else None

    lines = [
        "[compact-resume] The conversation was just compacted. The summary above was written by the "
        "agent that held the full context, following the ruleset's compact instructions.",
        "- Its Established facts section is TRUSTED: treat every item as verified in this session. Do "
        "not re-check, re-query or re-read to confirm them, and do not hedge them in replies. This "
        "overrides the usual rule to verify a memory or record before relying on it. Re-verify an "
        "item only when something you observe now contradicts it, or when the summary itself marks "
        "it as unverified.",
        "- Carry on from the summary's Next step section as if the session had not been compacted.",
    ]
    if latest:
        lines.append(
            f"- Full pre-compaction transcript (reference only, NOT loaded): {latest} . Search it "
            "(grep or a targeted read, never a whole-file read) only when you need an exact detail "
            "that the summary does not hold."
        )
    else:
        lines.append("- No pre-compaction transcript copy was found for this session.")
    print("\n".join(lines))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"compact-resume: {e}", file=sys.stderr)
    sys.exit(0)
