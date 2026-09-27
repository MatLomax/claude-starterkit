#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash|PowerShell): deny any shell command that sleeps.

Waiting on a job with `sleep` is polling: every check re-sends the whole context, and a sleep past
the ~5-minute prompt-cache lifetime re-writes the entire context into the cache on the next call.
A backgrounded command or agent already sends a completion notification, so the right wait is to
end the turn. A deny is a guardrail (holds under bypassPermissions).

Caught: `sleep` / `/bin/sleep` / `usleep` / `gsleep` in command position (start of line, after `;`
`&` `|` `(` a backtick `$(` `{`, after `do`/`then`/`else`, after a wrapper like
`nohup`/`timeout N`/`env`, or as the start of a `-c` string), PowerShell `Start-Sleep`,
`[Thread]::Sleep(` and `Wait-Event -Timeout`, cmd's `timeout /t N`, and interpreter sleeps
(`time.sleep(`, `asyncio.sleep(`, `setTimeout(`, Perl's `select(undef, undef, undef, N)`) when the
command runs an interpreter inline. Disguised sleeps count as sleeps: `tail -f /dev/null` (with or
without a `timeout` around it), `read -t N`, and `ping` of the local host as a timer. A
heredoc body is checked only when it feeds a shell (shell patterns) or an interpreter (interpreter
patterns); text fed to anything else (`git commit -F -`, `cat > file`) is data, not a wait. A quoted
mention such as `grep "sleep 60"` is not in command position and passes.

Not covered: a `Monitor` script (a different tool, and its loop costs no tokens), and a sleep
inside a script file the command runs.
"""
import json
import re
import sys

CMD_POS = r"(?:^|[;&|(`{\n]|\$\(|\b(?:do|then|else|nohup|env|exec|xargs|command|builtin)\s+|\btimeout\s+\S+\s+|-c\s+[\"'])"
SHELL_PATTERNS = [
    re.compile(CMD_POS + r"\s*(?:/usr)?(?:/bin/)?(?:u|g)?sleep(?:\s|$|;)", re.IGNORECASE),
    re.compile(r"\bStart-Sleep\b", re.IGNORECASE),
    re.compile(r"\[(?:System\.)?(?:Threading\.)?Thread\]::Sleep\s*\(", re.IGNORECASE),
    re.compile(r"\bWait-Event\b[^;|\n]*-Timeout\b", re.IGNORECASE),
    re.compile(CMD_POS + r"\s*timeout(?:\.exe)?\s+/t\s+\d", re.IGNORECASE),
    # disguised sleeps: a no-op that blocks, bounded by a timeout or not
    re.compile(CMD_POS + r"\s*tail\s+(?:-\w+\s+)*-\w*[fF]\w*\s+(?:-\w+\s+)*/dev/null\b"),
    re.compile(CMD_POS + r"\s*read\b[^;&|\n]*\s-\w*t\s*\d"),
    re.compile(CMD_POS + r"\s*ping\b[^;&|\n]*\s(?:127\.0\.0\.1|localhost|::1)\b", re.IGNORECASE),
]
CODE_PATTERNS = [
    re.compile(r"\b(?:time|asyncio)\.sleep\s*\("),
    re.compile(r"\bsetTimeout\s*\("),
    re.compile(r"\bselect\s*\(\s*undef\s*,\s*undef\s*,\s*undef\s*,"),
]
SHELL = re.compile(r"(?:^|[\s;&|(/])(?:ba|z|da|k)?sh\b|\b(?:pwsh|powershell)\b", re.IGNORECASE)
INTERPRETER = re.compile(r"(?:^|[\s;&|(/])(?:python[\d.]*|node|deno|bun|ruby|perl|php)\b")
HEREDOC = re.compile(r"(?<!<)<<-?\s*(['\"]?)([A-Za-z_][\w.-]*)\1")


def split_heredocs(cmd):
    """(command text without heredoc bodies, [(text before the heredoc opener, body)])."""
    outer, docs, lines, i = [], [], cmd.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        outer.append(line)
        i += 1
        for m in HEREDOC.finditer(line):
            strip, delim, body = m.group(0).startswith("<<-"), m.group(2), []
            while i < len(lines) and (lines[i].strip() if strip else lines[i]) != delim:
                body.append(lines[i])
                i += 1
            i += 1
            docs.append((line[:m.start()], "\n".join(body)))
    return "\n".join(outer), docs


def matches(text, patterns):
    return any(p.search(text) for p in patterns)


def sleeps(cmd):
    outer, docs = split_heredocs(cmd)
    if matches(outer, SHELL_PATTERNS):
        return True
    if INTERPRETER.search(outer) and matches(outer, CODE_PATTERNS):
        return True
    for opener, body in docs:
        if SHELL.search(opener) and matches(body, SHELL_PATTERNS):
            return True
        if INTERPRETER.search(opener) and matches(body, CODE_PATTERNS):
            return True
    return False


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cmd = (data.get("tool_input") or {}).get("command")
    if not isinstance(cmd, str) or not sleeps(cmd):
        sys.exit(0)

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            "Blocked: this command sleeps. Sleeping to wait on work is polling, and every poll "
            "re-sends the whole context (past ~5 minutes it re-writes the entire context into the "
            "cache). To wait on a long job: run it with run_in_background: true, then END YOUR TURN "
            "or carry on with other work; the completion notification wakes you. This holds in a "
            "subagent too. For external state with no completion event (CI, a remote queue), use "
            "the tool's own blocking wait in the background (e.g. `gh run watch <id> "
            "--exit-status`) or the Monitor tool with a script that prints only when the state "
            "changes. Never Monitor a job you started yourself. A disguised delay (`timeout N "
            "tail -f /dev/null`, `read -t`, `ping localhost`) is a sleep too: do not route around "
            "this guard, wait the sanctioned way."
        ),
    }}))
    sys.exit(0)


if __name__ == "__main__":
    main()
