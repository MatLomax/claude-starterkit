# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Recommended plugins.** Along with the worklog question, the installer offers a multiselect of recommended plugins, none ticked by default. Nothing is vendored: each ticked plugin is installed after the core install by its own official installer. The first is [ripwire](https://github.com/redhat-et/ripwire), installed with its documented quick install; once it installs, the installer offers to register ripwire's Claude Code hooks (`share/ripwire/skills/install.sh --hook`), defaulting to yes, or to no with a note when `jq` is missing. ripwire has no official Windows installer, so on Windows it is listed with a link to its releases. Without a terminal nothing is prompted: `--plugins=ripwire` / `STARTERKIT_PLUGINS` names the plugins to install, `--plugin-hooks` / `STARTERKIT_PLUGIN_HOOKS=1` runs their follow-up steps, and `--no-plugins` skips the list. A plugin that fails to install, or has no installer on the platform, is reported at the end and exits non-zero without stopping the rest.
- `.github/workflows/ci.yml` — runs the Go tests on Linux, macOS and Windows, then installs through both one-liners (including `irm | iex` and the scriptblock form on Windows) against locally served release assets, checks the result and a no-change re-run, and installs ripwire non-interactively in a sandboxed home on Linux.
- `CLAUDE.starterkit-compaction.md` "# Compact instructions", imported at the end of `CLAUDE.starterkit.md` and installed alongside it, which keeps each instruction file under Claude Code's 40k-character per-file warning — the section Claude Code reads when it writes a compaction summary. Compaction clears old material out of context rather than starting a new session, so the summary is a complete handoff written by the agent that holds the full context, under six headings: task and scope (with the user's standing instructions and corrections), established facts (found, measured or decided, with exact identifiers and a short source), decisions, state of the work (in-flight jobs and each repo's exact git state), open items and blockers, and the next step with whether it is authorised. Established facts are trusted by the next agent as verified in the session; anything not verified is marked `(unverified)`. §5 "Verify before asserting" names a compaction summary as not a record that needs re-checking.
- `hooks/compact-snapshot.py` (PreCompact) — copies the full session transcript to `~/.claude/compact-transcripts/<timestamp>-<session_id>.jsonl` before every compaction, keeping the newest 10 across sessions, so an exact detail the summary did not keep can still be searched. Never blocks a compaction.
- `hooks/compact-resume.py` (SessionStart, matcher `compact`) — tells the post-compaction agent that the summary's established facts are trusted (no re-checking, no hedging, overriding the verify-a-record rule unless something observed now contradicts one), to carry on from the summary's next step, and where the transcript copy is, as a reference to grep rather than load. Wired by `install.sh` / `install.ps1`, listed in the `INSTRUCTIONS.md` / `INSTRUCTIONS-windows.md` settings templates and the `README.md` hook list.
- `hooks/compact-continue.py` (PostCompact, matcher `manual`, `asyncRewake: true`) — a manual `/compact` otherwise ends at the prompt and the work waits for the user to type again. The hook exits 2 in the background, which wakes Claude to carry on from the summary's next step if it is authorised to start, or to reply with one line naming what it is waiting on. Auto-compaction already continues the interrupted turn, so the hook ignores it (matcher `manual`, and the input's `trigger` is checked again). The installers' hook table now carries optional extra fields per hook, used here for `asyncRewake`. Wired by `install.sh` / `install.ps1`, listed in both settings templates and the `README.md` hook list.

### Changed

- **The installer is a single self-contained binary, installed with a one-liner.** `curl -fsSL https://github.com/MatLomax/claude-starterkit/releases/latest/download/install.sh | sh` (macOS / Linux) or `irm https://github.com/MatLomax/claude-starterkit/releases/latest/download/install.ps1 | iex` (Windows) downloads the installer for the machine's OS and CPU from the latest release, checks its SHA-256 and runs it; the same line reinstalls or upgrades, so no clone of the repo is needed. `install.sh` and `install.ps1` are now only those bootstraps: they pass options through (`sh -s -- --no-worklog`, or the PowerShell scriptblock form `-NoWorklog`), give the installer the terminal when piped so its prompts work, and install a pinned release with `STARTERKIT_VERSION=X.Y.Z`. The installer itself (`cmd/starterkit-install`, Go) carries the ruleset and every part it imports, the worklog add-on, the review rules, both statusline scripts and all hook scripts embedded, and does what the two scripts did: the same files, the same `CLAUDE.md` import lines, and the same `settings.json` merge (hooks, attribution, statusline, env, config defaults, the `matlomax` marketplace with worklog). On a copy of a real `settings.json` its output is byte-identical to the previous `install.sh`; where the old Python merge rewrote a user's non-ASCII text as `\u` escapes and normalised numbers (`1.50` to `1.5`), the new one leaves them as written. The worklog prompt and `--with-worklog` / `--no-worklog` / `STARTERKIT_WORKLOG` are unchanged. Prebuilt for Linux, macOS and Windows on x64 and arm64.
- `.github/workflows/release.yml` runs the Go tests and publishes the per-platform installer binaries, a `.sha256` for each, and `install.sh` / `install.ps1` as the release assets (`scripts/build-release.sh`). A dispatch re-publish of a tag from before this change still builds that tag's zip.
- `CLAUDE.starterkit.md` §4 moves to `CLAUDE.starterkit-agents.md`, and §7, §8 and §9 to `CLAUDE.starterkit-git.md`. The ruleset imports both where the sections stood, keeping their numbers so every `§N` reference still resolves, and the installer copies them beside it. Each file is now under Claude Code's 40k-character per-file warning (the main ruleset is about 36.6k); everything still loads every session. Listed in `README.md` and in the manual install and uninstall steps of `INSTRUCTIONS.md` / `INSTRUCTIONS-windows.md`.

