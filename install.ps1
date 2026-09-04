<#
Installs a shared Claude Code user-level ruleset + guardrail hooks (Windows / PowerShell).

  - installs %USERPROFILE%\.claude\CLAUDE.starterkit.md and ensure-appends an idempotent
    `@./CLAUDE.starterkit.md` import to %USERPROFILE%\.claude\CLAUDE.md (never overwrites it)
  - installs %USERPROFILE%\.claude\hooks\*.py    (the guardrail + primer hooks)
  - merges hooks + AI-attribution suppression + env (DO_NOT_TRACK, opus-alias
    pin) + opinionated config defaults into settings.json, idempotently and
    WITHOUT clobbering your existing settings.

Safe to re-run. Restart Claude Code (or start a fresh session) afterwards for the hooks to load.
Honours $env:CLAUDE_CONFIG_DIR if set, else %USERPROFILE%\.claude.

Usage (from this folder):
  powershell -ExecutionPolicy Bypass -File .\install.ps1
#>
$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClaudeDir = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE ".claude" }
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"

# 0. Find a working Python — hook commands need one baked in. Windows rarely has `python3`.
$PyCmd = $null
foreach ($cand in @("py -3", "python", "python3")) {
  $parts = $cand.Split(" ")
  $exe = $parts[0]
  $rest = if ($parts.Length -gt 1) { $parts[1..($parts.Length-1)] } else { @() }
  try {
    & $exe @rest --version *> $null
    if ($LASTEXITCODE -eq 0) { $PyCmd = $cand; break }
  } catch { }
}
if (-not $PyCmd) {
  Write-Error "No Python found on PATH (tried 'py -3', 'python', 'python3'). The hooks are Python scripts and need it. Install Python 3 from python.org or the Microsoft Store, then re-run."
  exit 1
}
Write-Host "using Python command: $PyCmd"

New-Item -ItemType Directory -Force -Path (Join-Path $ClaudeDir "hooks") | Out-Null

# 1. Ruleset — install as CLAUDE.starterkit.md and import it from your CLAUDE.md.
#    Your CLAUDE.md is never overwritten; we only ensure ONE @import line is present.
Copy-Item (Join-Path $Here "CLAUDE.starterkit.md") (Join-Path $ClaudeDir "CLAUDE.starterkit.md") -Force
Write-Host "installed CLAUDE.starterkit.md"
$importLine = "@./CLAUDE.starterkit.md"
$claudeMd = Join-Path $ClaudeDir "CLAUDE.md"
if ((Test-Path $claudeMd) -and (Select-String -Path $claudeMd -SimpleMatch -Pattern $importLine -Quiet)) {
  Write-Host "CLAUDE.md already imports CLAUDE.starterkit.md"
} else {
  if ((Test-Path $claudeMd) -and ((Get-Item $claudeMd).Length -gt 0)) { Add-Content -Path $claudeMd -Value "" }
  Add-Content -Path $claudeMd -Value $importLine
  Write-Host "appended '$importLine' to CLAUDE.md"
}

# 2. hooks
$hookSrc = Join-Path $Here "hooks\*.py"
Copy-Item $hookSrc (Join-Path $ClaudeDir "hooks") -Force
$hookCount = (Get-ChildItem (Join-Path $ClaudeDir "hooks\*.py")).Count
Write-Host "installed $hookCount hook scripts"

# 2b. statusline script (native PowerShell port — no bash/jq needed on Windows).
Copy-Item (Join-Path $Here "statusline-command.ps1") (Join-Path $ClaudeDir "statusline-command.ps1") -Force
Write-Host "installed statusline-command.ps1"
$slScriptPath = (Join-Path $ClaudeDir "statusline-command.ps1").Replace("\", "/")
$psExe = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
$SlCmd = "$psExe -NoProfile -File `"$slScriptPath`""
Write-Host "statusline command: $SlCmd"

# 3. settings.json — idempotent merge (same Python merge as install.sh, so behavior can't drift).
#    Passes the resolved Python command so the baked-in hook commands actually run on Windows.
$mergeScript = @'
import json, os, sys, shutil, time
d, pycmd, sl_cmd = sys.argv[1], sys.argv[2], sys.argv[3]
settings = os.path.join(d, "settings.json")
hooks = os.path.join(d, "hooks").replace("\\", "/")

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
        cmd = f"{pycmd} {hooks}/{script}"
        if cmd in present:
            continue
        entry = {"hooks": [{"type": "command", "command": cmd}]}
        if matcher:
            entry["matcher"] = matcher
        groups.append(entry)

if "attribution" not in cfg:
    cfg["attribution"] = {"commit": "", "pr": "", "sessionUrl": False}

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
'@

$tmp = Join-Path $env:TEMP "claude-starterkit-merge-$Stamp.py"
Set-Content -Path $tmp -Value $mergeScript -Encoding UTF8
try {
  $parts = $PyCmd.Split(" ")
  $exe = $parts[0]
  $rest = if ($parts.Length -gt 1) { $parts[1..($parts.Length-1)] } else { @() }
  & $exe @rest $tmp $ClaudeDir $PyCmd $SlCmd
  if ($LASTEXITCODE -ne 0) { throw "settings.json merge failed" }
} finally {
  Remove-Item $tmp -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Done. Restart Claude Code (or start a fresh session) for the hooks to take effect."
