# Review before done

The single source of truth for reviewing work before it counts as done. Installed by the
starterkit but **not enabled by default**: it applies only where a `CLAUDE.md` imports it
(`@~/.claude/review-rules.md`). Do not restate these rules elsewhere; edit them in the
starterkit repo.

- **One review, by an agent that did not do the work.** Before marking a task implemented or
  done (and before committing it), run one review agent with none of the implementer's context.
  Give it the task scope, acceptance criteria, implementation and tests, and ask whether the
  change does what the task asked, correctly: bugs, wrong behaviour, unmet acceptance criteria,
  broken or false-green tests, regressions. It runs after the gates are green.
- **Fix, re-review the fixes once, then stop.** Fix the real defects it finds, then re-review only
  those fixes, once. Anything still open after that goes to the user; do not start another round.
- **A review judges the product, not the paperwork.** Demands for more proof, evidence trails,
  counter-evidence, stricter attribution, or rigour beyond the task's acceptance criteria are not
  findings and never block completion. A genuine defect outside the task's scope becomes its own
  tracked task, not a reason to widen this one.
- **Record the outcome briefly.** Note on the task what the review found and what was fixed, and
  file any out-of-scope defect as its own task. That is the whole of the review's bookkeeping.
