# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.7] - 2026-09-07

### Added

- `CLAUDE.starterkit.md` §0 — "How to apply these rules — strictly and silently": the ruleset largely exists to redirect the default harness behavior, so follow it silently — never narrate that you are obeying a rule, announce compliance, cite one by name/number as you follow it, or flag that a redirect happened; where a rule specifies its own output shape (e.g. "acknowledge + state what changes + STOP"), that shape is the entire obligation. Applies to spawned agents' messages as well as your own. The sole never-silent exception is commit status: on finishing a unit of work, always state clearly whether it was committed, since some projects auto-commit and some don't and the user must never have to guess.

## [0.3.6] - 2026-09-06

### Added

- `CLAUDE.starterkit.md` §5 — "No emoji or pictographic symbols in terminal-rendered output": chat replies render in a terminal whose font stack usually has no colour-emoji fallback, so an unsupported glyph shows as a tofu box — default to ASCII for structural markers, and never rely on Nerd Font Private-Use-Area icons in text (they render only under a Nerd Font). Absorbed from a machine-local rule so it now applies across every machine via the shared import.
- `CLAUDE.starterkit.md` §10 — "When working with third-party libraries, always RTFM first": read a library/tool's actual docs or source before asserting how it behaves or reverse-engineering it from symbol names or `strings`; a "no API for X / stuck by design" claim made without opening the docs is the same unverified assertion §2's read-enough obligation bans, aimed at a dependency instead of a question.

## [0.3.5] - 2026-09-05

### Added

- `CLAUDE.starterkit.md` §5 — "Text meant to be pasted to a person is sanitized of LLM tells": strip en/em-dashes, curly quotes/apostrophes, the ellipsis character, and stray non-ASCII punctuation from any paste-to-a-human deliverable so it reads like a person typed it. Absorbed from a machine-local rule, so it now applies across every machine via the shared import.

## [0.3.4] - 2026-09-04

### Changed

- **`agent-guard.py` allows named agents.** The hook no longer blocks an `Agent` spawn that carries a `name:` — a descriptive `name:` slug (to tell parallel agents apart) is fine and encouraged. The only spawn rule it enforces is an explicit `model`. The banned *teammate* pattern (the team system where agents are left open as idle addressable mailboxes) stays a prose rule; the Agent tool has no live param to detect it. `CLAUDE.starterkit.md` §4 reworded to match.

## [0.3.3] - 2026-09-04

### Changed

- **Composable install.** The ruleset now installs as a separate `~/.claude/CLAUDE.starterkit.md` and is pulled into context by an idempotent `@./CLAUDE.starterkit.md` import that the installer ensure-appends to your `~/.claude/CLAUDE.md`. The installer **no longer overwrites (or backs up and replaces) your `CLAUDE.md`** — it only guarantees the one import line, so re-running never duplicates it and your own rules are layered with, not clobbered by, the starterkit's.
- Documented the `settings.json` `env` pins and config defaults the installer seeds (previously undocumented) in `README.md` and both `INSTRUCTIONS` guides, and rewrote the install steps for the import-based model.

### Fixed

- Removed lingering `deny-artifact.py` references that 0.3.2 missed: the `README.md` hook roster (count 9 → 8) and the manual-install settings examples in `INSTRUCTIONS.md` / `INSTRUCTIONS-windows.md`. The hook itself was dropped in 0.3.2; these docs still told manual installers to wire it.

## [0.3.2] - 2026-09-04

### Added

- `make_bundle.py` — release bundler that single-sources the version from `CHANGELOG.md` (the first released `## [x.y.z]`) and emits a flat `dist/claude-starterkit-<version>.zip`, so the archive name can never drift from the changelog.
- Installer seeds `env` opt-outs/pins into `settings.json` (per-key, non-clobbering): `DO_NOT_TRACK=1` and `ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-4-8` (pins the `opus` alias to Opus 4.8).
- Installer seeds opinionated config defaults (`setdefault`, non-clobbering): `enableArtifact: false`, `includeCoAuthoredBy: false`, `feedbackDrafts: off`, `promptSuggestionEnabled: false`, `remoteControlAtStartup: false`, `askUserQuestionTimeout: never`, `worktree.baseRef: fresh`, `effortLevel: high`.

### Removed

- The `deny-artifact.py` PreToolUse hook and its installer entry — artifact publishing is now prevented by the native `enableArtifact: false` setting alone.

### Changed

- `CLAUDE.md` §6 — the artifact-enforcement note now points at the native `enableArtifact: false` setting instead of the removed hook.

