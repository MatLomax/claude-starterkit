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

gh-run-wait.py, the helper the deny message names for waiting on a GitHub Actions run, is the one
sanctioned sleeping script, and this guard sets its limits: it runs only in the background (in the
foreground it is sleep-then-check polling), as one direct call per command with literal arguments,
at most 6 hours (`--timeout` up to 21600) and checking at most every 10 seconds (`--interval` 10 or
more). Using it for anything but waiting on that run, or writing another sleeping script, is a
disguised delay. Recognising a run is fail-closed: the whole command is tokenized in one pass (so a
multi-line quoted commit message stays one word), and a segment with a word whose last path
component is `gh-run-wait.py` runs it unless its command is one that only reads, copies or prints
a file (`git`, `grep`, `cat`, `chmod`, `echo`, ...; Python only with `-c` / `-m`), with no command
substitution and no shell or `xargs` elsewhere in the command to run what it prints. Quoted words
of any other command (`bash -lc "..."`, `eval`, `pwsh -Command`) and heredocs fed to a shell are
checked the same way. `--help` returns at once and may run in the foreground.
"""
import json
import os
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
    """(command text without heredoc bodies, [(text before the heredoc opener, body, opener line)])."""
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
            docs.append((line[:m.start()], "\n".join(body), line))
    return "\n".join(outer), docs


def matches(text, patterns):
    return any(p.search(text) for p in patterns)


def sleeps(cmd):
    outer, docs = split_heredocs(cmd)
    if matches(outer, SHELL_PATTERNS):
        return True
    if INTERPRETER.search(outer) and matches(outer, CODE_PATTERNS):
        return True
    for opener, body, _ in docs:
        if SHELL.search(opener) and matches(body, SHELL_PATTERNS):
            return True
        if INTERPRETER.search(opener) and matches(body, CODE_PATTERNS):
            return True
    return False



HELPER = "gh-run-wait.py"
MAX_TIMEOUT, MIN_INTERVAL = 21600, 10
# a word that mentions the helper as a file name (not test_gh-run-wait.py, not gh-run-wait.pyc)
HELPER_MENTION = re.compile(r"(?<![\w.-])gh-run-wait\.py(?!\.?[\w-])", re.IGNORECASE)
# commands that read, copy or print a file but cannot run it (PowerShell's too; names are lowercased)
READERS = {"git", "grep", "rg", "cat", "head", "tail", "less", "ls", "chmod", "cp", "mv", "rm", "diff",
           "wc", "file", "stat", "echo", "printf", "gh", "get-content", "gc", "type", "select-string",
           "sls", "get-item", "get-childitem", "dir", "copy-item", "move-item", "remove-item", "test-path",
           "write-output", "write-host"}
# commands that run text they are given: with one in the command, a reader's mention is not exempt
EXECUTORS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "pwsh", "powershell", "cmd", "eval", "source",
             ".", "xargs", "parallel", "ssh", "iex", "invoke-expression"}
# commands that run the command after them: `sudo bash`, `env bash` run a shell
WRAPPERS = {"env", "sudo", "doas", "nohup", "nice", "timeout", "stdbuf", "command", "exec", "time", "ionice"}
STDIN_INTERPRETERS = {"node", "perl", "ruby", "php", "deno", "bun"}
QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")
SSH_VALUE_FLAGS = set("-B -b -c -D -E -e -F -I -i -J -L -l -m -O -o -p -Q -R -S -W -w".split())
KEYWORDS = {"!", "{", "}", "if", "then", "else", "elif", "do", "done", "fi", "while", "until", "time", "esac"}
LOOPS = {"while", "until", "for", "select"}
PYTHON = re.compile(r"^(?:python[\d.]*w?|pypy[\d.]*|py)$")
PY_VALUE_FLAGS = {"-W", "-X"}
PY_CODE_FLAG = re.compile(r"^-[bBdEiIOqsSuvx]*[cm]")
REDIRECT = re.compile(r"^(?:\d*|&)(?:>>|>\||>&|<&|>|<)")
ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")


class Word:
    def __init__(self):
        self.value, self.quoted, self.expands = "", False, False

    @staticmethod
    def of(value):
        w = Word()
        w.value = value
        return w


class Segment:
    def __init__(self, subst=False):
        self.words, self.subst = [], subst


def tokenize(text, powershell=False):
    """The simple commands in a shell command, as Segments of Words, in one pass over the whole text.

    Quotes are removed from a word's value (a multi-line quoted string stays one word); a backslash
    is kept before a letter, digit or backslash (Windows paths) and escapes anything else. `;` `&` `|`
    `(` `)` a backtick and a newline end a segment; a segment inside or holding `$(` or a backtick
    has `subst` set. In PowerShell the backtick escapes the next character instead and a backslash is
    literal. Raises ValueError on an unbalanced quote."""
    segs, seg, word, i, n = [], Segment(), None, 0, len(text)

    def end_word():
        nonlocal word
        if word is not None:
            seg.words.append(word)
            word = None

    def end_segment(subst=False):
        nonlocal seg
        end_word()
        if seg.words:
            segs.append(seg)
        seg = Segment(subst)

    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c in " \t\r":
            end_word()
        elif c == "#" and word is None:
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif c == "`" and powershell:
            word = word or Word()
            word.value += nxt
            i += 2
            continue
        elif c == "`":
            seg.subst = True
            end_segment(subst=True)
        elif c == "&" and (nxt == ">" or word is not None and word.value[-1:] in "<>" and word.value):
            word = word or Word()
            word.value += c
        elif c in ";&|()\n":
            inner = c == "(" and word is not None and word.value.endswith("$")
            if inner:
                seg.subst = True
            end_segment(subst=inner)
        elif c == "\\" and not powershell:
            word = word or Word()
            if nxt == "\n":
                i += 2
                continue
            word.value += (c + nxt) if (nxt.isalnum() or nxt == "\\") else nxt
            i += 2
            continue
        elif c == "'":
            word = word or Word()
            word.quoted = True
            close = text.find("'", i + 1)
            if close < 0:
                raise ValueError("unbalanced single quote")
            word.value += text[i + 1:close]
            i = close + 1
            continue
        elif c == '"':
            word = word or Word()
            word.quoted = True
            i += 1
            while True:
                if i >= n:
                    raise ValueError("unbalanced double quote")
                d = text[i]
                if d == '"':
                    break
                esc = "`" if powershell else "\\"
                if d == esc and i + 1 < n and (powershell or text[i + 1] in '"\\$`\n'):
                    if text[i + 1] != "\n":
                        word.value += text[i + 1]
                    i += 2
                    continue
                if d == "`" and not powershell or d == "$" and text[i + 1:i + 2] == "(":
                    seg.subst = True
                if d == "$" or d == "`" and not powershell:
                    word.expands = True
                word.value += d
                i += 1
        else:
            word = word or Word()
            if c == "$":
                word.expands = True
            word.value += c
        i += 1
    end_segment()
    return segs


def command_name(word):
    name = word.value.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def names_helper(word):
    return word.value.replace("\\", "/").rsplit("/", 1)[-1].lower() == HELPER


def head(words):
    """(index, name) of the command a segment runs, past VAR=value assignments and shell keywords."""
    i = 0
    while i < len(words) and (words[i].value in KEYWORDS and not words[i].quoted or ASSIGNMENT.match(words[i].value)):
        i += 1
    return i, (command_name(words[i]) if i < len(words) else "")


def python_code_flag(words):
    """Whether a Python interpreter's own flags (before the script) include -c or -m."""
    j = 0
    while j < len(words) and words[j].value.startswith("-") and words[j].value != "-":
        if PY_CODE_FLAG.match(words[j].value):
            return True
        j += 2 if words[j].value in PY_VALUE_FLAGS else 1
    return False


