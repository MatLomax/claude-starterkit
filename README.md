# Claude Code ruleset + guardrail hooks

A user-level `CLAUDE.md` (working standards + interaction rules) plus a set of Claude Code hooks that
mechanically enforce the parts that can be enforced. Everything is machine- and project-agnostic.

## Install

```bash
./install.sh
```

On **Windows**, run the PowerShell installer instead and see `INSTRUCTIONS-windows.md`:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Then **restart Claude Code** (or start a fresh session) so the hooks load. Re-running is safe
(idempotent). It **backs up** any existing `~/.claude/CLAUDE.md` and `~/.claude/settings.json`
(timestamped `.bak-…`) and **merges** into `settings.json` without clobbering your other config.
Honours `$CLAUDE_CONFIG_DIR` if set, else `~/.claude`.

## What it installs

- **`CLAUDE.md`** → `~/.claude/CLAUDE.md` — the user-level ruleset.
- **9 hooks** → `~/.claude/hooks/`, wired into `settings.json`:
  - `correction-primer.py` (UserPromptSubmit) — nudges you when a message reads as a
    correction/question, not a start-imperative.
  - `commit-style-primer.py` (UserPromptSubmit) — injects a repo's `.git/COMMIT_STYLE.md` when you
    ask to commit.
  - `icon-reminder.py` (UserPromptSubmit) — reminds to copy real icon-library glyphs, not hand-draw.
  - `deny-askuserquestion.py` (PreToolUse) — blocks the `AskUserQuestion` tool (ask in-message).
  - `agent-guard.py` (PreToolUse) — blocks an `Agent` spawn with no explicit `model` or a `name:`.
  - `deny-artifact.py` (PreToolUse) — blocks publishing to the `Artifact` tool.
  - `git-guard.py` (PreToolUse) — blocks broad staging (`git add -A/./-u`, `commit -a`) and
    whole-tree mutations (`reset --hard`, `checkout .`, `restore .`, `clean -f`, create-form `stash`).
  - `nul-guard.py` (PreToolUse) — blocks a `Write`/`Edit` whose content carries a NUL/stray control byte.
  - `tie-break-guard.py` (Stop) — blocks turn-end if the reply defers owed bookkeeping
    ("want me to log it?", "still need to verify").
- **`attribution` setting** — sets `{commit:"", pr:"", sessionUrl:false}` (no AI attribution on
  commits/PRs), only if you haven't already configured it.
- **statusline** → `~/.claude/statusline-command.sh` (Unix) or `statusline-command.ps1` (Windows),
  wired into `settings.json` as `statusLine` (only if you haven't set one). Renders
  `Model · effort · branch[*] · project · context · <5h bar> · <7d bar>` — the rate-limit bars go
  green → yellow → red as you approach the cap, and the elapsed-time labels turn amber when your burn
  rate is on pace to hit the cap before reset (red at ≥98% used). The two scripts are ports of each
  other and render identically. **Deps:** Unix needs `jq` + `awk` (standard); the Windows `.ps1` is
  native PowerShell and needs nothing extra.

## Notes

- The hooks are written for `bypassPermissions`/`dontAsk` modes: they use `deny` (a guardrail that
  holds under those modes) and context injection, never a permission prompt.
- Heuristics (git flag matching, correction/question detection) are pragmatic — tune the scripts in
  `~/.claude/hooks/` to taste.
- To uninstall: restore the `.bak-…` files and remove the hook entries from `settings.json`.
