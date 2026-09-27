#!/usr/bin/env python3
"""SessionStart hook: keep a git repository's auto memory inside the repository.

Claude Code keeps auto memory in <config dir>/projects/<project>/memory/, where <project> is derived
from the path the repository was opened at. The same repository opened at two paths (an sshfs mount
and the machine it lives on, say) gets two unrelated memories, and `autoMemoryDirectory` accepts only
an absolute path, so a setting cannot say "inside this repo".

This hook links that default directory to <repo>/.claude/memory/ (a symlink, or a directory junction
on Windows), creating the target and adding it to the repository's .git/info/exclude. Claude Code
resolves the memory directory after SessionStart hooks run, so the link is in place for the session
that creates it. Every path the repository is opened from gets its own link to the one directory.

<project> is resolved the way Claude Code resolves it: the nearest directory above the working
directory holding a .git entry; for a linked worktree, the main checkout it belongs to; every
character other than an ASCII letter or digit replaced by "-", and a name longer than 200 characters
cut to 200 with a hash of the full path appended.

The hook changes nothing outside a git repository, when auto memory is pointed elsewhere
(autoMemoryDirectory, CLAUDE_CODE_PROJECT_DIR_NAME, CLAUDE_COWORK_MEMORY_PATH_OVERRIDE), or when the
default directory already holds memories or points somewhere else: it reports those two cases to the
user and leaves them for the user to move. It prints nothing on success, because SessionStart stdout
becomes session context, and only a JSON systemMessage when there is something to tell the user.
"""
import json
import os
import re
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
    if os.environ.get("CLAUDE_COWORK_MEMORY_PATH_OVERRIDE"):
        return "CLAUDE_COWORK_MEMORY_PATH_OVERRIDE"
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


def link_target(link):
    """Where link points, or None when it is not a symlink or junction."""
    try:
        return os.readlink(link)
    except (OSError, ValueError):
        return None


def same_dir(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def make_link(target, link):
    if os.name == "nt":
        # A junction needs neither administrator rights nor Developer Mode, unlike a symlink.
        import _winapi
        _winapi.CreateJunction(target, link)
    else:
        os.symlink(target, link)


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    cwd = data.get("cwd") or os.getcwd()
    root = git_root(cwd)
    if root is None or redirected():
        return None
    root = canonical_root(root)
    if memory_dir_setting(root):
        return None

    base = os.environ.get("CLAUDE_CODE_REMOTE_MEMORY_DIR") or config_dir()
    link = os.path.join(base, "projects", project_name(root), "memory")
    target = os.path.join(root, ".claude", "memory")

    os.makedirs(target, exist_ok=True)
    ensure_excluded(root)

    pointed = link_target(link)
    if pointed is not None:
        if same_dir(link, target):
            return None
        return (f"project-memory: {link} links to {pointed}, not to {target}. "
                "Auto memory for this repo stays there until that link is removed.")
    if os.path.isdir(link):
        if os.listdir(link):
            return (f"project-memory: {link} already holds memories, so it was not linked to {target}. "
                    "Move its files into the repo's .claude/memory/ and delete it; the next session links it.")
        os.rmdir(link)
    elif os.path.lexists(link):
        return f"project-memory: {link} is a file, so it was not linked to {target}."
    os.makedirs(os.path.dirname(link), exist_ok=True)
    make_link(target, link)
    return f"project-memory: auto memory for this repo now lives in {target}"


if __name__ == "__main__":
    try:
        msg = main()
    except Exception as e:
        msg = f"project-memory: {e}"
    if msg:
        print(json.dumps({"systemMessage": msg}))
    sys.exit(0)
