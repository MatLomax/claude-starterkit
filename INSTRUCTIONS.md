# Install instructions

Two ways to install — the automated script, or the manual steps. Either is fine.

---

## Option A — run the installer (recommended)

```bash
./install.sh
```

Then **restart Claude Code** (or start a fresh session) so the hooks load. The script installs the
ruleset as `~/.claude/CLAUDE.starterkit.md` and ensure-appends a single `@./CLAUDE.starterkit.md`
import to your `~/.claude/CLAUDE.md` (never overwriting it), backs up `~/.claude/settings.json`, and
merges into `settings.json` without touching your other settings. Re-running is safe.

It prompts whether to install the optional **worklog** task-log add-on, defaulting to yes (press
Enter to accept). Pass `--no-worklog` (or `STARTERKIT_WORKLOG=0`) to skip it, or `--with-worklog` to
install without prompting; non-interactive runs install it by default.

---

## Option B — do it manually

Let `CFG` be your Claude config dir: `~/.claude` (or `$CLAUDE_CONFIG_DIR` if you set one).

**1. Install the ruleset and import it.** Copy the ruleset as a separate file, then ensure your
`CLAUDE.md` imports it — this never overwrites your own `CLAUDE.md`:

```bash
mkdir -p "$CFG/hooks"
cp CLAUDE.starterkit.md "$CFG/CLAUDE.starterkit.md"
grep -qF '@./CLAUDE.starterkit.md' "$CFG/CLAUDE.md" 2>/dev/null \
  || printf '\n%s\n' '@./CLAUDE.starterkit.md' >> "$CFG/CLAUDE.md"
```

*Optional:* if you use [`worklog`](https://github.com/MatLomax/worklog), also install the add-on that
points the ruleset's generic "tracked node" wording at it — otherwise skip this:

```bash
cp CLAUDE.starterkit-worklog.md "$CFG/CLAUDE.starterkit-worklog.md"
grep -qF '@./CLAUDE.starterkit-worklog.md' "$CFG/CLAUDE.md" 2>/dev/null \
  || printf '\n%s\n' '@./CLAUDE.starterkit-worklog.md' >> "$CFG/CLAUDE.md"
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
  "env": { "DO_NOT_TRACK": "1", "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-8" },
  "enableArtifact": false,
  "includeCoAuthoredBy": false,
  "feedbackDrafts": "off",
  "promptSuggestionEnabled": false,
  "remoteControlAtStartup": false,
  "askUserQuestionTimeout": "never",
  "worktree": { "baseRef": "fresh" },
  "effortLevel": "high",
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/icon-reminder.py" } ] },
      { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/correction-primer.py" } ] },
      { "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/commit-style-primer.py" } ] }
    ],
    "PreToolUse": [
      { "matcher": "AskUserQuestion", "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/deny-askuserquestion.py" } ] },
      { "matcher": "Agent",           "hooks": [ { "type": "command", "command": "python3 $HOME/.claude/hooks/agent-guard.py" } ] },
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
- The `env` pins + config defaults reinforce the ruleset (telemetry off; `opus` → Opus 4.8; the
  Artifact tool off; no AI co-author line; etc.). The installer sets each only if you haven't chosen
  your own — when pasting manually, drop any you don't want.

**4. Restart Claude Code.** The hooks load at session start.

---

## Uninstall

Delete `$CFG/CLAUDE.starterkit.md` and remove the `@./CLAUDE.starterkit.md` line from
`$CFG/CLAUDE.md`, restore the `settings.json.bak` you backed up, and delete the hook scripts from
`$CFG/hooks/`. If you enabled the worklog add-on, also delete `$CFG/CLAUDE.starterkit-worklog.md` and
its `@./CLAUDE.starterkit-worklog.md` line.

## What each piece does

See `README.md` for the one-line description of every hook and the ruleset.
