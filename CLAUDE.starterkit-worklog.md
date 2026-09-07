# Optional add-on: worklog task/decision log

The installer offers this fragment via a prompt that **defaults to yes** (Enter installs it); pass
`--no-worklog` (or set `STARTERKIT_WORKLOG=0`) to skip it. It teaches the assistant to use
[`worklog`](https://github.com/MatLomax/worklog) — a
cross-session task/decision log — as the tracker the main ruleset keeps referring to ("a tracked
node", "the task graph"). Drop it if you don't use worklog; the base ruleset stands on its own
without it.

- **Use `worklog` as the cross-session task/decision log when a project has it enabled.** It is an
  MCP server (SQLite-backed, distributed as a single Go binary). MCP is attach-only — inert until
  `worklog init` has run in that project, which creates the DB at `<project>/.worklog/`. It needs the
  binary on PATH; if `command not found`, install it (`go install
  github.com/MatLomax/worklog/cmd/worklog@latest`, or grab a release binary) before use. **Creating
  tasks: omit `slug` and let it derive from the title** — the auto title-to-slug is enough in almost
  every case; set an explicit slug only when strictly necessary.
- **Keep an enabled project's worklog current as part of the change — not as an afterthought.** When
  you change a repo that has worklog enabled (a `.worklog/` is present), updating that repo's worklog
  is part of doing the work: record the task, the key decisions (`task-decide`), and any
  surfaced-but-deferred gaps as tracked nodes, so the next session sees what was done and why. A
  change that lands with its worklog untouched leaves the tracker lying. This holds even when the
  worklog MCP isn't attached to the current session — drive `worklog serve --db
  <repo>/.worklog/tasks.db` over its newline-delimited JSON-RPC 2.0 (stdin/stdout) to reach it.
