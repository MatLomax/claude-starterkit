#!/usr/bin/env python3
"""SessionStart + PreToolUse (Write|Edit|Bash|PowerShell) hook: keep a project's auto memory inside
the project.

Claude Code keeps auto memory in <config dir>/projects/<project>/memory/, where <project> is derived
from the path the project was opened at. The same project opened at two paths (an sshfs mount and
the machine it lives on, say) gets two unrelated memories, and `autoMemoryDirectory` accepts only an
absolute path, so a setting cannot say "inside this project".

This hook links that default directory to <project>/.claude/memory/ (a symlink, or a directory
junction on Windows). Every path the project is opened from gets its own link to the one directory.
The project's memory directory is created only when the first memory is saved:
- SessionStart links the default directory when <project>/.claude/memory/ already exists, so the
  session reads it. Claude Code resolves the memory directory after SessionStart hooks run. When the
  default directory already holds files (saved before the link existed, or written by a Bash
  command), they are moved into the project and the directory is linked.
- PreToolUse on a Write or Edit into the default directory creates <project>/.claude/memory/, moves
  anything already there into it and links the default directory before the write runs, so the first
  memory lands in the project.
In a git repository the target is also added to the repository's .git/info/exclude. PreToolUse on
Bash and PowerShell adds it too when the project's memory is linked, so a repository created or
cloned during a session excludes its memory from the next shell command on, before a `git add`.

PreToolUse on Bash and PowerShell denies a command that writes into a memory directory (any
.claude/memory, or a per-path <config dir>/projects/<name>/memory) instead of only reading it: memory
files are written with the Write and Edit tools, so these hooks see them. Deleting one is allowed.

Claude Code takes any .git entry as a repository root, even one git itself rejects. When the root it
would use is not a real repository (a stray .git holding only info/exclude, say), or is the home
directory, every folder under it without its own repository shares one memory. The hook then links
nothing: SessionStart tells the user, and a Write or Edit into that memory is denied, so nothing is
saved where it would be stranded once the .git is removed.

<project> is resolved the way Claude Code resolves it, from the session's project directory: the
nearest directory above it holding a .git entry (a linked worktree maps to its main checkout), or the
project directory itself outside a git repository; every character other than an ASCII letter or
digit is replaced by "-", and a name longer than 200 characters is cut to 200 with a hash of the full
path appended.

The hook changes nothing when auto memory is pointed elsewhere (autoMemoryDirectory,
CLAUDE_CODE_REMOTE_MEMORY_DIR, CLAUDE_CODE_PROJECT_DIR_NAME, CLAUDE_COWORK_MEMORY_PATH_OVERRIDE),
when the default directory is already a link (a link that points somewhere else was made on
purpose), or when the project is the home directory or inside the config dir: <home>/.claude is the
config dir, and Claude Code keeps its own memory stores in its memory/ directory.
It prints nothing unless it linked something or could not, and then only a JSON systemMessage for the
user (SessionStart stdout would otherwise become session context).
"""
import json
import os
import re
import shutil
import sys

MAX_NAME = 200
EXCLUDE_LINE = "/.claude/memory/"


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def utf16_units(s):
    b = s.encode("utf-16-le", "surrogatepass")
    return [int.from_bytes(b[i:i + 2], "little") for i in range(0, len(b), 2)]


def js_hash(s):
    """The 32-bit string hash Claude Code appends to long project names, in base 36."""
    h = 0
    for u in utf16_units(s):
        h = (h * 31 + u) & 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 0x100000000
    h = abs(h)
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        h, r = divmod(h, 36)
        out = digits[r] + out
        if h == 0:
            return out


def project_name(path):
    name = "".join(chr(u) if u < 128 and chr(u).isalnum() else "-" for u in utf16_units(path))
    if len(name) <= MAX_NAME:
        return name
    return f"{name[:MAX_NAME]}-{js_hash(path)}"


