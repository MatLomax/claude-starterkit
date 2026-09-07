# Claude Code ruleset + guardrail hooks

A user-level `CLAUDE.md` (working standards + interaction rules) plus a set of Claude Code hooks that
mechanically enforce the parts that can be enforced. Everything is machine- and project-agnostic.

This is one person's opinionated ruleset, shared in case it's useful — fork it and cut what doesn't
fit your workflow. The installer never overwrites your own `CLAUDE.md` or clobbers your
`settings.json`; it layers on top and every opinionated default is set only if you haven't chosen
your own (see [What it installs](#what-it-installs)).

## Install

```bash
./install.sh
```

On **Windows**, run the PowerShell installer instead and see `INSTRUCTIONS-windows.md`:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Then **restart Claude Code** (or start a fresh session) so the hooks load. Re-running is safe
(idempotent). It installs the ruleset as a separate `~/.claude/CLAUDE.starterkit.md` and
ensure-appends a single `@./CLAUDE.starterkit.md` import to your `~/.claude/CLAUDE.md` — **your own
`CLAUDE.md` is never overwritten**. It **backs up** `~/.claude/settings.json` (timestamped `.bak-…`)
and **merges** into it without clobbering your other config. Honours `$CLAUDE_CONFIG_DIR` if set,
else `~/.claude`.

## What it installs

- **`CLAUDE.starterkit.md`** → `~/.claude/CLAUDE.starterkit.md` — the user-level ruleset, pulled into
  context by an idempotent `@./CLAUDE.starterkit.md` line appended to your `~/.claude/CLAUDE.md`
  (your own `CLAUDE.md` is left intact — the starterkit layers on top of it).
- **`CLAUDE.starterkit-worklog.md`** — an add-on that points the ruleset's generic "tracked node" /
  "task graph" wording at [`worklog`](https://github.com/MatLomax/worklog), a cross-session task log.
  The installer offers it via a prompt that **defaults to yes** (press Enter to install). Opt out with
  `--no-worklog` / `-NoWorklog`, or `STARTERKIT_WORKLOG=0`; non-interactive runs install it by default.
  Skip it and the base ruleset is unaffected.
- **8 hooks** → `~/.claude/hooks/`, wired into `settings.json`:
  - `correction-primer.py` (UserPromptSubmit) — nudges you when a message reads as a
    correction/question, not a start-imperative.
  - `commit-style-primer.py` (UserPromptSubmit) — injects a repo's `.git/COMMIT_STYLE.md` when you
    ask to commit.
  - `icon-reminder.py` (UserPromptSubmit) — reminds to copy real icon-library glyphs, not hand-draw.
  - `deny-askuserquestion.py` (PreToolUse) — blocks the `AskUserQuestion` tool (ask in-message).
  - `agent-guard.py` (PreToolUse) — blocks an `Agent` spawn with no explicit `model`.
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
- **`settings.json` defaults** (merged in, each only if you haven't set your own value): `env` gets
  `DO_NOT_TRACK=1` and `ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-4-8` (pins the `opus` alias to Opus
  4.8); plus `enableArtifact:false` (turns the Artifact tool off), `includeCoAuthoredBy:false`,
  `feedbackDrafts:off`, `promptSuggestionEnabled:false`, `remoteControlAtStartup:false`,
  `askUserQuestionTimeout:never`, `worktree.baseRef:fresh`, and `effortLevel:high`.

## Notes

- The hooks are written for `bypassPermissions`/`dontAsk` modes: they use `deny` (a guardrail that
  holds under those modes) and context injection, never a permission prompt.
- Heuristics (git flag matching, correction/question detection) are pragmatic — tune the scripts in
  `~/.claude/hooks/` to taste.
- To uninstall: delete `~/.claude/CLAUDE.starterkit.md` and remove the `@./CLAUDE.starterkit.md`
  line from `~/.claude/CLAUDE.md`, restore the `settings.json.bak-…`, and delete the hook scripts. If
  you enabled the worklog add-on, also delete `~/.claude/CLAUDE.starterkit-worklog.md` and its
  `@./CLAUDE.starterkit-worklog.md` line (re-running with `--no-worklog` does not remove it).
- **Upgrading from ≤ 0.3.1?** Those versions installed the ruleset *inline* as `~/.claude/CLAUDE.md`.
  This version installs it as `CLAUDE.starterkit.md` + an import, so after upgrading, delete the old
  inline ruleset from your `~/.claude/CLAUDE.md` (keep the `@./CLAUDE.starterkit.md` line) so it isn't
  loaded twice.

## License

MIT — see [`LICENSE`](LICENSE).
