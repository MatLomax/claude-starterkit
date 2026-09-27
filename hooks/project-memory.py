#!/usr/bin/env python3
"""SessionStart + PreToolUse (Write|Edit) hook: keep a project's auto memory inside the project.

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
In a git repository the target is also added to the repository's .git/info/exclude.

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
    """A .git entry that marks a repository root: a directory or a file, not a symlink."""
    return os.path.lexists(p) and not os.path.islink(p) and (os.path.isdir(p) or os.path.isfile(p))


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


def locate(data):
    """(project root, whether it is a git repository), or None when the hook should stand aside."""
    start = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    start = os.path.abspath(start)
    if redirected():
        return None
    root = git_root(start)
    is_git = root is not None
    root = canonical_root(root) if is_git else start
    if os.path.dirname(root) == root or memory_dir_setting(root):
        return None
    # The home directory's .claude is the config dir, where Claude Code keeps its own memory stores
    # (memory/personal/); a project there is not linked.
    config = norm(config_dir())
    if norm(os.path.join(root, ".claude")) == config or norm(root).startswith(config + os.sep):
        return None
    return root, is_git


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


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    event = data.get("hook_event_name") or "SessionStart"
    found = locate(data)
    if found is None:
        return None
    root, is_git = found
    link = os.path.join(config_dir(), "projects", project_name(root), "memory")
    target = os.path.join(root, ".claude", "memory")

    if event == "PreToolUse":
        path = (data.get("tool_input") or {}).get("file_path") or ""
        if not path or not norm(path).startswith(norm(link) + os.sep) or is_link(link):
            return None
        create = True
    else:
        create = False

    msg = settle(link, target, create)
    if is_git and is_link(link) and os.path.isdir(target):
        ensure_excluded(root)
    return msg


if __name__ == "__main__":
    try:
        msg = main()
    except Exception as e:
        msg = f"project-memory: {e}"
    if msg:
        print(json.dumps({"systemMessage": msg}))
    sys.exit(0)
