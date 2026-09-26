#!/usr/bin/env python3
"""PreToolUse hook (matcher: all tools): stop work once its spend passes a limit.

Two separate limits, each enforced by denying tool calls so the model can only end its turn and
report. A deny is a guardrail (holds under bypassPermissions). Hooks fire inside subagents and
Workflow agents too, so a runaway anywhere in the session tree is stopped.

- Prompt limit (env PROMPT_SPEND_LIMIT, default 3M): everything the main conversation and its
  subagents spend since the user's last typed message. Task notifications and scheduled /loop
  wakeups do not reset it; the user's next message does. Checked on calls from the main
  conversation and from regular subagents.
- Workflow limit (env WORKFLOW_SPEND_LIMIT, default 10M): the total spend of one Workflow run (its
  agents' transcripts under `subagents/workflows/<run>/`), over the run's whole life. Checked on
  calls from that run's agents only; workflow spend does not count toward the prompt limit.

Spend is API-price-weighted tokens: input x1, cache write x1.25, cache read x0.1, output x5.
Limits take a number of weighted tokens with an optional k/M suffix ("3M", "500k", "3000000");
"0" or "off" disables that limit.

Reads transcripts incrementally: per-file byte offsets and spend (per-minute buckets for the prompt
pot, a running total per workflow file) are kept in a small state file per session under
~/.cache/claude-spend-guard/, so each call parses only new lines. The state is replaced atomically as
one consistent snapshot, so concurrent calls from parallel agents never double-count.
"""
import glob
import json
import os
import sys
import tempfile

DEFAULT_PROMPT_LIMIT = 3_000_000
DEFAULT_WORKFLOW_LIMIT = 10_000_000
STATE_VERSION = 2
STATE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "claude-spend-guard")
AUTOMATED_PREFIXES = ("<task-notification", "<local-command", "<command-", "Caveat:")


def parse_limit(raw, default):
    if raw is None or raw.strip() == "":
        return default
    s = raw.strip().lower()
    if s in ("0", "off", "none", "false"):
        return 0
    mult = 1
    if s.endswith("m"):
        mult, s = 1_000_000, s[:-1]
    elif s.endswith("k"):
        mult, s = 1_000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return default


def cost(usage):
    return (usage.get("input_tokens", 0) + 1.25 * usage.get("cache_creation_input_tokens", 0)
            + 0.1 * usage.get("cache_read_input_tokens", 0) + 5 * usage.get("output_tokens", 0))


def is_human_prompt(rec):
    """True for a message the user typed into the main conversation."""
    if rec.get("type") != "user" or rec.get("isSidechain"):
        return False
    origin = rec.get("turnOrigin") or (rec.get("origin") or {}).get("kind")
    if origin is not None:
        return origin == "human"
    if rec.get("isMeta"):
        return False
    content = (rec.get("message") or {}).get("content")
    return isinstance(content, str) and not content.startswith(AUTOMATED_PREFIXES)


def locate(path):
    """(main transcript, workflow run id or None) for a main, subagent or workflow-agent transcript."""
    head, parts = path, []
    while True:
        head, tail = os.path.split(head)
        if not tail:
            return path, None
        if tail == "subagents":
            below = parts[::-1]
            run = below[1] if len(below) >= 3 and below[0] == "workflows" else None
            return head + ".jsonl", run
        parts.append(tail)


def load_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(state, f)
    os.replace(tmp, path)