def is_entry(p):
    """A .git entry that marks a repository root: a directory or a file, not a symlink or junction."""
    return os.path.lexists(p) and not is_link(p) and (os.path.isdir(p) or os.path.isfile(p))


def git_root(start):
    d = os.path.abspath(start)
    while True:
        if is_entry(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read().strip()


def canonical_root(root):
    """The main checkout for a linked worktree; any other repository is its own root."""
    try:
        text = read(os.path.join(root, ".git"))
    except OSError:
        return root
    if not text.startswith("gitdir:"):
        return root
    try:
        gitdir = os.path.normpath(os.path.join(root, text[7:].strip()))
        common = os.path.normpath(os.path.join(gitdir, read(os.path.join(gitdir, "commondir"))))
        if os.path.dirname(gitdir) != os.path.join(common, "worktrees"):
            return root
        back = os.path.normpath(os.path.join(gitdir, read(os.path.join(gitdir, "gitdir"))))
        if back != os.path.join(root, ".git"):
            return root
    except OSError:
        return root
    if os.path.basename(common) != ".git":
        return root if os.path.lexists(os.path.join(common, ".git")) else common
    return os.path.dirname(common)


def common_git_dir(root):
    """The directory git reads info/exclude from for the repository at root."""
    dot = os.path.join(root, ".git")
    if os.path.isdir(dot):
        return dot
    try:
        text = read(dot)
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    gitdir = os.path.normpath(os.path.join(root, text[7:].strip()))
    try:
        return os.path.normpath(os.path.join(gitdir, read(os.path.join(gitdir, "commondir"))))
    except OSError:
        return gitdir


def memory_dir_setting(root):
    for p in (
        os.path.join(config_dir(), "settings.json"),
        os.path.join(root, ".claude", "settings.json"),
        os.path.join(root, ".claude", "settings.local.json"),
    ):
        try:
            with open(p, encoding="utf-8") as f:
                if json.load(f).get("autoMemoryDirectory"):
                    return p
        except (OSError, ValueError, AttributeError):
            continue
    return None


def redirected():
    """Why auto memory is not in the default per-project directory, or None when it is."""
    for var in ("CLAUDE_COWORK_MEMORY_PATH_OVERRIDE", "CLAUDE_CODE_REMOTE_MEMORY_DIR"):
        if os.environ.get(var):
            return var
    pinned = os.environ.get("CLAUDE_CODE_PROJECT_DIR_NAME", "")
    if os.environ.get("CLAUDE_CONFIG_DIR") and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", pinned):
        return "CLAUDE_CODE_PROJECT_DIR_NAME"
    return None


def ensure_excluded(root):
    common = common_git_dir(root)
    if not common:
        return
    info = os.path.join(common, "info")
    exclude = os.path.join(info, "exclude")
    try:
        with open(exclude, encoding="utf-8") as f:
            existing = f.read()
    except FileNotFoundError:
        existing = ""
    if EXCLUDE_LINE in existing.splitlines():
        return
    os.makedirs(info, exist_ok=True)
    with open(exclude, "a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(EXCLUDE_LINE + "\n")


def is_link(p):
    """Whether p is a symlink or a directory junction."""
    if os.path.islink(p):
        return True
    try:
        os.readlink(p)
        return True
    except (OSError, ValueError, AttributeError):
        return False


def make_link(target, link):
    if os.name == "nt":
        # A junction needs neither administrator rights nor Developer Mode, unlike a symlink.
        import _winapi
        _winapi.CreateJunction(target, link)
    else:
        os.symlink(target, link)


def norm(p):
    return os.path.normcase(os.path.abspath(os.path.expanduser(p)))


HEAD_TEXT = re.compile(r"^ref:[ \t]*refs/|^[0-9a-f]{40}(?:[0-9a-f]{24})?\s*$")


def gitdir_problem(gitdir):
    """Why gitdir is not a git directory as git itself judges one, or None when it is."""
    head = os.path.join(gitdir, "HEAD")
    if not os.path.islink(head):
        try:
            if os.path.getsize(head) > 4096:
                return "no valid HEAD"
            with open(head, encoding="utf-8", errors="replace") as f:
                if not HEAD_TEXT.search(f.read(255)):
                    return "no valid HEAD"
        except OSError:
            return "no HEAD"
    common = gitdir
    try:
        common = os.path.normpath(os.path.join(gitdir, read(os.path.join(gitdir, "commondir"))))
    except OSError:
        pass
    for sub in ("objects", "refs"):
        if not os.path.isdir(os.path.join(common, sub)):
            return f"no {sub} folder"
    return None


def repo_problem(root):
    """Why root's .git is not a git repository, or None when it is one."""
    dot = os.path.join(root, ".git")
    if os.path.isdir(dot):
        return gitdir_problem(dot)
    try:
        text = read(dot)
    except OSError:
        return "unreadable"
    if not text.startswith("gitdir:"):
        return "a file without a gitdir line"
    gitdir = os.path.normpath(os.path.join(root, text[7:].strip()))
    if not os.path.isdir(gitdir):
        return f"its gitdir {gitdir} is missing"
    if gitdir_problem(gitdir):
        return f"its gitdir {gitdir} is not a repository"
    return None


def shared_root(root):
    """Why the git root Claude Code would use lumps unrelated folders into one memory, or None.

    Returns (warning for the user at session start, reason for denying a memory write)."""
    dot = os.path.join(root, ".git")
    if norm(root) == norm(os.path.expanduser("~")):
        return (f"project-memory: your home directory {root} is a git repository, so every folder under "
                "it without its own repository shares one memory. Move the repository out of "
                f"{root} (a dotfiles repo works as a bare repository used with --git-dir). Memory can't "
                "be saved until it's removed.",
                f"project-memory: not saved. Your home directory {root} is a git repository, so this "
                "memory would land in the memory shared by every folder under it, and be stranded there "
                "once the repository is moved. Tell the user that memory can't be saved until the "
                f"repository is moved out of {root}, and what you were going to save.")
    reason = repo_problem(root)
    if reason is None:
        return None
    return (f"project-memory: {dot} is not a git repository ({reason}), so Claude Code treats {root} as "
            "this session's project, and every folder under it without its own repository shares one "
            f"memory. Delete {dot} if nothing uses it. Memory can't be saved until it's removed.",
            f"project-memory: not saved. {dot} is not a git repository ({reason}), so this memory would "
            f"land in the memory shared by every folder under {root}, and be stranded there once that "
            f".git is removed. Tell the user that memory can't be saved until {dot} is deleted, and what "
            "you were going to save.")


def locate(data):
    """(project root, whether it is a git repository, shared_root() of it), or None when the hook
    should stand aside."""
    start = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    start = os.path.abspath(start)
    if redirected():
        return None
    root = git_root(start)
    is_git = root is not None
    problem = shared_root(root) if is_git else None
    root = canonical_root(root) if is_git else start
    if os.path.dirname(root) == root or memory_dir_setting(root):
        return None
    if problem:
        return root, is_git, problem
    # The home directory's .claude is the config dir, where Claude Code keeps its own memory stores
    # (memory/personal/); a project there is not linked.
    config = norm(config_dir())
    if norm(os.path.join(root, ".claude")) == config or norm(root).startswith(config + os.sep):
        return None
    return root, is_git, None


def settle(link, target, create):
    """Link the default memory directory to the project's; returns a message for the user or None.

    Files already in the default directory are moved into the project first. With create unset, a
    project without a memory directory and an empty default directory are left as they are."""
    if is_link(link):
        if not os.path.isdir(link):
            return f"project-memory: {link} is a broken link, so auto memory cannot be saved there."
        return None
    if os.path.lexists(link) and not os.path.isdir(link):
        return f"project-memory: {link} is a file, so it was not linked to {target}."
    held = sorted(os.listdir(link)) if os.path.isdir(link) else []
    if not held and not create and not os.path.isdir(target):
        return None
    if os.path.lexists(target) and not os.path.isdir(target):
        return f"project-memory: {target} is a file, so auto memory stays in {link}."
    clashes = [n for n in held if os.path.lexists(os.path.join(target, n))]
    if clashes:
        return (f"project-memory: {link} and {target} both hold {', '.join(clashes)}, so auto memory "
                f"stays in {link}. Merge them into {target} and delete {link}; the next session links it.")
    os.makedirs(target, exist_ok=True)
    for n in held:
        shutil.move(os.path.join(link, n), os.path.join(target, n))
    if os.path.isdir(link):
        os.rmdir(link)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    make_link(target, link)
    moved = f" ({len(held)} file{'s' if len(held) != 1 else ''} moved there)" if held else ""
    return f"project-memory: auto memory for this project now lives in {target}{moved}"


# A memory directory named in a command: a project's .claude/memory, or a per-path
# <config dir>/projects/<name>/memory (names start with "-", or "C--" for a Windows drive).
MEMORY_PATH = re.compile(r"(?:\.claude|projects[\\/]+(?:-|[A-Za-z]--)[^\\/\s'\"`]*)[\\/]+memory(?![\w.-])",
                         re.IGNORECASE)
SHELL_DENY = ("project-memory: memory files are written with the Write or Edit tool, not a shell command, "
              "so the memory hooks see them. Use Write to create a memory or Edit to change one.")
# commands that read or delete a file but cannot write one (PowerShell's too; names are lowercased)
READS = {"cat", "less", "more", "head", "tail", "ls", "tree", "stat", "file", "wc", "grep", "egrep", "fgrep",
         "rg", "ag", "diff", "cmp", "readlink", "realpath", "basename", "dirname", "test", "[", "du", "bat",
         "md5sum", "sha1sum", "sha256sum", "jq", "cd", "pushd", "popd", "echo", "printf", "rm", "rmdir",
         "unlink", "get-content", "gc", "type", "get-childitem", "gci", "dir", "select-string", "sls",
         "test-path", "get-item", "gi", "resolve-path", "rvpa", "get-filehash", "measure-object",
         "format-hex", "set-location", "sl", "push-location", "pop-location", "split-path", "join-path",
         "write-output", "write-host", "remove-item", "ri", "del", "erase", "rd"}
COPIES = {"cp", "copy-item", "cpi", "copy", "rsync"}  # read-only when the memory path is not the destination
# commands that run code they are given: a memory path anywhere in their words counts
RUNNERS = re.compile(r"^(?:python[\d.]*w?|pypy[\d.]*|py|node|deno|bun|perl|ruby|php|sh|bash|zsh|dash|ksh|"
                     r"fish|pwsh|powershell|cmd|eval|source|\.|xargs|ssh|iex|invoke-expression)$")
WRAPPERS = {"sudo", "doas", "env", "command", "nice", "nohup", "time", "exec", "stdbuf", "ionice"}
SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "|&", ";;"}
HEREDOC = re.compile(r"(?<!<)<<-?\s*(['\"]?)([A-Za-z_][\w.-]*)\1")
ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")


def split_heredocs(cmd):
    """(command text without heredoc bodies, [(the line opening the heredoc, its body)])."""
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
            docs.append((line, "\n".join(body)))
    return "\n".join(outer), docs


def segments(text, powershell):
    """The simple commands in text, each a list of words; None when the quoting cannot be parsed."""
    import shlex
    out = []
    for line in text.split("\n"):
        try:
            lex = shlex.shlex(line, posix=not powershell, punctuation_chars=True)
            lex.whitespace_split, lex.commenters = True, ""
            words = list(lex)
        except ValueError:
            return None
        current = []
        for w in words:
            if w in SEPARATORS:
                out.append(current)
                current = []
            else:
                current.append(w.strip("'\"") if powershell else w)
        out.append(current)
    return [s for s in out if s]


def command_name(word):
    name = re.split(r"[\\/]", word)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def writes_memory(words):
    """Whether one simple command writes into a memory directory."""
    rest = []
    i = 0
    while i < len(words):
        if re.fullmatch(r"\d*(?:>>?|>\||&>>?)", words[i]) or words[i] in (">", ">>", "&>"):
            target = words[i + 1] if i + 1 < len(words) else ""
            if MEMORY_PATH.search(target):
                return True
            i += 2
            continue
        rest.append(words[i])
        i += 1
    while rest and (ASSIGNMENT.match(rest[0]) or command_name(rest[0]) in WRAPPERS):
        rest = rest[1:]
    if not rest:
        return False
    name = command_name(rest[0])
    if RUNNERS.match(name):
        return any(MEMORY_PATH.search(w) for w in rest[1:])
    named = [w for w in rest[1:] if MEMORY_PATH.search(w) and not re.search(r"\s", w)]
    if not named:
        return False
    if name == "sed":
        return any(re.match(r"^-[a-zA-Z]*i", w) or w.startswith("--in-place") for w in rest[1:])
    if name == "find":
        return any(w in ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0",
                         "-fprintf", "-fls") for w in rest[1:])
    if name in COPIES:
        args = [w for w in rest[1:] if not w.startswith("-")]
        return bool(args) and bool(MEMORY_PATH.search(args[-1]))
    return name not in READS


