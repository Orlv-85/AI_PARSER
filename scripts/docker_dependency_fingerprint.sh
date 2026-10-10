#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT_DIR"

FILES="
build/Dockerfile
build/Dockerfile.runtime
build/requirements.txt
build/requirements-dev.txt
pyproject.toml
"

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

hash_stream() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print substr($1, 1, 16)}'
  else
    shasum -a 256 "$1" | awk '{print substr($1, 1, 16)}'
  fi
}

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT INT TERM

for path in $FILES; do
  if [ ! -f "$path" ]; then
    echo "Missing dependency fingerprint input: $path" >&2
    exit 1
  fi
  printf '%s  %s\n' "$(hash_file "$path")" "$path" >>"$tmp_file"
done

hash_stream "$tmp_file"
