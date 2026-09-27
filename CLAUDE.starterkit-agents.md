## 4. Multi-agent & workflow authoring

- **Set an explicit `{model}` on EVERY sub-agent** (Agent tool, Workflow `agent()` calls) — never
  inherit the session model by omission. When the session runs a top-tier model, a defaulted fan-out
  burns tokens at that rate across the whole fleet. Reflect the per-phase choice in
  `meta.phases[].model`.
- **Roster + tiering:**
  - **Always the tier shorthand, never a model id.** `opus`, `sonnet`, `haiku` — each rides the
    latest release of its tier automatically; writing an id in a prompt or a workflow is redundant
    at best and stale at worst.
  - **Tier by EFFORT, not by default.** Judgment — architecture, cross-surface semantics, design
    forks, verify/audit-first investigation, coordinating roots → Opus. Genuinely mechanical,
    pattern-following work with an in-repo precedent to copy → Sonnet (or haiku for trivial
    sweeps). When unsure, pick Opus — under-tiering is the recurring failure mode.
- **Name agents with a descriptive slug — it's encouraged.** A `name:` that's a short descriptive
  slug (to tell parallel agents apart) is fine and helps. What's banned is the *teammate* pattern —
  the team system where agents are **left open** as idle, addressable mailboxes that need explicit
  shutdown; a plain named subagent still runs to completion, returns its report, and self-terminates.
  Parallel fan-out works with multiple Agent calls in one block.
- **The orchestrator holds the test-and-judge seat.** Fan out agents for parallel *work*, then run
  the gates and judge the results *yourself* and dispatch targeted fixes — don't bake a self-contained
  verify/decide/self-repair loop into the workflow and walk away.
- **Agents run ONLY targeted tests — never the full suite.** Reason about blast radius: an
  app-only change can't regress an unrelated subsystem's suite. Only the *orchestrator* runs the full
  suite, once, at the very end. When orchestrating a wave of concurrent agents sharing the tree, gate
  only after EVERY agent has returned (mid-wave, others' half-written edits make the gates report reds
  that belong to in-flight work).
- **Spend is capped; at the cap, stop and report.** Two limits, in API-price-weighted tokens (input
  x1, cache write x1.25, cache read x0.1, output x5):
  - **Per prompt — `PROMPT_SPEND_LIMIT`, default 3M:** everything the main conversation and its
    subagents spend after the user's last message. Task notifications and `/loop` wakeups do not
    reset it; the user's next message does.
  - **Per Workflow run — `WORKFLOW_SPEND_LIMIT`, default 10M:** the whole spend of one Workflow run's
    agents, over the run's life. Workflow spend does not count toward the prompt limit.

  At a limit every tool call in that scope is denied — do not retry or route around it: end the turn,
  and report what was done, what is open, and what the next step would cost (a Workflow agent returns
  what it has, marked incomplete). Measured against ~2,700 real prompts, 95% spend under 1.25M and 40
  passed 3M; past Workflow runs of 15-32 agents spent 4.3-5.4M; the runaway that prompted this spent
  104.5M after one reply. A planned big run raises the limit for its session
  (`PROMPT_SPEND_LIMIT=10M claude`) or simply continues on the user's next message. For unattended
  `claude -p` runs, also pass the native `--max-budget-usd`, which caps dollars and stops background
  subagents at the cap.

*Enforcement note:* the spend-guard `PreToolUse` hook (all tools) enforces both spend limits, in
subagents and Workflow agents as well as the main thread. The agent-guard `PreToolUse` hook (matcher `Agent`) denies a sub-agent spawn that
omits `model`. Prose-only (not hookable): the teammate /
left-open ban, explicit-model on
**workflow-internal** `agent()` calls (invisible to a PreToolUse hook), and the orchestrator-judge
seat + targeted-tests discipline (judgment / per-project command patterns).
