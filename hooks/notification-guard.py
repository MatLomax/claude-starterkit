#!/usr/bin/env python3
"""MessageDisplay + PreToolUse + PostToolUse + Stop + UserPromptSubmit hook: notification-guard.

Only the harness delivers a background job's completion: a <task-notification> or a system-reminder
that arrives as input, in a new turn. When the assistant's own text contains something shaped like
one ("Background task b1x2 completed with exit code 0", a <system-reminder> or <task-notification>
tag), the assistant wrote it, and acting on it (reading the job's output, checking its status,
starting another wait) is polling on a made-up event.

No hook can stop the tool call that follows such text in an interactive session: PreToolUse fires
before MessageDisplay sees the text, and before the text reaches the transcript. So:
- MessageDisplay (fires as the text streams) keeps the message's text so far in a per-session state
  file, and when the unquoted text holds a completion notice it sets a flag and marks the line on
  screen.
- PostToolUse and PreToolUse report a set flag to the assistant (PreToolUse denies the call), then
  clear it. PostToolUse is the first to see it in interactive sessions: the call right after the
  notice has already run, and the assistant is told before it acts on the result.
- Stop blocks a reply that ends the turn with a flag set, or whose own text holds a notice (once,
  respecting stop_hook_active).
- UserPromptSubmit clears the flag: new input starts clean.

Quoted material is ignored before matching (fenced code, inline code, `>` blockquotes,
double-quoted text), so describing a notification does not trip it. The harness's own notifications
are input, which MessageDisplay never receives.
"""
import json
import os
import re
import sys

MARKERS = [
    re.compile(r"<\s*/?\s*system-reminder\s*>", re.I),
    re.compile(r"<\s*/?\s*task-notification\s*>", re.I),
    re.compile(r"\bbackground (task|command|agent)\b[^\n]{0,80}\b(completed|finished|failed)\b[^\n]{0,40}\bexit code\b", re.I),
    re.compile(r"\[system notification\b", re.I),
]

WHY = ("Only the harness delivers a background job's completion, as input in a new turn. You wrote "
       "this yourself: nothing has been reported finished. Do not act on it: do not read the job's "
       "output, check its status or start another wait because of it. Carry on with other work, or "
       "end the turn and act when a real notification arrives. Say plainly in your reply that the "
       "completion text was your own.")

SCREEN_MARK = "[notification-guard: the line above is Claude's own text, not a real notification]\n"


def state_path(session_id):
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")
    return os.path.join(base, "notification-guard", safe + ".json")


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)


def strip_quoted(text):
    """The text with quoted and code material removed; a fence still open counts as code."""
    text = re.sub(r"```.*?(```|\Z)", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))
    text = re.sub(r"\"[^\"\n]*\"", " ", text)
    text = re.sub(r"“[^”\n]*”", " ", text)
    return text


def fabricated(text):
    """The first notification-shaped fragment in the unquoted text, or None."""
    text = strip_quoted(text)
    for pattern in MARKERS:
        found = pattern.search(text)
        if found:
            return found.group(0)
    return None


def on_display(data, path):
    state = load(path)
    if state.get("message_id") != data.get("message_id"):
        state = {"message_id": data.get("message_id"), "text": "", "flag": state.get("flag")}
    state["text"] += data.get("delta") or ""
    found = None if state.get("flag") else fabricated(state["text"])
    if found:
        state["flag"] = found
    save(path, state)
    if found:
        delta = data.get("delta") or ""
        sep = "" if delta.endswith("\n") or not delta else "\n"
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "MessageDisplay", "displayContent": delta + sep + SCREEN_MARK}}))


def take_flag(path):
    state = load(path)
    flag = state.get("flag")
    if flag:
        state["flag"] = None
        save(path, state)
    return flag


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    event = data.get("hook_event_name")
    path = state_path(data.get("session_id"))
    if event == "MessageDisplay":
        on_display(data, path)
    elif event == "UserPromptSubmit":
        if os.path.exists(path):
            os.remove(path)
    elif event == "PreToolUse":
        flag = take_flag(path)
        if flag:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": f"Your reply contains a completion notice ('{flag}'). {WHY}"}}))
    elif event == "PostToolUse":
        flag = take_flag(path)
        if flag:
            print(json.dumps({"decision": "block",
                              "reason": f"Your reply before this call contains a completion notice ('{flag}'). {WHY}"}))
    elif event == "Stop" and not data.get("stop_hook_active"):
        flag = take_flag(path) or fabricated(data.get("last_assistant_message") or "")
        if flag:
            print(json.dumps({"decision": "block",
                              "reason": f"Your reply contains a completion notice ('{flag}'). {WHY}"}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"notification-guard: {e}", file=sys.stderr)
    sys.exit(0)
