#!/usr/bin/env bash
# Installs a shared Claude Code user-level ruleset + guardrail hooks.
#
#   - writes  ~/.claude/CLAUDE.md          (backs up any existing one)
#   - installs ~/.claude/hooks/*.py        (the guardrail + primer hooks)
#   - merges hooks + AI-attribution suppression into ~/.claude/settings.json,
#     idempotently and WITHOUT clobbering your existing settings.
#
# Safe to re-run. Restart Claude Code (or start a fresh session) afterwards for the hooks to load.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$CLAUDE_DIR/hooks"

# 1. CLAUDE.md — back up any existing file first.
if [ -f "$CLAUDE_DIR/CLAUDE.md" ]; then
  cp "$CLAUDE_DIR/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md.bak-$STAMP"
  echo "backed up existing CLAUDE.md -> CLAUDE.md.bak-$STAMP"
fi
cp "$HERE/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"
echo "installed CLAUDE.md"

# 2. hooks
cp "$HERE"/hooks/*.py "$CLAUDE_DIR/hooks/"
chmod +x "$CLAUDE_DIR"/hooks/*.py
echo "installed $(ls -1 "$HERE"/hooks/*.py | wc -l) hook scripts"

# 2b. statusline script (needs jq + awk at render time; standard on Linux/macOS).
cp "$HERE/statusline-command.sh" "$CLAUDE_DIR/statusline-command.sh"
chmod +x "$CLAUDE_DIR/statusline-command.sh"
echo "installed statusline-command.sh"

# 3. settings.json — idempotent merge (backs up; never clobbers other keys or existing hooks).
SL_CMD="bash $CLAUDE_DIR/statusline-command.sh"
python3 - "$CLAUDE_DIR" "$SL_CMD" <<'PY'
import json, os, sys, shutil, time
d = sys.argv[1]
sl_cmd = sys.argv[2]
settings = os.path.join(d, "settings.json")
hooks = os.path.join(d, "hooks")

cfg = {}
if os.path.exists(settings):
    with open(settings) as f:
        cfg = json.load(f)
    shutil.copy2(settings, settings + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))

WANT = {
    "UserPromptSubmit": [
        (None, "icon-reminder.py"),
        (None, "correction-primer.py"),
        (None, "commit-style-primer.py"),
    ],
    "PreToolUse": [
        ("AskUserQuestion", "deny-askuserquestion.py"),
        ("Agent", "agent-guard.py"),
        ("Artifact", "deny-artifact.py"),
        ("Bash", "git-guard.py"),
        ("Write|Edit", "nul-guard.py"),
    ],
    "Stop": [
        (None, "tie-break-guard.py"),
    ],
}

def have(groups):
    return {x["command"] for g in groups for x in g.get("hooks", []) if x.get("command")}

h = cfg.setdefault("hooks", {})
for event, wants in WANT.items():
    groups = h.setdefault(event, [])
    present = have(groups)
    for matcher, script in wants:
        cmd = f"python3 {hooks}/{script}"
        if cmd in present:
            continue
        entry = {"hooks": [{"type": "command", "command": cmd}]}
        if matcher:
            entry["matcher"] = matcher
        groups.append(entry)

# AI-attribution suppression — only if you haven't set it yourself.
if "attribution" not in cfg:
    cfg["attribution"] = {"commit": "", "pr": "", "sessionUrl": False}

# statusLine — only if you haven't set one yourself.
if "statusLine" not in cfg:
    cfg["statusLine"] = {"type": "command", "command": sl_cmd}

with open(settings, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
print("merged hooks + attribution + statusLine into settings.json")
PY

echo
echo "Done. Restart Claude Code (or start a fresh session) for the hooks to take effect."
