#!/usr/bin/env python3
"""PreToolUse hook (matcher: Bash): git guardrails.

Denies:
  - broad staging: `git add -A|--all|-u|--update|.`, and `git commit -a|-am|--all`
    (stage only your own hunks — these sweep up other sessions' work);
  - whole-tree mutations: `git reset --hard`, `git checkout -- .`, `git restore .`,
    `git clean -f`, create-form `git stash` (path-scoped forms pass).

The staging checks read the argv of each `git add` / `git commit` in the command line (split on
`;`, `&&`, `||`, `|`, `&`, newlines, with heredoc bodies dropped), so a flag belonging to another
command in the same line (`rsync -a`, `grep -a`) or text inside a commit message never trips them.

A deny is a guardrail, so it holds under bypassPermissions. (AI-attribution suppression is handled by
the native `attribution` setting in settings.json, not here.) The whole-tree regexes are pragmatic —
tune at install if needed.
"""
import json
import os
import re
import shlex
import sys

HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n[ \t]*\2[ \t]*(?=\n|$)", re.S)
OPERATORS = {";", "&&", "||", "|", "&", "|&", "\n", "(", ")", ";;"}
# git's own options that take the next token as their value (`git -C <path> commit ...`).
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
# `git commit` options that take the next token as their value, when not written with `=`.
COMMIT_VALUE_LONG = {
    "--message", "--file", "--reuse-message", "--reedit-message", "--template", "--author",
    "--date", "--fixup", "--squash", "--cleanup", "--trailer", "--pathspec-from-file",
}
COMMIT_VALUE_SHORT = set("mFCct")
BROAD_PATHS = {".", "./", ":/", ":/:"}
# What may precede `git` in a simple command: `VAR=value` assignments and pass-through wrappers.
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
WRAPPERS = {"command", "sudo", "env", "exec", "time", "nice", "nohup"}


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def simple_commands(cmd):
    """The argv of each simple command in a shell command line."""
    cmd = HEREDOC.sub("", cmd)
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()\n")
        lex.whitespace = " \t\r"
        lex.whitespace_split = True
        lex.commenters = ""
        tokens = list(lex)
    except ValueError:
        tokens = [t for part in re.split(r"(;|&&|\|\||\||&|\n)", cmd) for t in (
            [part] if part in OPERATORS else part.split())]
    argv = []
    for tok in tokens:
        if tok in OPERATORS:
            if argv:
                yield argv
            argv = []
        else:
            argv.append(tok)
    if argv:
        yield argv


def git_subcommand(argv):
    """(subcommand, its args) if argv runs git, else (None, [])."""
    i = 0
    while i < len(argv) and (argv[i] in WRAPPERS or ASSIGNMENT.match(argv[i])):
        i += 1
    if i >= len(argv) or os.path.basename(argv[i]) != "git":
        return None, []
    j = i + 1
    while j < len(argv) and argv[j].startswith("-"):
        j += 2 if argv[j] in GIT_VALUE_OPTS else 1
    if j < len(argv):
        return argv[j], argv[j + 1:]
    return None, []


def add_is_broad(args):
    after_dashdash = False
    for tok in args:
        if after_dashdash or not tok.startswith("-"):
            if tok in BROAD_PATHS:
                return True
        elif tok == "--":
            after_dashdash = True
        elif tok in ("--all", "--update"):
            return True
        elif not tok.startswith("--") and ("A" in tok or "u" in tok):
            return True
    return False


def commit_is_all(args):
    skip = False
    for tok in args:
        if skip:
            skip = False
        elif tok == "--":
            return False
        elif tok == "--all":
            return True
        elif tok.startswith("--"):
            skip = tok in COMMIT_VALUE_LONG
        elif tok.startswith("-") and len(tok) > 1:
            for k, ch in enumerate(tok[1:], 1):
                if ch == "a":
                    return True
                if ch in COMMIT_VALUE_SHORT:
                    skip = k == len(tok) - 1
                    break
    return False


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cmd = (data.get("tool_input") or {}).get("command") or ""

    # Broad staging.
    for argv in simple_commands(cmd):
        sub, args = git_subcommand(argv)
        if sub == "add" and add_is_broad(args):
            deny("Stage only your own changes: no `git add -A/./-u` (it sweeps up other sessions' "
                 "work). Use `git add <the-paths-you-touched>`.")
        if sub == "commit" and commit_is_all(args):
            deny("Stage only your own changes: no `git commit -a/-am/--all` (it commits every "
                 "tracked change, including other sessions' work). Stage your paths, then plain "
                 "`git commit`.")

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