## [0.3.1] - 2026-09-04

### Added

- `CLAUDE.md` §2 — "'Read enough to answer accurately' is an OBLIGATION, not a permission you can decline": asserting how code/a system behaves from a name/shape/comment instead of opening the definition is the same failure as citing a stale memory.
- `CLAUDE.md` §2 — "Tripwire — asking permission for a step you already have standing authorization to take": a read-only step under a standing grant needs no permission ask; finish it and report the pinned cause.
- `CLAUDE.md` §3 — "All gates green" now carries "a backgrounded/wrapped run's completion EXIT CODE is not that confirmation — READ THE LOG": only the inner suite's result line is ground truth.
- `CLAUDE.md` §9 — "A session launched inside a worktree can't run git against the main checkout — `ExitWorktree(keep)` is the way out": plus "Expect main to have moved while you worked" (cherry-pick/rebase when `--ff-only` is refused).
- `CLAUDE.md` §10 — the `worklog` cross-session task/decision log bullet (`MatLomax/worklog`, SQLite-backed MCP server; `worklog init` per project; omit `slug` and let it derive from the title).

### Changed

- `CLAUDE.md` §7 — the `.git/COMMIT_STYLE.md` bullet expanded to spell out all three cases (present; absent with commits → derive-and-write; absent with no commits → the one time to ask) and that the whole dance is done silently.
- Re-synced the packaged `CLAUDE.md` to the **union** of the maintained user-level ruleset across both machines, reconciling divergence between them (machine-specific homelab import excluded).

## [0.3.0] - 2026-08-20

### Added

- CHANGELOG.md, following the Keep a Changelog format.
- Ruleset preamble to `CLAUDE.md`.
- `CLAUDE.md` §2 — "Confirm your understanding is explain-only; investigate means finish it": bans the half-investigation.
- `CLAUDE.md` §2 — "Drive means carry to COMPLETION": defines a "drive" as orchestrate-to-done owning the whole live subtree.
- `CLAUDE.md` §3 tie-break — a Scope sub-bullet distinguishing owed bookkeeping (work that would be lost) from churn about in-flight work.
- `CLAUDE.md` §5 — "Persistent records state current truth — correcting one is a sweep, not a patch": five linked obligations on memories, docs, and instructions.
- `CLAUDE.md` §10 — "Long shell commands go to the BACKGROUND from the START": the 120s foreground-cap rule.

### Changed

- Synced the packaged `CLAUDE.md` ruleset up to the maintained user-level version (machine-specific homelab import excluded).

## [0.2.0] - 2026-08-07

### Added

- User-level `CLAUDE.md` ruleset (working standards + interaction rules), installed to `~/.claude/CLAUDE.md`.
- Nine Claude Code hooks wired into `settings.json`:
  - `correction-primer.py` (UserPromptSubmit) — nudges when a message reads as a correction/question rather than a start-imperative.
  - `commit-style-primer.py` (UserPromptSubmit) — injects a repo's `.git/COMMIT_STYLE.md` when you ask to commit.
  - `icon-reminder.py` (UserPromptSubmit) — reminds to copy real icon-library glyphs, not hand-draw them.
  - `deny-askuserquestion.py` (PreToolUse) — blocks the `AskUserQuestion` tool.
  - `agent-guard.py` (PreToolUse) — blocks an `Agent` spawn with no explicit `model` or a `name:`.
  - `deny-artifact.py` (PreToolUse) — blocks publishing to the `Artifact` tool.
  - `git-guard.py` (PreToolUse) — blocks broad staging and whole-tree mutations.
  - `nul-guard.py` (PreToolUse) — blocks a `Write`/`Edit` whose content carries a NUL/stray control byte.
  - `tie-break-guard.py` (Stop) — blocks turn-end if the reply defers owed bookkeeping.
- `attribution` setting — sets `{commit:"", pr:"", sessionUrl:false}` to strip AI attribution from commits/PRs, only when not already configured.
- Status line for Unix (`statusline-command.sh`) and Windows (`statusline-command.ps1`), rendering `Model · effort · branch[*] · project · context · <5h bar> · <7d bar>` with rate-limit bars and burn-rate labels.
- Installers for Unix (`install.sh`) and Windows (`install.ps1`) — idempotent, back up existing `CLAUDE.md`/`settings.json`, merge into `settings.json` without clobbering, and honour `$CLAUDE_CONFIG_DIR`.
- Documentation: `README.md`, `INSTRUCTIONS.md`, and `INSTRUCTIONS-windows.md`.
