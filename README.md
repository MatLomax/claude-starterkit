# Claude Code ruleset + guardrail hooks

A user-level `CLAUDE.md` (working standards + interaction rules) plus a set of Claude Code hooks that
mechanically enforce the parts that can be enforced. Everything is machine- and project-agnostic.

This is one person's opinionated ruleset, shared in case it's useful — fork it and cut what doesn't
fit your workflow. The installer never overwrites your own `CLAUDE.md` or clobbers your
`settings.json`; it layers on top and every opinionated default is set only if you haven't chosen
your own (see [What it installs](#what-it-installs)).

## Install

macOS / Linux:

```sh
curl -fsSL https://github.com/MatLomax/claude-starterkit/releases/latest/download/install.sh | sh
```

Windows (PowerShell; see `INSTRUCTIONS-windows.md`):

```powershell
irm https://github.com/MatLomax/claude-starterkit/releases/latest/download/install.ps1 | iex
```

The same one-liner reinstalls or upgrades; no local copy of this repo is needed. It downloads the
installer for your OS and CPU from the latest release, checks its SHA-256, and runs it. The installer
is a single self-contained binary with the ruleset, hooks and statusline built in, so nothing but
Python 3 (which the hooks need) has to be installed first.

Then **restart Claude Code** (or start a fresh session) so the hooks load. Re-running is safe
(idempotent). It installs the ruleset as a separate `~/.claude/CLAUDE.starterkit.md` and
ensure-appends a single `@./CLAUDE.starterkit.md` import to your `~/.claude/CLAUDE.md` — **your own
`CLAUDE.md` is never overwritten**. It **backs up** `~/.claude/settings.json` (timestamped `.bak-…`)
and **merges** into it without clobbering or reordering your other config. Honours
`$CLAUDE_CONFIG_DIR` if set, else `~/.claude`.

Options pass through to the installer (`--help` lists them all):

```sh
curl -fsSL https://github.com/MatLomax/claude-starterkit/releases/latest/download/install.sh | sh -s -- --no-worklog --no-plugins
```

```powershell
& ([scriptblock]::Create((irm https://github.com/MatLomax/claude-starterkit/releases/latest/download/install.ps1))) -NoWorklog -NoPlugins
```

`STARTERKIT_VERSION=X.Y.Z` installs a specific release instead of the latest. Prebuilt installers
cover Linux and macOS (x64 and arm64) and Windows (x64 and arm64). Running `./install.sh` or
`install.ps1` from a clone of this repo does the same as the one-liner: it downloads the released
installer.

## Recommended plugins

Along with the worklog question, the installer offers a short list of recommended plugins in a
multiselect, **none ticked by default**, and installs the ticked ones after the core install. Nothing is vendored: ticking one runs that plugin's own official
installer, and re-running it updates the plugin.

- **[ripwire](https://github.com/redhat-et/ripwire)** — deterministic codebase maps for coding agents
  (a CLI plus agent skills). Installed with ripwire's documented quick install: its official
  `scripts/install.sh` is fetched with `curl -fsSL` and run with `RIPWIRE_REPO=redhat-et/ripwire`
  (a failed or empty download fails the install rather than running nothing), and it verifies its
  release, installs the binary to `~/.local/bin` and activates its skills. The install counts as
  done only once ripwire is actually found afterwards. Once it installs, the
  installer offers to register ripwire's Claude Code hooks (`<prefix>/share/ripwire/skills/install.sh
  --hook`: a session-start primer, a prompt router and a tool-call recorder that never blocks),
  defaulting to yes; if `jq` (which those hooks need) is missing, it says so and defaults to no.
  ripwire has no official Windows installer, so on Windows it is listed with a link to its releases.

Without a terminal (CI, scripts) the installer prompts for nothing: it installs only the plugins named
with `--plugins=ripwire` (or `STARTERKIT_PLUGINS=ripwire`), and runs their follow-up steps only with
`--plugin-hooks` (`STARTERKIT_PLUGIN_HOOKS=1`). `--no-plugins` skips the list. A plugin that fails to
install, or that has no installer on this platform, is reported at the end with a non-zero exit, and
does not undo or stop the rest of the install.

## What it installs

- **`CLAUDE.starterkit.md`** → `~/.claude/CLAUDE.starterkit.md` — the user-level ruleset, pulled into
  context by an idempotent `@./CLAUDE.starterkit.md` line appended to your `~/.claude/CLAUDE.md`
  (your own `CLAUDE.md` is left intact — the starterkit layers on top of it).
- **Three parts of the ruleset, imported by `CLAUDE.starterkit.md` itself** (so your `CLAUDE.md`
  needs no extra line) and installed beside it, which keeps each file under Claude Code's
  40k-character per-file warning:
  - `CLAUDE.starterkit-agents.md` — §4, multi-agent and workflow authoring, and the spend limits.
  - `CLAUDE.starterkit-git.md` — §7 commits and PRs, §8 session isolation, §9 worktrees.
  - `CLAUDE.starterkit-compaction.md` — the "# Compact instructions" Claude Code follows when it
    writes a compaction summary.
- **`CLAUDE.starterkit-worklog.md`** — an add-on that points the ruleset's generic "tracked node" /
  "task graph" wording at [`worklog`](https://github.com/MatLomax/worklog), a cross-session task log.
  The installer offers it via a prompt that **defaults to yes** (press Enter to install). Opt out with
  `--no-worklog` / `-NoWorklog`, or `STARTERKIT_WORKLOG=0`; non-interactive runs install it by default.
  Skip it and the base ruleset is unaffected.
- **Project memory** — an add-on that keeps each project's
  [auto memory](https://code.claude.com/docs/en/memory#auto-memory) inside the project, in
  `<project>/.claude/memory/`, so every path the project is opened from (an sshfs mount and the
  machine it lives on, a second clone location) shares one memory. The project is the git repo
  (excluded from git through `.git/info/exclude`), or outside a repo the directory the session
  starts in. It wires `project-memory.py` (SessionStart, and PreToolUse on `Write|Edit`): Claude
  Code keeps auto memory under `~/.claude/projects/<path-derived name>/memory/`, and
  `autoMemoryDirectory` accepts only an absolute path, so the hook links that directory to the
  project's (a symlink; a junction on Windows). The project's directory is created only when the
  first memory is saved: the hook links just before that write, and at session start it links a
  project that already has one. Memories already in the per-path directory are moved into the
  project. It works from every surface that runs hooks (CLI, IDE extensions, the desktop app). It
  leaves alone a per-path directory that is already a link (one pointing elsewhere was made on
  purpose), or whose files clash with the project's by name, saying so; and it does nothing when
  `autoMemoryDirectory` is set. The installer offers it via a prompt that **defaults to no**; opt
  in with `--with-project-memory` / `-WithProjectMemory`, or `STARTERKIT_PROJECT_MEMORY=1`.
  The link relies on how Claude Code names the per-path directory and on when it loads memory,
  neither of which is documented: if a release changes either, memory falls back to the per-path
  directory and nothing is lost.
- **14 hooks** → `~/.claude/hooks/`, wired into `settings.json`:
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
  - `sleep-guard.py` (PreToolUse) — blocks a `Bash`/`PowerShell` command that sleeps (`sleep`,
    `Start-Sleep`, inline `time.sleep`/`setTimeout`, and disguised delays such as
    `timeout N tail -f /dev/null`, `read -t N`, `ping localhost`): wait on background work via its
    completion notification, on a GitHub Actions run via `gh-run-wait.py`, and on other external
    state via the tool's own blocking wait, not by polling. It also sets `gh-run-wait.py`'s limits:
    the helper runs only with `run_in_background: true`, as one direct call with literal arguments
    (not in a loop, a wrapper or another shell), with `--timeout` at most 300 seconds and
    `--interval` at least 10. Recognising a run is fail-closed: a command that names the helper
    counts as running it unless it only reads, copies or prints the file (`git`, `grep`, `cat`, ...).
  - `gh-run-wait.py` (not a hook: a helper the sleep-guard names) — waits on a GitHub Actions run
    (`python3 ~/.claude/hooks/gh-run-wait.py <run URL>`, run in the background): checks it with
    HTTP GETs every 15 seconds (`--interval`) and exits when the run's status or conclusion changes
    or a job finishes, printing each job's state; a finished run returns at once, and `--timeout`
    (default 300 seconds) bounds the whole wait. Exit 0 finished green, 1 finished otherwise,
    3 changed and still running, 124 no change in time, 2 a usage or API error.
  - `spend-guard.py` (PreToolUse, all tools) — blocks every tool call once spend passes a limit, so
    the model stops and reports: `PROMPT_SPEND_LIMIT` (default `3M` API-price-weighted tokens) for
    the main conversation + subagents since your last message, and `WORKFLOW_SPEND_LIMIT` (default
    `10M`) per Workflow run. `off` disables either.
  - `tie-break-guard.py` (Stop) — blocks turn-end if the reply leaves record-keeping undone:
    asks permission to log a gap, claims a record with no write behind it, or promises one and
    ends the turn.
  - `notification-guard.py` (MessageDisplay, PreToolUse, PostToolUse, Stop, UserPromptSubmit) — a
    background job's completion only ever arrives as input in a new turn. When the assistant's own
    text holds something shaped like one (a system-reminder or task-notification tag, "Background
    task X completed with exit code N"), the hook flags it as the text streams and marks the line on
    screen, then tells the assistant after its next tool call (or denies the call, when the flag is
    already set) and blocks a reply that ends the turn on it. The one tool call right after the text
    still runs in an interactive session: Claude Code runs PreToolUse before any hook sees the text.
    Quoted and code text is ignored.
  - `compact-snapshot.py` (PreCompact) — copies the full session transcript to
    `~/.claude/compact-transcripts/` before every compaction (newest 10 kept), as a reference for
    exact details the summary did not keep. Never blocks a compaction.
  - `compact-resume.py` (SessionStart, matcher `compact`) — tells the post-compaction agent that the
    summary's Established facts are trusted as verified (no re-checking), and where the transcript
    copy is, as an optional reference that is not loaded.
  - `compact-continue.py` (PostCompact, matcher `manual`, `asyncRewake`) — after a manual `/compact`,
    wakes Claude to carry on from the summary's Next step if it is authorised, or to say in one line
    what it is waiting on. Auto-compaction continues by itself, so it is left alone.
- **`review-rules.md`** (opt-in, not enabled by default) — installed to `~/.claude/review-rules.md`
  but imported nowhere. It defines the review before done: one review by an agent that didn't do
  the work, fixes re-reviewed once, then anything open goes to the user; paperwork demands are not
  findings. It adds tokens to every session that loads it, so enable it only where wanted, with
  `@~/.claude/review-rules.md` in a machine's `~/.claude/CLAUDE.md` or a project's `CLAUDE.md`.
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
  `DO_NOT_TRACK=1`; plus `enableArtifact:false` (turns the Artifact tool off),
  `includeCoAuthoredBy:false`, `feedbackDrafts:off`, `promptSuggestionEnabled:false`,
  `spinnerTipsEnabled:false` (no tips under the spinner), `remoteControlAtStartup:false`,
  `askUserQuestionTimeout:never`, `worktree.baseRef:fresh`, `effortLevel:high`,
  `autoCompactEnabled:true` (compacts automatically as context fills), and
  `cleanupPeriodDays:36500` (keeps session transcripts instead of purging them after 30 days).
  The `opus` alias is left unpinned (latest Opus); an `env.ANTHROPIC_DEFAULT_OPUS_MODEL` set to
  exactly `claude-opus-4-8` is removed on install, any other value is kept.

## Notes

- The hooks are written for `bypassPermissions`/`dontAsk` modes: they use `deny` (a guardrail that
  holds under those modes) and context injection, never a permission prompt.
- Heuristics (git flag matching, correction/question detection) are pragmatic — tune the scripts in
  `~/.claude/hooks/` to taste.
- To uninstall: delete `~/.claude/CLAUDE.starterkit.md` and its three imported parts, remove the `@./CLAUDE.starterkit.md`
  line from `~/.claude/CLAUDE.md`, restore the `settings.json.bak-…`, and delete the hook scripts. If
  you enabled the worklog add-on, also delete `~/.claude/CLAUDE.starterkit-worklog.md` and its
  `@./CLAUDE.starterkit-worklog.md` line (re-running with `--no-worklog` does not remove it). If
  you enabled project memory, also remove its `project-memory.py` SessionStart and PreToolUse
  entries from `settings.json` (re-running with `--no-project-memory` does not remove them); the
  links it made and each project's `.claude/memory/` stay, so move a project's memories back before
  deleting its link.
- **Upgrading from ≤ 0.3.1?** Those versions installed the ruleset *inline* as `~/.claude/CLAUDE.md`.
  This version installs it as `CLAUDE.starterkit.md` + an import, so after upgrading, delete the old
  inline ruleset from your `~/.claude/CLAUDE.md` (keep the `@./CLAUDE.starterkit.md` line) so it isn't
  loaded twice.

## License

MIT — see [`LICENSE`](LICENSE).
