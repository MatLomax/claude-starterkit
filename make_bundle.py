#!/usr/bin/env python3
"""Bundle the Claude Code starterkit into a versioned zip for release.

Single-sources the version from CHANGELOG.md (the first released `## [x.y.z]`
heading) so the zip name can never drift from the changelog. Produces a flat
archive — the payload sits at the zip root (hooks/, CLAUDE.starterkit.md, install.sh, ...) —
so a Windows "Extract All" yields one folder named after the zip, with no double
nesting.

  python3 make_bundle.py [--out DIR]

Prior release zips are left untouched in dist/; only this version's own zip is
(re)written on a same-version rebuild.
"""
import argparse
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = "claude-starterkit"

# The installable payload — exactly what the installers lay down. Dev/release
# tooling (this script), VCS metadata, dist/ and .gitignore are excluded.
TOP_FILES = [
    "CLAUDE.starterkit.md", "CHANGELOG.md", "README.md",
    "INSTRUCTIONS.md", "INSTRUCTIONS-windows.md",
    "install.sh", "install.ps1",
    "statusline-command.sh", "statusline-command.ps1",
]
HOOK_DIR = "hooks"


def read_version():
    """The first released `## [x.y.z]` heading in CHANGELOG.md — `[Unreleased]`
    is skipped, so the bundle always names a real, released version."""
    with open(os.path.join(HERE, "CHANGELOG.md"), encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^##\s*\[(\d+\.\d+\.\d+)\]", line)
            if m:
                return m.group(1)
    sys.exit("no released version in CHANGELOG.md (expected a '## [x.y.z]' heading)")


def payload():
    files = list(TOP_FILES)
    for f in sorted(os.listdir(os.path.join(HERE, HOOK_DIR))):
        if f.endswith(".py"):
            files.append(f"{HOOK_DIR}/{f}")
    return files


def build(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    version = read_version()
    zip_path = os.path.join(out_dir, f"{BUNDLE}-{version}.zip")
    files = payload()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in files:
            full = os.path.join(HERE, rel)
            if not os.path.exists(full):
                sys.exit(f"missing payload file: {rel}")
            z.write(full, rel)
    size = os.path.getsize(zip_path) / 1024
    print(f"  {zip_path}")
    print(f"  {len(files)} files, {size:.0f} KB")
    return zip_path


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(HERE, "dist"))
    build(ap.parse_args().out)


if __name__ == "__main__":
    main()
