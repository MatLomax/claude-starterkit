# claude-starterkit — working on this repo

These are instructions for working on the starterkit repo itself. They are not shipped: the
installer embeds an explicit file list (`payload.go`), and this file is not on it. The shipped ruleset
is `CLAUDE.starterkit.md` with the parts it imports (`CLAUDE.starterkit-agents.md`, `-git.md`,
`-compaction.md`), plus the optional `CLAUDE.starterkit-worklog.md` add-on.

## Releases

- Releases are cut by `.github/workflows/release.yml`, never by hand. On a push to `main` it reads the
  first versioned `## [X.Y.Z]` heading in `CHANGELOG.md`. If `vX.Y.Z` has no tag yet, it tags the
  commit, runs the Go tests, builds the installer for every platform with
  `scripts/build-release.sh`, and publishes the GitHub release with that version's changelog section
  as the notes and the release assets attached: one `starterkit-install-<os>-<arch>` binary per
  platform, a `.sha256` for each, and the `install.sh` / `install.ps1` bootstraps.
- To cut a release (only on an explicit release instruction): move the `[Unreleased]` entries under a
  new `## [X.Y.Z] - YYYY-MM-DD` heading, commit with a release subject per `.git/COMMIT_STYLE.md`,
  and push to `main`. Do not create or push a tag yourself.
- A release is done when the workflow run is green and the release exists on GitHub with its assets
  (`gh run list -R MatLomax/claude-starterkit`, `gh release view vX.Y.Z -R MatLomax/claude-starterkit`).
  A red run means the release is not done.
- To publish the release for a tag that already exists (a backfill, or a re-publish after a failed
  run): `gh workflow run release.yml -R MatLomax/claude-starterkit -f version=X.Y.Z`. It builds from
  that tag's own tree (a tag from before the Go installer builds its zip with its own `make_bundle.py`).

## The installer

- `cmd/starterkit-install` is the installer, a Go program with the payload embedded by
  `payload.go`: every `CLAUDE.starterkit*.md`, `review-rules.md`, both statusline scripts and
  `hooks/*.py`. A new ruleset part or hook script is picked up by those globs; a new hook also needs
  its entry in the `Hooks` table in `internal/install/settings.go`. The recommended plugins are in
  `internal/plugins/plugins.go`.
- `install.sh` and `install.ps1` are only bootstraps: they download the released binary for the
  platform, check its SHA-256 and run it. `.github/workflows/ci.yml` runs the Go tests on Linux,
  macOS and Windows and installs through both one-liners against locally served release assets.
- Build and test locally with Go (`go test ./...`; `go build ./cmd/starterkit-install`, then run the
  binary with `CLAUDE_CONFIG_DIR` pointing at a scratch directory). `STARTERKIT_BASE_URL` points the
  bootstraps at another copy of the release assets built by `scripts/build-release.sh`: serve that
  directory over HTTP (`python3 -m http.server`), which both bootstraps accept; `install.sh` with
  curl also takes `file:///path/to/dir`.

## Working copy

The working copy lives on `samwise:/data/projects/claude-starterkit`; run git there over `ssh samwise`.
After a release lands, reinstall on the machine that needs it with the one-liner, which needs no
local copy: `curl -fsSL https://github.com/MatLomax/claude-starterkit/releases/latest/download/install.sh | sh`
(Windows: `irm https://github.com/MatLomax/claude-starterkit/releases/latest/download/install.ps1 | iex`).
