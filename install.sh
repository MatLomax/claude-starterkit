#!/usr/bin/env bash
# Installs a shared Claude Code user-level ruleset + guardrail hooks.
#
#   - installs ~/.claude/CLAUDE.starterkit.md and ensure-appends an idempotent
#     `@./CLAUDE.starterkit.md` import to ~/.claude/CLAUDE.md (never overwrites it)
#   - installs ~/.claude/hooks/*.py        (the guardrail + primer hooks)
#   - merges hooks + AI-attribution suppression + env (DO_NOT_TRACK, opus-alias
#     pin) + opinionated config defaults into ~/.claude/settings.json,
#     idempotently and WITHOUT clobbering your existing settings.
#
# Safe to re-run. Restart Claude Code (or start a fresh session) afterwards for the hooks to load.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

mkdir -p "$CLAUDE_DIR/hooks"

# 1. Ruleset — install as CLAUDE.starterkit.md and import it from your CLAUDE.md.
#    Your CLAUDE.md is never overwritten; we only ensure ONE @import line is present.
cp "$HERE/CLAUDE.starterkit.md" "$CLAUDE_DIR/CLAUDE.starterkit.md"
echo "installed CLAUDE.starterkit.md"
IMPORT_LINE="@./CLAUDE.starterkit.md"
CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"
if [ -f "$CLAUDE_MD" ] && grep -qF "$IMPORT_LINE" "$CLAUDE_MD"; then
  echo "CLAUDE.md already imports CLAUDE.starterkit.md"
else
  { [ -s "$CLAUDE_MD" ] && printf '\n'; printf '%s\n' "$IMPORT_LINE"; } >> "$CLAUDE_MD"
  echo "appended '$IMPORT_LINE' to CLAUDE.md"
fi

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

# env — opt out of telemetry and pin the `opus` alias to Opus 4.8. Per-key, so
# any value you've already chosen is left untouched.
env = cfg.setdefault("env", {})
env.setdefault("DO_NOT_TRACK", "1")
env.setdefault("ANTHROPIC_DEFAULT_OPUS_MODEL", "claude-opus-4-8")

# Opinionated config defaults that reinforce the guardrails above (no artifacts,
# no AI co-author line, deterministic worktrees, less UI noise, high effort).
# Each only if you haven't chosen your own value — never clobbers.
DEFAULTS = {
    "includeCoAuthoredBy": False,
    "enableArtifact": False,
    "askUserQuestionTimeout": "never",
    "worktree": {"baseRef": "fresh"},
    "feedbackDrafts": "off",
    "promptSuggestionEnabled": False,
    "remoteControlAtStartup": False,
    "effortLevel": "high",
}
for k, v in DEFAULTS.items():
    cfg.setdefault(k, v)

with open(settings, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
print("merged hooks + attribution + statusLine + env + config defaults into settings.json")
PY

echo
echo "Done. Restart Claude Code (or start a fresh session) for the hooks to take effect."
