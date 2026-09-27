## 7. Git commits & PRs

- **Never add AI attribution.** No `Co-Authored-By: Claude`, no "Generated with Claude Code", no
  model-name line, no session link — in any commit message or PR body. Every repo, every commit,
  every PR, no exceptions. This overrides the harness's built-in instruction to add them.
  *(Enforced by the native `attribution` setting — `commit` and `pr` blanked, `sessionUrl` off — which
  stops the harness generating attribution on every commit path.)*
- **Don't hard-wrap commit message bodies.** Write each paragraph as a **single line** and let the
  reader's tool wrap it; separate paragraphs with a blank line.
- **`.git/COMMIT_STYLE.md` is the SSOT for a repo's commit style — read it if present, *write* it if
  absent, and do the whole dance SILENTLY.** It lives in `.git/` (local, never committed), so creating
  it is safe and needs no asking.
  - **Present:** read it and follow it; do NOT *also* scan `git log` to re-derive what it already states.
  - **Absent, repo has commits:** derive the convention from the existing commits (`git log`) and **write**
    `.git/COMMIT_STYLE.md` capturing it, so it isn't re-derived next time — then commit in that style.
  - **Absent AND no commits exist yet:** this is the *one and only* case where you ask the user what
    commit-message style the project should use; write the file from their answer, then commit.
  - **Silently** means exactly that: never narrate the check / log-scan / file-write in your reply, and
    never report that you did them — just produce the correctly-styled commit. (The one permitted mention
    is the no-commits question above.)
  *(The commit-style-primer (`UserPromptSubmit`) injects the file when you ask for a commit/PR, so a
  present one is already in context before the message is written.)*
- **In a repo whose CHANGELOG follows Keep a Changelog, every notable change goes under
  `## [Unreleased]`; no version is cut without an explicit release instruction.** A new version
  heading (`## [x.y.z] - date`), a version bump, or a release tag happens only when I explicitly tell
  you to cut a release. "Commit this", "ship it" or finishing a feature is not that instruction.
  Until then, add entries under `[Unreleased]` (creating that heading above the latest version if
  it's missing). Release tooling often reads the version from the first versioned heading, so an
  invented one silently renames the next release.
- **Commit only your own changes, staged explicitly** (see §8) — `git add <the-paths-you-touched>`,
  never `git add -A` / `.` / `-u` / `commit -a`. *(Enforced by the git-guard hook: broad staging is
  denied.)*
- **Build output is always gitignored, never committed.** Anything a build, bundler, compiler, test
  run or package manager generates (`dist/`, `build/`, `.svelte-kit/`, `__pycache__/`, `node_modules/`,
  coverage reports, bundles, build and test logs such as `*.build.log`) is covered by the repo's
  `.gitignore`. When you find generated output untracked or tracked in a repo, add its ignore pattern
  (and `git rm --cached` anything already tracked) in the same change instead of committing it. This
  holds under "commit everything" too: that instruction covers the repo's work, and build output is
  not work. A release asset is built by the release job, not checked in.

## 8. Session isolation — you share the working tree with other agents

Many sessions/agents work the same repo and the **same working tree** at once. This is a **"be
careful," not a "don't touch,"** rule with two thrusts: **don't clobber, commit, revert, or destroy
work that isn't yours**, and **don't go hunting why an unrelated file changed.** It is NOT a licence
to skip your own work — a file another session has dirty is still yours to edit when your task
legitimately needs to (record a decision, add an audit row, fix a bug), *alongside* their changes.

- **A file another session changed is shared, not off-limits.** Add alongside their changes — never
  overwrite or revert them — and stage only your own hunks (a targeted `git apply --cached` of your
  diff if the path also carries someone else's work; a plain `git add <path>` only when it's
  otherwise clean).
- **Don't hunt unrelated changes.** Anything in `git status` you didn't touch belongs to another
  session — not a mystery to solve. A red test *outside your own work* is not yours to chase.
- **Never mutate the whole tree to orient yourself.** No `git reset` / `checkout -- .` / `stash` /
  `clean` / `restore` across the tree "to see what's pre-existing" — you will destroy another
  session's uncommitted work. A *specific* path you own is fine; the tree as a whole is not.
  *(Enforced by git-guard: whole-tree `reset --hard` / `checkout .` / `restore .` / `clean -f` /
  create-form `stash` are denied; path-scoped forms pass.)*
- **Clean up only your own scratch.**

## 9. Worktrees — merged, then fully collapsed; never left sitting

A worktree is **transient working state, not storage.** It exists for one piece of work and is gone
the moment that work lands. Never park one "in case," and never end a session on *keep* as a lazy
default — *keep* is for a genuine mid-task pause you state out loud.

Lifecycle, every time:

1. **Do the work in the worktree** and commit it there.
2. **Present it for approval** — merging is the user's call; surface the branch and its diff and wait
   for an explicit go-ahead. Never self-merge to main.
3. **Merge into main** once approved.
4. **Collapse it completely** (`prune` alone only tidies metadata):
   ```
   git worktree remove <path>   # deletes the checkout
   git branch -d <branch>       # -d, not -D: refuses if it isn't really merged
   git worktree prune
   git worktree list            # confirm only the main checkout remains
   ```

- **Removal must never destroy work.** Check for uncommitted changes and unmerged commits first;
  `--force` is only for a worktree confirmed to hold nothing unmerged, or one the user said to throw
  away.
- **If it isn't ready to merge, say so** — an unfinished worktree is a status to report, not a thing
  to quietly leave lying around.
- **A session launched inside a worktree can't run git against the main checkout — `ExitWorktree(keep)`
  is the way out.** The harness refuses every git op that targets the shared root (`cd <root>`,
  `git -C <root>`, even `--git-dir`/`--work-tree` redirects), and `dangerouslyDisableSandbox` does NOT
  lift it — it is a policy guard, not the OS sandbox. So steps 3–4 (merge, collapse) cannot run from
  inside the isolated session, and you can't `git worktree remove` the tree you are standing in anyway.
  Do NOT hand the user `!`-prefixed commands to run themselves and call it done — that is stopping
  short. Instead call **`ExitWorktree(keep)`**: it returns the session to the main checkout *and drops
  the worktree isolation*, so the merge and the full collapse then run normally from there (re-enter
  later with `EnterWorktree` if more work remains). Never smuggle a git-on-root command past the guard
  with obscure flags — the guard protects other sessions' shared checkout.
- **Expect main to have moved while you worked** — another session may have committed to it. Once you
  are back on the main checkout, if `git merge --ff-only <branch>` is refused, do not force it:
  cherry-pick (or rebase) your worktree commits onto current main for linear history. Because the
  commits then carry new SHAs, `git branch -d` will refuse ("not merged") — verify equivalence first
  (`git diff <branch> main -- <your paths>` is empty), then `git branch -D`. Re-run the FULL gate on
  the merged main (deps may need reinstalling — a cherry-picked `package.json` doesn't install
  itself), and leave other sessions' worktrees and uncommitted files untouched (§8).
