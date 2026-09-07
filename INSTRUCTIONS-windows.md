# Install instructions (Windows)

Two ways to install — the automated PowerShell script, or the manual steps. Either is fine.

**Prerequisite:** Python 3 must be on your `PATH` (the hooks are Python scripts). Check with
`py -3 --version` or `python --version`. If missing, install from
[python.org](https://www.python.org/downloads/) or the Microsoft Store — during the python.org
installer, tick **"Add Python to PATH"**.

---

## Option A — run the installer (recommended)

From this folder, in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Then **restart Claude Code** (or start a fresh session) so the hooks load. The script:

- detects your Python command (`py -3`, `python`, or `python3`) and bakes the working one into the
  hook commands — Windows rarely has a bare `python3`;
- installs the ruleset as `CLAUDE.starterkit.md` and appends a single `@./CLAUDE.starterkit.md`
  import to your `CLAUDE.md` (never overwriting it); backs up `settings.json` (timestamped `.bak-…`);
- merges into `settings.json` without touching your other settings.

Re-running is safe (idempotent). It honours `$env:CLAUDE_CONFIG_DIR` if set, else
`%USERPROFILE%\.claude`.

It prompts whether to install the optional **worklog** task-log add-on, defaulting to yes (press
Enter to accept). Pass `-NoWorklog` (or set `$env:STARTERKIT_WORKLOG = "0"` first) to skip it, or
`-WithWorklog` to install without prompting; non-interactive runs install it by default.

---

## Option B — do it manually

Let `CFG` be your Claude config dir: `%USERPROFILE%\.claude` (or `$env:CLAUDE_CONFIG_DIR` if you set
one). In PowerShell:

**1. Install the ruleset and import it.** Copy the ruleset as a separate file, then ensure your
`CLAUDE.md` imports it — this never overwrites your own `CLAUDE.md`:

```powershell
$CFG = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE ".claude" }
New-Item -ItemType Directory -Force -Path (Join-Path $CFG "hooks") | Out-Null
Copy-Item .\CLAUDE.starterkit.md (Join-Path $CFG "CLAUDE.starterkit.md")
$claudeMd = Join-Path $CFG "CLAUDE.md"
if (-not ((Test-Path $claudeMd) -and (Select-String -Path $claudeMd -SimpleMatch -Pattern '@./CLAUDE.starterkit.md' -Quiet))) {
  Add-Content -Path $claudeMd -Value "`n@./CLAUDE.starterkit.md"
}
```

*Optional:* if you use [`worklog`](https://github.com/MatLomax/worklog), also install the add-on that
points the ruleset's generic "tracked node" wording at it — otherwise skip this:

```powershell
Copy-Item .\CLAUDE.starterkit-worklog.md (Join-Path $CFG "CLAUDE.starterkit-worklog.md")
if (-not ((Test-Path $claudeMd) -and (Select-String -Path $claudeMd -SimpleMatch -Pattern '@./CLAUDE.starterkit-worklog.md' -Quiet))) {
  Add-Content -Path $claudeMd -Value "`n@./CLAUDE.starterkit-worklog.md"
}
```

**2. Install the hooks and the statusline.** (No `chmod` needed on Windows. The statusline is a
native PowerShell script — no `jq`/`bash` required.)

```powershell
Copy-Item .\hooks\*.py (Join-Path $CFG "hooks") -Force
Copy-Item .\statusline-command.ps1 (Join-Path $CFG "statusline-command.ps1") -Force
```

**3. Wire the hooks into `settings.json`.** Open `%USERPROFILE%\.claude\settings.json` and add the
block below. If you **already have** a `"hooks"` key, merge these entries into its arrays (append —
don't replace what's there).

> **Python command:** the block below uses `py -3` (the Windows Python launcher). If `py` isn't
> available, replace every `py -3` with `python` (whichever `--version` works). Use **forward
> slashes** in the paths, and substitute your real home path for `C:/Users/YOU`.

```json
{
  "attribution": { "commit": "", "pr": "", "sessionUrl": false },
  "statusLine": { "type": "command", "command": "pwsh -NoProfile -File \"C:/Users/YOU/.claude/statusline-command.ps1\"" },
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
      { "hooks": [ { "type": "command", "command": "py -3 C:/Users/YOU/.claude/hooks/icon-reminder.py" } ] },
      { "hooks": [ { "type": "command", "command": "py -3 C:/Users/YOU/.claude/hooks/correction-primer.py" } ] },
      { "hooks": [ { "type": "command", "command": "py -3 C:/Users/YOU/.claude/hooks/commit-style-primer.py" } ] }
    ],
    "PreToolUse": [
      { "matcher": "AskUserQuestion", "hooks": [ { "type": "command", "command": "py -3 C:/Users/YOU/.claude/hooks/deny-askuserquestion.py" } ] },
      { "matcher": "Agent",           "hooks": [ { "type": "command", "command": "py -3 C:/Users/YOU/.claude/hooks/agent-guard.py" } ] },
      { "matcher": "Bash",            "hooks": [ { "type": "command", "command": "py -3 C:/Users/YOU/.claude/hooks/git-guard.py" } ] },
      { "matcher": "Write|Edit",      "hooks": [ { "type": "command", "command": "py -3 C:/Users/YOU/.claude/hooks/nul-guard.py" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "py -3 C:/Users/YOU/.claude/hooks/tie-break-guard.py" } ] }
    ]
  }
}
```

- `attribution` (empty `commit`/`pr`, `sessionUrl:false`) suppresses AI attribution on commits/PRs.
  Skip it if you already have your own `attribution` setting.
- `statusLine` renders the model / effort / branch / project / context / rate-limit-bar status line.
  If `pwsh` (PowerShell 7+) isn't installed, use `powershell` instead of `pwsh` in the command. Skip
  the whole line if you already have your own `statusLine` setting.
- The `env` pins + config defaults reinforce the ruleset (telemetry off; `opus` → Opus 4.8; the
  Artifact tool off; no AI co-author line; etc.). The installer sets each only if you haven't chosen
  your own — when pasting manually, drop any you don't want.

**4. Restart Claude Code.** The hooks load at session start.

---

## Troubleshooting

- **"No Python found on PATH"** — install Python 3 (see prerequisite above) and reopen the terminal
  so `PATH` refreshes, then re-run.
- **Hooks don't fire** — open `settings.json` and confirm the `command` prefix (`py -3` / `python`)
  is one that runs in *your* shell. Run one by hand to check, e.g.
  `py -3 %USERPROFILE%\.claude\hooks\git-guard.py` (it will just wait for stdin — Ctrl+C to exit).
- **Script won't run / execution policy** — use the exact `-ExecutionPolicy Bypass` invocation in
  Option A; it applies only to that one run and changes nothing permanently.

---

## Uninstall

Delete `%USERPROFILE%\.claude\CLAUDE.starterkit.md` and remove the `@./CLAUDE.starterkit.md` line
from `%USERPROFILE%\.claude\CLAUDE.md`, restore the `settings.json.bak-…` you backed up, and delete
the hook scripts from `%USERPROFILE%\.claude\hooks\`. If you enabled the worklog add-on, also delete
`%USERPROFILE%\.claude\CLAUDE.starterkit-worklog.md` and its `@./CLAUDE.starterkit-worklog.md` line.

## What each piece does

See `README.md` for the one-line description of every hook and the ruleset.
