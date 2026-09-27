#!/usr/bin/env bash
# Cross-compiles the installer for every release platform into OUT_DIR, with a .sha256 next to each
# binary, and copies the two bootstrap scripts beside them. These files are the release assets.
#
#   scripts/build-release.sh VERSION OUT_DIR
set -euo pipefail

version="${1:?usage: scripts/build-release.sh VERSION OUT_DIR}"
out="${2:?usage: scripts/build-release.sh VERSION OUT_DIR}"
cd "$(dirname "$0")/.."
mkdir -p "$out"
if command -v sha256sum >/dev/null 2>&1; then sha=(sha256sum); else sha=(shasum -a 256); fi

# asset-os:asset-arch:GOOS:GOARCH
targets=(
  linux:x64:linux:amd64
  linux:arm64:linux:arm64
  macos:x64:darwin:amd64
  macos:arm64:darwin:arm64
  windows:x64:windows:amd64
  windows:arm64:windows:arm64
)

for t in "${targets[@]}"; do
  IFS=: read -r os arch goos goarch <<<"$t"
  name="starterkit-install-$os-$arch"
  [ "$os" = windows ] && name="$name.exe"
  CGO_ENABLED=0 GOOS="$goos" GOARCH="$goarch" go build -trimpath \
    -ldflags "-s -w -X main.version=$version" -o "$out/$name" ./cmd/starterkit-install
  (cd "$out" && "${sha[@]}" "$name" > "$name.sha256")
  echo "built $out/$name"
done

cp install.sh install.ps1 "$out/"