def read_new(path, fstate, is_main, state):
    """Consume complete lines appended to `path` since the last call. A workflow file (one with a
    `run`) accumulates its whole spend in `total`; any other file keeps per-minute buckets from the
    prompt anchor on."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    off = fstate.get("off", 0)
    if size < off:  # file replaced or truncated: start over
        off, fstate["buckets"], fstate["ids"], fstate["total"] = 0, {}, [], 0
    if size == off:
        return
    with open(path, "rb") as f:
        f.seek(off)
        data = f.read()
    end = data.rfind(b"\n")
    if end < 0:
        return
    fstate["off"] = off + end + 1
    buckets = fstate.setdefault("buckets", {})
    ids = fstate.setdefault("ids", [])
    for line in data[:end].split(b"\n"):
        try:
            rec = json.loads(line)
        except Exception:
            continue
        ts = rec.get("timestamp") or ""
        if is_main and is_human_prompt(rec) and ts > state["anchor"]:
            state["anchor"] = ts
            for other in state["files"].values():
                if not other.get("run"):
                    other["buckets"] = {k: v for k, v in other.get("buckets", {}).items() if k >= ts[:16]}
            buckets = fstate["buckets"] = {k: v for k, v in buckets.items() if k >= ts[:16]}
            continue
        if rec.get("type") != "assistant" or not ts:
            continue
        if not fstate.get("run") and ts < state["anchor"]:
            continue
        msg = rec.get("message") or {}
        mid = msg.get("id")
        if mid in ids:
            continue
        if mid:
            ids.append(mid)
            del ids[:-64]
        c = cost(msg.get("usage") or {})
        if fstate.get("run"):
            fstate["total"] = fstate.get("total", 0) + c
        else:
            buckets[ts[:16]] = buckets.get(ts[:16], 0) + c


def spent(transcript, session_id):
    """(prompt-pot spend since the anchor, {workflow run: spend}, {agent file basename: run})."""
    main, _ = locate(transcript)
    state_path = os.path.join(STATE_DIR, f"{session_id or os.path.basename(main)}.json")
    state = load_state(state_path)
    if state.get("v") != STATE_VERSION:
        state = {"v": STATE_VERSION, "anchor": "", "files": {}}
    files = state["files"]
    subagents = os.path.join(main[:-len(".jsonl")], "subagents")
    paths = [main] + sorted(glob.glob(os.path.join(subagents, "**", "*.jsonl"), recursive=True))
    for p in paths:
        fstate = files.setdefault(p, {"run": locate(p)[1]})
        read_new(p, fstate, p == main, state)
    save_state(state_path, state)
    anchor_minute = state["anchor"][:16]
    prompt = sum(v for f in files.values() if not f.get("run")
                 for k, v in f.get("buckets", {}).items() if k >= anchor_minute)
    runs, agents = {}, {}
    for p, f in files.items():
        if f.get("run"):
            runs[f["run"]] = runs.get(f["run"], 0) + f.get("total", 0)
            agents[os.path.basename(p)] = f["run"]
    return prompt, runs, agents


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    prompt_limit = parse_limit(os.environ.get("PROMPT_SPEND_LIMIT"), DEFAULT_PROMPT_LIMIT)
    workflow_limit = parse_limit(os.environ.get("WORKFLOW_SPEND_LIMIT"), DEFAULT_WORKFLOW_LIMIT)
    transcript = data.get("transcript_path")
    if not (prompt_limit or workflow_limit) or not transcript or not transcript.endswith(".jsonl"):
        sys.exit(0)

    try:
        prompt, runs, agents = spent(transcript, data.get("session_id"))
    except Exception:
        sys.exit(0)

    run = locate(transcript)[1]
    if run is None and data.get("agent_type") == "workflow-subagent":
        run = agents.get(f"agent-{data.get('agent_id')}.jsonl", "")

    if run is not None:
        total = runs.get(run, 0)
        if workflow_limit and total >= workflow_limit:
            deny(
                f"Workflow spend limit reached: this Workflow run has spent {total / 1e6:.1f}M "
                f"weighted tokens (limit {workflow_limit / 1e6:.1f}M, set by WORKFLOW_SPEND_LIMIT). "
                "Every tool call in this run is now blocked. Do not retry or work around this: end "
                "your turn now and return what you have, marked as incomplete."
            )
        sys.exit(0)

    if prompt_limit and prompt >= prompt_limit:
        deny(
            f"Spend limit reached: {prompt / 1e6:.1f}M weighted tokens since the user's last message "
            f"(limit {prompt_limit / 1e6:.1f}M, set by PROMPT_SPEND_LIMIT; Workflow runs have their own "
            "limit and are not counted here). Every tool call is now blocked. Do not retry or work "
            "around this: end your turn now. A subagent returns what it has to its parent; the main "
            "conversation reports to the user what was done, what is still open and what the next "
            "step would cost. The user's next message resets the count."
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
