#!/bin/sh
# Installs the Claude Code starterkit: downloads the installer binary for this OS and CPU from the
# latest GitHub release, checks its SHA-256, and runs it. Every flag is passed through to it
# (see --help). Safe to re-run.
#
#   curl -fsSL https://github.com/MatLomax/claude-starterkit/releases/latest/download/install.sh | sh
#   curl -fsSL https://github.com/MatLomax/claude-starterkit/releases/latest/download/install.sh | sh -s -- --no-worklog
#
# STARTERKIT_VERSION=X.Y.Z installs that release instead of the latest.
set -eu

REPO="MatLomax/claude-starterkit"

die() { echo "install.sh: $*" >&2; exit 1; }

case "$(uname -s)" in
  Linux)  os=linux ;;
  Darwin) os=macos ;;
  *) die "unsupported OS $(uname -s); on Windows run install.ps1 (see the README)" ;;
esac
case "$(uname -m)" in
  x86_64|amd64)  arch=x64 ;;
  aarch64|arm64) arch=arm64 ;;
  *) die "no prebuilt installer for $(uname -s)/$(uname -m)" ;;
esac
asset="starterkit-install-$os-$arch"

if [ -n "${STARTERKIT_VERSION:-}" ]; then
  base="https://github.com/$REPO/releases/download/v${STARTERKIT_VERSION#v}"
else
  base="https://github.com/$REPO/releases/latest/download"
fi
# STARTERKIT_BASE_URL points at another copy of the release assets (a test server or a local
# directory as file:///...).
base="${STARTERKIT_BASE_URL:-$base}"

if command -v curl >/dev/null 2>&1; then
  fetch() { curl -fsSL -o "$2" "$1"; }
elif command -v wget >/dev/null 2>&1; then
  fetch() { wget -q -O "$2" "$1"; }
else
  die "needs curl or wget"
fi
if command -v sha256sum >/dev/null 2>&1; then
  sha256() { sha256sum "$1" | cut -d' ' -f1; }
elif command -v shasum >/dev/null 2>&1; then
  sha256() { shasum -a 256 "$1" | cut -d' ' -f1; }
else
  die "needs sha256sum or shasum to verify the download"
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT INT TERM

fetch "$base/$asset" "$tmp/$asset" || die "download failed: $base/$asset"
fetch "$base/$asset.sha256" "$tmp/$asset.sha256" || die "download failed: $base/$asset.sha256"
want="$(cut -d' ' -f1 < "$tmp/$asset.sha256")"
got="$(sha256 "$tmp/$asset")"
[ -n "$want" ] && [ "$want" = "$got" ] || die "checksum mismatch for $asset (expected $want, got $got)"
chmod +x "$tmp/$asset"

# Piped into sh, this script's stdin is the pipe, not the keyboard. Give the installer the terminal
# so its prompts work; with no terminal it runs non-interactively.
set +e
if [ -t 0 ]; then
  "$tmp/$asset" "$@"
elif (exec </dev/tty) 2>/dev/null; then
  "$tmp/$asset" "$@" </dev/tty
else
  "$tmp/$asset" "$@"
fi
status=$?
exit "$status"
