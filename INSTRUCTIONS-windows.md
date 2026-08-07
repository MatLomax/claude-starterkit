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
- backs up any existing `CLAUDE.md` and `settings.json` (timestamped `.bak-…`);
- merges into `settings.json` without touching your other settings.

Re-running is safe (idempotent). It honours `$env:CLAUDE_CONFIG_DIR` if set, else
`%USERPROFILE%\.claude`.

---

## Option B — do it manually

Let `CFG` be your Claude config dir: `%USERPROFILE%\.claude` (or `$env:CLAUDE_CONFIG_DIR` if you set
one). In PowerShell:

**1. Install the ruleset.** Back up any existing file, then copy:

```powershell
$CFG = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE ".claude" }
New-Item -ItemType Directory -Force -Path (Join-Path $CFG "hooks") | Out-Null
if (Test-Path (Join-Path $CFG "CLAUDE.md")) { Copy-Item (Join-Path $CFG "CLAUDE.md") (Join-Path $CFG "CLAUDE.md.bak") }
Copy-Item .\CLAUDE.md (Join-Path $CFG "CLAUDE.md")
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
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "py -3 C:/Users/YOU/.claude/hooks/icon-reminder.py" } ] },
      { "hooks": [ { "type": "command", "command": "py -3 C:/Users/YOU/.claude/hooks/correction-primer.py" } ] },
      { "hooks": [ { "type": "command", "command": "py -3 C:/Users/YOU/.claude/hooks/commit-style-primer.py" } ] }
    ],
    "PreToolUse": [
      { "matcher": "AskUserQuestion", "hooks": [ { "type": "command", "command": "py -3 C:/Users/YOU/.claude/hooks/deny-askuserquestion.py" } ] },
      { "matcher": "Agent",           "hooks": [ { "type": "command", "command": "py -3 C:/Users/YOU/.claude/hooks/agent-guard.py" } ] },
      { "matcher": "Artifact",        "hooks": [ { "type": "command", "command": "py -3 C:/Users/YOU/.claude/hooks/deny-artifact.py" } ] },
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

Restore the `CLAUDE.md.bak-…` / `settings.json.bak-…` you backed up, and delete the hook scripts
from `%USERPROFILE%\.claude\hooks\`.

## What each piece does

See `README.md` for the one-line description of every hook and the ruleset.
