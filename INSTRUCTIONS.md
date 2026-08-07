# Install instructions

Two ways to install — the automated script, or the manual steps. Either is fine.

---

## Option A — run the installer (recommended)

```bash
./install.sh
```

Then **restart Claude Code** (or start a fresh session) so the hooks load. The script backs up any
existing `~/.claude/CLAUDE.md` and `~/.claude/settings.json`, and merges into `settings.json` without
touching your other settings. Re-running is safe.

---

## Option B — do it manually

Let `CFG` be your Claude config dir: `~/.claude` (or `$CLAUDE_CONFIG_DIR` if you set one).

**1. Install the ruleset.** Back up any existing file, then copy:

```bash
mkdir -p "$CFG/hooks"
[ -f "$CFG/CLAUDE.md" ] && cp "$CFG/CLAUDE.md" "$CFG/CLAUDE.md.bak"
cp CLAUDE.md "$CFG/CLAUDE.md"
```

**2. Install the hooks and the statusline.** (The statusline needs `jq` + `awk` at render time —
both standard on Linux/macOS.)

```bash
cp hooks/*.py "$CFG/hooks/"
chmod +x "$CFG/hooks/"*.py
cp statusline-command.sh "$CFG/statusline-command.sh"
chmod +x "$CFG/statusline-command.sh"
```

**3. Wire the hooks into `settings.json`.** Open `$CFG/settings.json` and add the block below. If you
**already have** a `"hooks"` key, merge these entries into its arrays (append — don't replace what's
there). Replace `$HOME` with your real home path if your Claude Code version doesn't expand it in hook
commands.

```json
{
  "attribution": { "commit": "", "pr": "", "sessionUrl": false },
  "statusLine": { "type": "command", "command": "bash $HOME/.claude/statusline-command.sh" },
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/icon-reminder.py" } ] },
      { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/correction-primer.py" } ] },
      { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/commit-style-primer.py" } ] }
    ],
    "PreToolUse": [
      { "matcher": "AskUserQuestion", "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/deny-askuserquestion.py" } ] },
      { "matcher": "Agent",           "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/agent-guard.py" } ] },
      { "matcher": "Artifact",        "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/deny-artifact.py" } ] },
      { "matcher": "Bash",            "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/git-guard.py" } ] },
      { "matcher": "Write|Edit",      "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/nul-guard.py" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/tie-break-guard.py" } ] }
    ]
  }
}
```

- `attribution` (empty `commit`/`pr`, `sessionUrl:false`) suppresses AI attribution on commits/PRs.
  Skip it if you already have your own `attribution` setting.
- `statusLine` renders the model / effort / branch / project / context / rate-limit-bar status line.
  Skip it if you already have your own `statusLine` setting.

**4. Restart Claude Code.** The hooks load at session start.

---

## Uninstall

Restore the `CLAUDE.md.bak` / `settings.json.bak` you backed up, and delete the hook scripts from
`$CFG/hooks/`.

## What each piece does

See `README.md` for the one-line description of every hook and the ruleset.