def git_runs_code(words):
    """Whether a git command can run a program it is given: bisect run, rebase --exec, a ! alias, or a
    config set with -c / --config-env (core.pager, core.editor, diff.external, ...)."""
    j = 1
    while j < len(words) and words[j].value.startswith("-"):
        if words[j].value.startswith(("-c", "--config-env")):
            return True
        j += 2 if words[j].value in ("-C", "--git-dir", "--work-tree", "--namespace") else 1
    return any(w.value in ("bisect", "--exec", "-x") or w.value.startswith(("--exec=", "!")) or "=!" in w.value
               for w in words)


def ssh_remote(words, i):
    """The remote command words of an ssh segment (empty when ssh runs a shell on its stdin)."""
    j = i + 1
    while j < len(words) and words[j].value.startswith("-"):
        j += 2 if words[j].value in SSH_VALUE_FLAGS else 1
    return words[j + 1:]


def runs_input(words, i, name):
    """Whether a segment runs text it is given: a shell, eval, xargs (also behind sudo / env / ...),
    ssh with no remote command, or an interpreter reading its program from stdin."""
    if name == "ssh":
        return not ssh_remote(words, i)
    if name in EXECUTORS:
        return True
    if name in WRAPPERS:
        return any(command_name(w) in EXECUTORS | STDIN_INTERPRETERS or PYTHON.match(command_name(w))
                   for w in words[i + 1:] if not w.quoted)
    if PYTHON.match(name) or name in STDIN_INTERPRETERS:
        j = i + 1
        while j < len(words) and words[j].value.startswith("-") and words[j].value != "-":
            if PY_CODE_FLAG.match(words[j].value):
                return False
            j += 2 if words[j].value in PY_VALUE_FLAGS else 1
        return j >= len(words) or words[j].value == "-"
    return False


