# claude-starterkit — working on this repo

These are instructions for working on the starterkit repo itself. They are not shipped:
`make_bundle.py` bundles an explicit file list, and this file is not on it. The shipped ruleset is
`CLAUDE.starterkit.md`.

## Releases

- Releases are cut by `.github/workflows/release.yml`, never by hand. On a push to `main` it reads the
  first versioned `## [X.Y.Z]` heading in `CHANGELOG.md`. If `vX.Y.Z` has no tag yet, it tags the
  commit, builds the bundle with `make_bundle.py`, and publishes the GitHub release with that
  version's changelog section as the notes and `dist/claude-starterkit-X.Y.Z.zip` attached.
- To cut a release (only on an explicit release instruction): move the `[Unreleased]` entries under a
  new `## [X.Y.Z] - YYYY-MM-DD` heading, commit with a release subject per `.git/COMMIT_STYLE.md`,
  and push to `main`. Do not create or push a tag yourself.
- A release is done when the workflow run is green and the release exists on GitHub with its zip
  (`gh run list -R MatLomax/claude-starterkit`, `gh release view vX.Y.Z -R MatLomax/claude-starterkit`).
  A red run means the release is not done.
- To publish the release for a tag that already exists (a backfill, or a re-publish after a failed
  run): `gh workflow run release.yml -R MatLomax/claude-starterkit -f version=X.Y.Z`. It builds from
  that tag's own tree.

## Working copy

The working copy lives on `samwise:/data/projects/claude-starterkit`; run git there over `ssh samwise`.
After a change lands, reinstall on the machine that needs it with `install.sh`.