def shell_verdict(cmd, powershell):
    """The deny reason for a shell command that writes into a memory directory, else None."""
    if not MEMORY_PATH.search(cmd or ""):
        return None
    outer, docs = split_heredocs(cmd)
    for opener, body in docs:
        if MEMORY_PATH.search(body):
            first = segments(opener, powershell) or [[""]]
            if RUNNERS.match(command_name(first[-1][0] if first[-1] else "")):
                return SHELL_DENY
    parsed = segments(outer, powershell)
    if parsed is None:
        return SHELL_DENY
    return SHELL_DENY if any(writes_memory(words) for words in parsed) else None


def deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def exclude_linked(data):
    """Add the exclude line for a linked project memory in a git repository that lacks it."""
    try:
        found = locate(data)
        if found is None:
            return
        root, is_git, problem = found
        if not is_git or problem:
            return
        link = os.path.join(config_dir(), "projects", project_name(root), "memory")
        if is_link(link) and os.path.isdir(os.path.join(root, ".claude", "memory")):
            ensure_excluded(root)
    except OSError:
        pass


def main():
    """The hook's JSON output, or None."""
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    event = data.get("hook_event_name") or "SessionStart"
    tool = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or {}
    if event == "PreToolUse" and tool in ("Bash", "PowerShell"):
        reason = shell_verdict(tool_input.get("command") or "", tool == "PowerShell")
        if reason:
            return deny(reason)
        exclude_linked(data)
        return None

    found = locate(data)
    if found is None:
        return None
    root, is_git, problem = found
    link = os.path.join(config_dir(), "projects", project_name(root), "memory")
    target = os.path.join(root, ".claude", "memory")

    if event == "PreToolUse":
        path = tool_input.get("file_path") or ""
        if not path or not norm(path).startswith(norm(link) + os.sep):
            return None
        if problem:
            return deny(problem[1])
        if is_link(link):
            return None
        create = True
    else:
        if problem:
            return {"systemMessage": problem[0]}
        create = False

    msg = settle(link, target, create)
    if is_git and is_link(link) and os.path.isdir(target):
        ensure_excluded(root)
    return {"systemMessage": msg} if msg else None


if __name__ == "__main__":
    try:
        out = main()
    except Exception as e:
        out = {"systemMessage": f"project-memory: {e}"}
    if out:
        print(json.dumps(out))
    sys.exit(0)