class Call:
    """One run of the helper: its argument words (None if unreadable) and whether it is a direct call."""
    def __init__(self, args, direct):
        self.args, self.direct, self.looped = args, direct, False


def is_help(args):
    for w in args:
        if w.value == "--":
            return False
        if w.value in ("-h", "--help"):
            return True
    return False


def feeds_runner(line):
    """Whether a heredoc opener line feeds its body to something that runs it (quoted text ignored)."""
    for word in re.split(r"[\s;&|()]+", QUOTED.sub(" ", line)):
        name = command_name(Word.of(word.strip("\"'")))
        if name in EXECUTORS or name in STDIN_INTERPRETERS or PYTHON.match(name):
            return True
    return False


def real_heredocs(text):
    """split_heredocs, keeping only the openers that are not inside a quoted string."""
    outer, docs = split_heredocs(text)
    if not docs:
        return outer, docs
    stack, lines, keep, out, i = ["n"], text.split("\n"), [], [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        starts = {m.start(): m for m in HEREDOC.finditer(line)}
        j = 0
        while j < len(line):
            c, top = line[j], stack[-1]
            if j in starts and top in "ns":
                m = starts[j]
                strip, delim, body = m.group(0).startswith("<<-"), m.group(2), []
                while i < len(lines) and (lines[i].strip() if strip else lines[i]) != delim:
                    body.append(lines[i])
                    i += 1
                i += 1
                keep.append((line[:m.start()], "\n".join(body), line))
                j = m.end()
                continue
            if top == "'":
                if c == "'":
                    stack.pop()
            elif c == "\\":
                j += 1
            elif top == '"' and c == '"':
                stack.pop()
            elif c == "$" and line[j + 1:j + 2] == "(":
                stack.append("s")
                j += 1
            elif top == "s" and c == ")":
                stack.pop()
            elif top in "ns" and c in "'\"":
                stack.append(c)
            j += 1
    return "\n".join(out), keep


def find_calls(text, depth=0, powershell=False):
    """Every run of gh-run-wait.py in a shell command, judged fail-closed: a segment that names the
    helper runs it unless its command is a reader (or Python given -c / -m) that cannot run it."""
    if depth > 4:
        return [Call(None, False)] if HELPER_MENTION.search(text) else []
    outer, docs = real_heredocs(text)
    calls = []
    try:
        segs = tokenize(outer, powershell)
    except ValueError:
        segs = None
    if segs is None and docs:  # a `<<WORD` inside a quoted string is not a heredoc: read the text whole
        try:
            segs, outer, docs = tokenize(text, powershell), text, []
        except ValueError:
            pass
    if segs is None:
        segs = []
        first = next((w for w in outer.split() if not ASSIGNMENT.match(w)), "")
        first = first.strip("\"'").replace("\\", "/").rsplit("/", 1)[-1].lower()
        if HELPER_MENTION.search(outer) and first not in READERS:
            calls.append(Call(None, False))
    heads = [head(s.words) for s in segs]
    executor = any(runs_input(s.words, i, name) for s, (i, name) in zip(segs, heads))
    looped = re.search(r"\(\s*\)", outer) is not None or any(
        w.value in LOOPS | {"function"} and not w.quoted for s, (i, _) in zip(segs, heads) for w in s.words[:i + 1])
    for seg, (i, name) in zip(segs, heads):
        words = seg.words
        exempt = not seg.subst and (
            name in READERS and not executor and not any(ASSIGNMENT.match(w.value) for w in words[:i]) and not (name == "git" and git_runs_code(words))
            or PYTHON.match(name) and python_code_flag(words[i + 1:]))
        if exempt:
            continue
        if name == "ssh" and ssh_remote(words, i):  # ssh joins its remote command words for a remote shell
            calls += find_calls(" ".join(w.value for w in ssh_remote(words, i)), depth + 1, powershell)
            continue
        # a quoted multi-word string given to a shell (`bash -lc "cat x/gh-run-wait.py"`) is code, not a path
        code = runs_input(words, i, name) or name in ("su", "runuser")
        k = next((k for k, w in enumerate(words)
                  if names_helper(w) and not (code and w.quoted and any(ch.isspace() for ch in w.value))), None)
        if k is not None:
            args = words[k + 1:]
            if is_help(args):
                continue
            between = words[i + 1:k]
            direct = depth == 0 and (k == i or PYTHON.match(name) is not None and all(
                w.value.startswith("-") or j > 0 and between[j - 1].value in PY_VALUE_FLAGS
                for j, w in enumerate(between)))
            calls.append(Call(args, direct))
            continue
        found = []
        for w in words:
            if w.quoted:
                found += find_calls(w.value, depth + 1, powershell)
        if not found and any(HELPER_MENTION.search(w.value) for w in words if not w.quoted):
            found.append(Call(None, False))
        calls += found
    for _, body, line in docs:
        if feeds_runner(line):
            calls += find_calls(body, depth + 1, powershell)
    if looped:
        for c in calls:
            c.looped = True
    return calls


def argument_problem(args):
    """Why the helper's arguments are not allowed (None if they are): each must be literal, the
    timeout at most MAX_TIMEOUT seconds and the interval at least MIN_INTERVAL seconds."""
    skip = False
    for j, w in enumerate(args):
        if skip:
            skip = False
            continue
        r = REDIRECT.match(w.value) if not w.quoted else None
        if r:
            skip = r.end() == len(w.value)
            continue
        if w.value == "--":
            if any(x.expands for x in args[j + 1:]):
                return "its arguments must be literal (no $VAR or command substitution)"
            return None
        if w.expands:
            return "its arguments must be literal (no $VAR or command substitution)"
        for opt, ok, need in (("--timeout", lambda v: 0 < v <= MAX_TIMEOUT, f"--timeout must be 1-{MAX_TIMEOUT}"),
                              ("--interval", lambda v: v >= MIN_INTERVAL, f"--interval must be at least {MIN_INTERVAL}")):
            if w.value == opt or w.value.startswith(opt + "="):
                if w.value == opt:
                    nxt = args[j + 1] if j + 1 < len(args) else None
                    value = None if nxt is None or nxt.expands else nxt.value
                else:
                    value = w.value[len(opt) + 1:]
                if value is None or not (value.isascii() and value.isdigit()) or not ok(int(value)):
                    return f"{need} seconds (got {value if value is not None else 'no literal value'})"
    return None


def helper_verdict(cmd, background, helper, powershell=False):
    """The deny reason for a command that runs gh-run-wait.py outside its limits, else None."""
    calls = find_calls(cmd, powershell=powershell)
    if not calls:
        return None
    usage = f"`python3 {helper} <run URL>` (`py -3` on Windows)"
    if not background:
        return (
            "Blocked: gh-run-wait.py waits on a GitHub Actions run until it finishes, so it runs only "
            f"in the background: run {usage} with run_in_background: true and END YOUR TURN; its exit "
            "wakes you. In the foreground it is sleep-then-check polling. (Reading, copying or committing "
            "the file with git, grep, cat, head, tail, ls, cp and the like passes, as does --help; any "
            "other command naming it, sed included, counts as a run.)"
        )
    if len(calls) > 1 or any(c.args is None or not c.direct or c.looped for c in calls):
        return (
            f"Blocked: run gh-run-wait.py as one direct call per command, {usage} with literal "
            "arguments: not inside a loop, a function, a wrapper, another shell or a second call, so "
            "each wait stays at most 6 hours. It is the one sanctioned sleeping script; using it for "
            "anything but waiting on that run is a disguised delay."
        )
    problem = argument_problem(calls[0].args)
    if problem:
        return (
            f"Blocked: gh-run-wait.py {problem}. It waits at most 6 hours (--timeout up to "
            f"{MAX_TIMEOUT}) and checks at most every {MIN_INTERVAL} seconds (--interval {MIN_INTERVAL} "
            "or more), and returns only when the run finishes or on an error."
        )
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    ti = data.get("tool_input") or {}
    cmd = ti.get("command")
    if not isinstance(cmd, str):
        sys.exit(0)
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gh-run-wait.py").replace("\\", "/")
    try:
        reason = helper_verdict(cmd, ti.get("run_in_background") is True, helper,
                                data.get("tool_name") == "PowerShell")
    except Exception:  # never crash; a command that names the helper fails closed
        reason = (
            "Blocked: this command names gh-run-wait.py and the sleep-guard could not check it. Run it "
            f"as one direct call, `python3 {helper} <run URL>`, with run_in_background: true."
        ) if HELPER in cmd else None
    if reason:
        deny(reason)
    if not sleeps(cmd):
        sys.exit(0)

    deny(
        "Blocked: this command sleeps. Sleeping to wait on work is polling, and every poll "
        "re-sends the whole context (past ~5 minutes it re-writes the entire context into the "
        "cache). To wait on a long job: run it with run_in_background: true, then END YOUR TURN "
        "or carry on with other work; the completion notification wakes you. This holds in a "
        f"subagent too. To wait on a GitHub Actions run, run `python3 {helper} <run URL>` "
        "(`py -3` on Windows) in the background: it returns when the run changes (at most 5 "
        "minutes), and you run it again while the run is still going. Using it for anything "
        "but waiting on that run is a disguised delay. For "
        "other external state with no completion event (a remote queue), use the tool's own "
        "blocking wait in the background (`kubectl wait`, `docker wait`) or the Monitor tool "
        "with a script that prints only when the state changes. Never Monitor a job you started "
        "yourself. A disguised delay (`timeout N tail -f /dev/null`, `read -t`, `ping "
        "localhost`, a script of your own that sleeps) is a sleep too: do not route around this "
        "guard, wait the sanctioned way."
    )


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


if __name__ == "__main__":
    main()
