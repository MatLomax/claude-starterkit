# Compact instructions

Compaction clears old material out of context. It is not a new session. The summary it produces is
the whole of the working state the next turn starts from, so write it as a complete handoff from the
agent that holds the full context, trusted as if the session had never been compacted. Structure it
under these headings:

1. **Task and scope.** What the user asked for, in their terms, and what is explicitly in or out of
   scope. Every standing instruction and correction the user gave this session, verbatim where the
   wording matters, including any that override the ruleset.
2. **Established facts.** Everything found, measured, read or decided that the work depends on and
   that is not instant to re-derive: root causes and their evidence, figures and counts with their
   source, exact identifiers (full SHAs, branches, file paths, symbols, task slugs, IDs, hostnames),
   what each checked system actually holds, and what was checked and ruled out. Each item is stated as
   fact, with its source in a few words. These items are TRUSTED: the next agent treats them as
   verified in this session and does not re-check them. So only list what was actually verified, and
   mark anything not verified as `(unverified)`.
3. **Decisions.** Each decision the user made, and each fork resolved, with the chosen option and the
   reason. State the decision itself, not the options it chose between.
4. **State of the work.** What is done, what is in flight (background jobs or agents still running,
   with their IDs and output paths), and the exact git state of every repo touched: what is
   committed (with SHAs), what is uncommitted, and what is unpushed.
5. **Open items and blockers.** What is waiting on the user (with the question as it was put),
   external blockers, and known gaps with the tracked node that holds each.
6. **Next step.** The precise next action, and whether it is authorised to start or waiting on a "go".

Leave out raw tool output, file dumps, dead ends that taught nothing, and restatements of what the
ruleset or a project's `CLAUDE.md` already says. Point to a record (a worklog task, a doc, a scratch
file) instead of copying it, but copy any fact the next step depends on so that it needs no lookup.