### Removed

- `make_bundle.py` and the release zip: the installer binary carries its own payload.

- `install.sh` / `install.ps1` seed `autoCompactEnabled: true` and `spinnerTipsEnabled: false` (each only if unset), so a session compacts automatically as its context fills (the compact instructions and hooks then carry the work across) and the spinner shows no tips. The `README.md` defaults list and the settings templates in `INSTRUCTIONS.md` / `INSTRUCTIONS-windows.md` list both.

### Fixed

- Hook and statusline commands work when the Claude config directory has a space in its path (`C:/Users/John Smith/.claude`, a macOS home with a space). The script path in each hook command, and in the Unix statusline command, is double-quoted when it holds a space or another character the shell treats specially, with `"`, `\`, `$` and backticks escaped for the shell Claude Code runs hook commands through (`sh -c` on Unix, Git Bash on Windows); an ordinary path is written exactly as before, so existing installs' commands are unchanged. A reinstall rewrites the unquoted command an earlier install wrote for such a path in place, instead of adding a second entry beside it (or drops it when the quoted command is already registered), and upgrades the unquoted Unix statusline command the same way. A `$` or backtick in a Windows path is escaped for Git Bash, which PowerShell (Claude Code's fallback when Git Bash is missing) reads differently.
- `hooks/git-guard.py` broad-staging checks read the argv of each `git add` / `git commit` in the command line instead of regex-matching the whole line. A `-a` belonging to another command (`rsync -a`, `grep -a`, `ls -a`), a `-a` inside a commit message or heredoc, and a `git` mentioned as an argument (`echo git add .`) no longer deny the command. Forms the regexes missed are now denied: git's own options before the subcommand (`git -C <dir> add -A`), combined short flags (`git commit -qam`, `git add -Av`), and a broad path after `--` (`git add -- .`).

## [0.5.4] - 2026-09-27

### Added

- `review-rules.md` — opt-in review-before-done rules, installed to `~/.claude/review-rules.md` by `install.sh` / `install.ps1` and bundled by `make_bundle.py`, but imported nowhere: `CLAUDE.starterkit.md` does not reference it, so it is off by default and costs no tokens until a machine's or project's `CLAUDE.md` imports `@~/.claude/review-rules.md`. One review by an agent that did not do the work, run after the gates are green; real defects fixed and the fixes re-reviewed once, then anything open goes to the user; demands for more proof, evidence trails or attribution rigour are not findings; the outcome is noted briefly on the task. The repo copy is the single source for machines that previously each kept their own. Listed in `README.md`.

## [0.5.3] - 2026-09-27

### Changed

- `hooks/sleep-guard.py` also denies disguised delays: `tail -f /dev/null` (with or without a `timeout` around it), `read -t N`, `ping` of the local host, `usleep` / `gsleep`, cmd's `timeout /t N`, PowerShell `Wait-Event -Timeout`, and Perl's `select(undef, undef, undef, N)` in an inline script. Real reads, tails of real files and pings of real hosts still pass. The deny message names the sanctioned waits (`gh run watch <id> --exit-status` in the background, or `Monitor`) and says not to route around the guard.
- `CLAUDE.starterkit.md` §10 "Wait for a background job by ending the turn": a disguised delay is a sleep and a guard is not a puzzle; external state a tool can block on is waited on with that tool's own blocking wait in the background (`gh run watch`, `kubectl wait`, `docker wait`), leaving `Monitor` for state with no such wait; and a check on external state runs in the background too, since it can hang on the network. `README.md`'s hook list matches.

## [0.5.2] - 2026-09-27

### Added

- `CLAUDE.starterkit.md` §7 — "Build output is always gitignored, never committed": generated output (`dist/`, `build/`, `.svelte-kit/`, `__pycache__/`, `node_modules/`, coverage, bundles, build and test logs) is covered by the repo's `.gitignore`; found untracked or tracked, it gets an ignore pattern (and `git rm --cached`) in the same change instead of a commit, including under "commit everything".

## [0.5.1] - 2026-09-27

### Changed

- `hooks/tie-break-guard.py` checks record-keeping behaviour instead of phrasing. It blocks turn-end, at most once per turn, when the reply asks permission to keep a record ("want me to log it?", "shall I add a task?"), claims in the first person that a record was made ("I've logged it as a task") while no worklog write or file write happened in the turn, or promises one ("I'll add a task for that") with nothing written and no background work pending. It reads the turn's tool calls from the transcript. Fenced code, inline code, `>` blockquotes and double-quoted text are stripped before matching, so quoting or describing a trigger phrase no longer trips it. The block reason names the phrase that matched. The "verify" triggers ("still need to verify", "haven't verified", "want me to check/verify/confirm") are gone: they blocked honest status lines about limits and pushed agents toward open-ended proof-gathering. Prompted by the hook blocking two replies that only quoted its own trigger phrases, and by an unattended review loop that treated demands for more proof as bookkeeping it owed.
- `CLAUDE.starterkit.md` §3 tie-break: bookkeeping is defined as keeping records true (tracker status, recorded findings and decisions, promised notes and memories). Checking a fact before stating it is the §2 read-enough obligation, not bookkeeping, and neither licenses open-ended evidence trails or attribution rigour beyond the task. The enforcement note describes the new hook behaviour. `README.md`'s hook list matches.

## [0.5.0] - 2026-09-26

### Added

- `hooks/sleep-guard.py` (PreToolUse, matcher `Bash|PowerShell`) — denies any shell command that sleeps: `sleep` / `/bin/sleep` in command position (including inside loops, `$(…)`, `-c` strings and after wrappers like `nohup` / `timeout N`), PowerShell `Start-Sleep` / `[Thread]::Sleep(`, and inline `time.sleep(` / `asyncio.sleep(` / `setTimeout(`. Mentions pass: a quoted `grep "sleep 60"`, and heredoc text fed to anything other than a shell or an interpreter (a `git commit -F -` message, `cat > file`); a sleep inside a script file the command runs is not checked. Wired by `install.sh` / `install.ps1` and listed in the `INSTRUCTIONS.md` / `INSTRUCTIONS-windows.md` settings templates and the `README.md` hook list. Prompted by a background subagent that ran `sleep 595` polling loops for five hours on a ~700k-token context, re-writing the whole context into the prompt cache on almost every check; about half that session tree's spend went on polling.
- `hooks/spend-guard.py` (PreToolUse, all tools) — caps spend in API-price-weighted tokens (input x1, cache write x1.25, cache read x0.1, output x5) with two limits, denying every tool call in the capped scope so the model can only end its turn and report. `PROMPT_SPEND_LIMIT` (default `3M`) covers the main conversation and its subagents since the user's last typed message; task notifications and scheduled `/loop` wakeups do not reset it. `WORKFLOW_SPEND_LIMIT` (default `10M`) covers each Workflow run's agents (`subagents/workflows/<run>/`) over the run's life, is checked only on that run's agents' calls (identified by transcript path, or by `agent_type` `workflow-subagent` + `agent_id`), and is kept out of the prompt count. Both take `k`/`M` suffixes; `0`/`off` disables either. Transcripts are read incrementally with per-file offsets in a per-session state file under `~/.cache/claude-spend-guard/`, replaced atomically so parallel agents never double-count. Replayed line by line against the overnight runaway session (104.5M after one reply) it first blocks 21 minutes after the session's opening "go", at 4.0M; across ~2,700 real prompts 40 passed 3M, and past Workflow runs of 15-32 agents spent 4.3-5.4M. Wired by `install.sh` / `install.ps1` and listed in the settings templates and the `README.md` hook list.
- `CLAUDE.starterkit.md` §2 — "Review-and-fix loops stop after 3 rounds and report": an unattended review, fix, review loop stops after 3 rounds and reports what each round found, what is open and what a further round would target; the user decides on a fourth. It binds a drive too, and the "Drive" section says so.
- `CLAUDE.starterkit.md` §4 — "Spend is capped; at the cap, stop and report", documenting both spend-guard limits, what resets the prompt limit, and `--max-budget-usd` for unattended `claude -p` runs.
- `CLAUDE.starterkit.md` §10 — "Wait for a background job by ending the turn — never by polling it": once a job or agent is backgrounded, carry on or end the turn and let the completion notification wake you, in a subagent as much as in the main session; never wait with `sleep`. `Monitor` is reserved for external state with no completion event of its own, with a script that prints only on a real state change, and is never pointed at a job you started. The existing "Long shell commands go to the BACKGROUND" rule no longer offers "poll its output file" as a way to wait.
- `CLAUDE.starterkit.md` §7 — Keep a Changelog rule: in a repo whose CHANGELOG follows Keep a Changelog, every notable change goes under `## [Unreleased]`; a version heading, version bump or release tag is cut only on an explicit release instruction ("commit this" / "ship it" is not one).
- `install.sh` / `install.ps1` seed `cleanupPeriodDays: 36500` (only if unset), so Claude Code keeps session transcripts instead of purging them after its 30-day default. Transcripts are evidence you may need well after a month (reconstructing past work, time and decisions), and the purge is silent. The `README.md` defaults list and the settings templates in `INSTRUCTIONS.md` / `INSTRUCTIONS-windows.md` list it too.

### Removed

- The `opus` alias pin. `install.sh` / `install.ps1` no longer seed `ANTHROPIC_DEFAULT_OPUS_MODEL=claude-opus-4-8`, so `opus` resolves to the latest Opus like `sonnet` and `haiku` do for their tiers. On re-run, the installers remove that key when it holds exactly the value earlier kit versions seeded; any other value is left as the user's own choice. The settings templates in `INSTRUCTIONS.md` / `INSTRUCTIONS-windows.md`, the `README.md` defaults list, the `CLAUDE.starterkit.md` §4 roster (now: always the tier shorthand, never a model id) and the agent-guard deny message drop the 4.8 pin to match; the README and INSTRUCTIONS files note the removal for manually-pasted settings.

## [0.4.3] - 2026-09-16

### Added

- `CLAUDE.starterkit-worklog.md` — the base §5 "memories are purged, not corrected" exception now extends to *unfinished* worklog tasks. A task not yet implemented/done is a live spec of intended behaviour: incorrect or outdated content is deleted outright (the body rewritten to read true), never annotated, appended beside the old, or left as a "was X, now Y" trail. Once a task is implemented/done it becomes a historical record, so a change to it is a historical correction handled like any doc (correct in place, without rewriting what happened). Named with a tripwire: preserving a superseded requirement "for context" in a still-open task.

## [0.4.2] - 2026-09-16

### Added

- `install.sh` / `install.ps1` register the `matlomax` plugin marketplace globally in `~/.claude/settings.json` (`extraKnownMarketplaces`) — but only when the worklog add-on is selected, since worklog is the marketplace's reason to exist for this kit. The marketplace becomes known on every project; no plugin is enabled globally (`enabledPlugins` is left untouched). Plugin enablement stays per-project via `npx github:MatLomax/claude-plugins`, so a repo opts in to `worklog` in its own `.claude/settings.json`. `--no-worklog` leaves global plugin settings entirely alone.

## [0.4.1] - 2026-09-08

### Added

- `CLAUDE.starterkit.md` §2 — "Decisions are resolved BEFORE the task is written — a task never carries an open fork": a task, plan node or spec records decided behaviour only. Every fork it depends on is resolved before the tracker write — decided on the spot when one option is clearly better, or asked one question at a time in the message when it is genuinely the user's call — and the banned body shapes ("forks for the user to call", "decide whether X or Y", "per fork N", "wire it or remove it", "TBD", an Options section with no chosen option, a title ending in "or remove") are named with a tripwire and the incident that prompted it. §1's planning line and §2's "Capture decisions" gain matching clauses: no open decision parked in a task or spec, and a decision is captured as the chosen behaviour, never as the fork it resolved.

## [0.4.0] - 2026-09-07

### Added

- **`LICENSE` (MIT).** The repo is now MIT-licensed so anyone cloning it may install, modify, and redistribute it. Added a License section to `README.md`, and `LICENSE` ships in the release bundle.
- **`worklog` add-on, offered by an install-time prompt that defaults to yes.** The `worklog`-specific guidance moves out of the always-shipped ruleset into a separate `CLAUDE.starterkit-worklog.md` fragment. `install.sh` / `install.ps1` prompt for it (Enter accepts); opt out with `--no-worklog` (`-NoWorklog` on Windows) or `STARTERKIT_WORKLOG=0`, or install without prompting via `--with-worklog` / `-WithWorklog` / `=1`. Non-interactive runs install it by default. Both `INSTRUCTIONS` guides document the manual add-on step, and `make_bundle.py` ships the fragment.

### Changed

- **De-personalized the shipped ruleset for a public audience.** The `worklog` §10 bullet ("my cross-session task/decision log", pinned to a specific tool) is replaced by a generic pointer to the optional add-on. The §5 emoji example no longer describes one specific machine's kitty/FiraCode setup — it now reads as a general "Nerd Font with no colour-emoji fallback" failure case. `README.md` reframes the kit as one person's opinionated ruleset to fork.

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
