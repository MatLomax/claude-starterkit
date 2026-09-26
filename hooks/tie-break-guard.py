#!/usr/bin/env python3
"""Stop hook: tie-break-guard.

Blocks the turn from ending when the assistant's final message leaves record-keeping undone:

1. **A claimed record with no write behind it** — "I logged it as a task", "I've saved a memory"
   — when no tool call in this turn wrote a worklog entry or a file.
2. **A promised record at turn end** — "I'll add a task for that", "I'll note it in memory" —
   when no such write happened this turn and no background work is pending (the turn is ending,
   so nothing will carry it out).
3. **Asking permission to keep a record** — "want me to log it?", "shall I add a task?" —
   recording a gap is owed, never an action a question withholds.

Bookkeeping here means keeping records true: tracker entries, recorded findings and decisions,
promised notes and memories. Checking a fact before stating it is a different obligation and is
NOT enforced here, so phrases like "not verified on hardware" never trip the hook.

Quoted material is ignored before matching — fenced code, inline code, `>` blockquotes and
double-quoted text — so describing or quoting a trigger phrase does not trip it.

Bypass-mode compatible (Stop hooks fire regardless of permission mode). Loop-safe: it never
bounces a turn more than once (respects `stop_hook_active`).
"""
import json
import re
import sys

# A tool call that writes a record: the worklog MCP (any write tool), a worklog CLI/DB command,
# or any file Write/Edit.
WORKLOG_WRITE_TOOL = re.compile(
    r"worklog.*__(task-(create|journal|decide|update|body-replace|section-\w+|link|add-blocker|"
    r"remove-blocker)|session-summary|record-edit)$")
WORKLOG_SHELL = re.compile(r"\bworklog\b|\.worklog/|tasks\.db")

RECORD_NOUN = r"(worklog|task|sub-?task|memory|memories|note|journal|decision|ledger|audit row)"
# First-person past-tense claims that a record exists (reports about other sessions' records,
# "it's logged as a task", are not claims about this turn and pass).
CLAIMS = [
    rf"\bi('ve| have)? (logged|recorded|filed|tracked|noted|journal(l)?ed|saved|captured)\b[^.\n]{{0,40}}\b(as|in|to|into|under)\b[^.\n]{{0,20}}\b{RECORD_NOUN}\b",
    rf"\bi('ve| have)? (added|created|filed|opened|wrote|written|saved)\b (a|an|the|its|one)? ?(new |follow-up |separate |worklog )?{RECORD_NOUN}\b",
]
# Future-tense promises to make a record.
PROMISES = [
    rf"\bi'?ll (log|record|file|track|journal|note|capture)\b",
    rf"\bi'?ll (add|create|open|write|save) (a|an|the)? ?(new |follow-up |separate |worklog )?{RECORD_NOUN}\b",
    r"\bi'?ll (update|add to) the worklog\b",
]
# Asking permission to make a record.
ASKS = [
    r"\b(want me to|shall i|should i|do you want me to|would you like me to) (log|record|file|track|journal|note down)\b",
    rf"\b(want me to|shall i|should i|do you want me to|would you like me to) (add|create|open|write|save) (a|an|the)? ?(new |follow-up |separate |worklog )?{RECORD_NOUN}\b",
]


def strip_quoted(text: str) -> str:
    """The message with quoted and code material removed."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))
    text = re.sub(r"\"[^\"\n]*\"", " ", text)
    text = re.sub(r"“[^”\n]*”", " ", text)
    return text


def first_match(patterns, text):
    for pattern in patterns:
        found = re.search(pattern, text)
        if found:
            return found.group(0)
    return None


def turn_tool_calls(transcript_path):
    """(name, input) for every tool call since the user's last typed message."""
    calls = []
    try:
        with open(transcript_path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except (OSError, TypeError):
        return None
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("isSidechain"):
            continue
        message = entry.get("message") or {}
        content = message.get("content")
        if entry.get("type") == "user":
            typed = isinstance(content, str) or (isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "text" for b in content))
            if typed:
                calls = []
        elif entry.get("type") == "assistant" and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    calls.append((block.get("name") or "", block.get("input") or {}))
    return calls


def wrote_record(calls) -> bool:
    """A worklog write, or any file Write/Edit (a note may live outside a memory directory)."""
    for name, params in calls:
        if WORKLOG_WRITE_TOOL.search(name):
            return True
        if name in ("Bash", "PowerShell") and WORKLOG_SHELL.search(str(params.get("command", ""))):
            return True
        if name in ("Write", "Edit", "MultiEdit") and params.get("file_path"):
            return True
    return False


def waiting_on_background(calls) -> bool:
    """The turn launched background work, so it ends waiting for a notification and a stated
    next step is a plan for that wake-up, not an abandoned promise."""
    return any(params.get("run_in_background") or name == "Agent" for name, params in calls)


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if data.get("stop_hook_active"):
        sys.exit(0)
    message = data.get("last_assistant_message") or ""
    if not message:
        sys.exit(0)
    text = strip_quoted(message).lower()

    asked = first_match(ASKS, text)
    if asked:
        block(f"Your reply asks permission to keep a record ('{asked}'). Recording a gap is owed, "
              "not an action a question withholds: write the worklog entry or memory now, then "
              "report it. If this was a genuine choice about the current work, restate it as that "
              "choice.")

    claimed = first_match(CLAIMS, text)
    promised = first_match(PROMISES, text)
    if not (claimed or promised):
        sys.exit(0)
    calls = turn_tool_calls(data.get("transcript_path"))
    if calls is None or wrote_record(calls):
        sys.exit(0)
    if claimed:
        block(f"Your reply says a record was made ('{claimed}'), but no worklog write or memory "
              "file write happened this turn. Make the record now, or correct the claim.")
    if waiting_on_background(calls):
        sys.exit(0)
    block(f"Your reply promises a record ('{promised}'), but the turn is ending and nothing was "
          "written. Write the worklog entry or memory now, then report it.")


if __name__ == "__main__":
    main()
