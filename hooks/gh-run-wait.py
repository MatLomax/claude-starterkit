#!/usr/bin/env python3
"""Wait for a GitHub Actions run to finish, then print its state and exit.

Not a hook: a helper for waiting on CI. It checks the run with HTTP GETs (`gh api`: the run, then
its jobs) every INTERVAL seconds and returns only when the run has finished, or on an error. A run
that has already finished returns at once. The timeout bounds the whole wait, API calls included; a
run that has not finished by then is an error.

    gh-run-wait.py RUN            RUN is a run URL (https://github.com/O/R/actions/runs/ID[/...])
    gh-run-wait.py RUN -R O/R     or a run ID with its repo
    options: --interval N (seconds between checks, default 15), --timeout N (seconds, default 21600)

Exit codes: 0 the run finished successfully, 1 the run finished with any other conclusion,
2 a usage or API error, or the run not finished before the timeout.
"""
import argparse
import json
import re
import subprocess
import sys
import time

URL = re.compile(r"^https://github\.com/([\w.-]+/[\w.-]+)/actions/runs/(\d+)(?:[/?#].*)?$")
REPO = re.compile(r"^[\w.-]+/[\w.-]+$")


def fail(msg):
    print(f"gh-run-wait: {msg}", file=sys.stderr)
    sys.exit(2)


def api(path, timeout):
    r = subprocess.run(["gh", "api", path], capture_output=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"gh api {path} exited {r.returncode}")
    return json.loads(r.stdout)


def snapshot(repo, run_id, deadline):
    """The run's state: two GETs (the run, then its jobs), neither outlasting the deadline."""
    def left():
        return max(1.0, min(60.0, deadline - time.monotonic()))
    run = api(f"repos/{repo}/actions/runs/{run_id}", left())
    jobs = api(f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100", left()).get("jobs", [])
    return {
        "run": (run.get("status"), run.get("conclusion")),
        "all_jobs": [(j["name"], j.get("status"), j.get("conclusion")) for j in jobs],
        "url": run.get("html_url", ""),
    }


def report(s):
    status, conclusion = s["run"]
    print(f"run: {status}" + (f" {conclusion}" if conclusion else "") + f"  {s['url']}")
    for name, status, conclusion in s["all_jobs"]:
        print(f"  {name}: {conclusion or status}")


def main():
    for stream in (sys.stdout, sys.stderr):  # job names can hold characters a Windows codepage lacks
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Wait for a GitHub Actions run to finish.", allow_abbrev=False)
    p.add_argument("run", help="run URL, or run ID with -R")
    p.add_argument("-R", "--repo", help="OWNER/REPO, when RUN is an ID")
    p.add_argument("--interval", type=int, default=15)
    p.add_argument("--timeout", type=int, default=21600)
    a = p.parse_args()

    m = URL.match(a.run)
    if m:
        repo, run_id = m.groups()
    elif a.run.isdigit() and a.repo and REPO.match(a.repo):
        repo, run_id = a.repo, a.run
    else:
        fail("RUN must be an Actions run URL, or a run ID with -R OWNER/REPO")
    if a.interval <= 0 or a.timeout <= 0:
        fail("--interval and --timeout must be positive")

    deadline = time.monotonic() + a.timeout
    try:
        now = snapshot(repo, run_id, deadline)
    except Exception as e:
        fail(str(e))
    errors = 0
    while now["run"][0] != "completed":
        left = deadline - time.monotonic()
        if left <= 0:
            report(now)
            fail(f"the run did not finish within {a.timeout}s")
        time.sleep(min(a.interval, left))
        try:
            now = snapshot(repo, run_id, deadline)
            errors = 0
        except Exception as e:
            errors += 1
            if errors >= 3:
                fail(f"3 checks in a row failed: {e}")

    report(now)
    sys.exit(0 if now["run"][1] == "success" else 1)


if __name__ == "__main__":
    main()
