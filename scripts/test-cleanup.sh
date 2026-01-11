#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "Checking consolidated output directory..."
if [[ ! -d "$ROOT_DIR/output" ]]; then
    echo "Missing consolidated output directory: $ROOT_DIR/output" >&2
    exit 1
fi

mapfile -t EXTRA_OUTPUT_DIRS < <(
    find "$ROOT_DIR" -type d \
        \( -iname '*output*' -o -iname 'out' -o -iname 'outputs' -o -iname 'results' -o -iname 'result' \) \
        -not -path "$ROOT_DIR/output" \
        -not -path "$ROOT_DIR/output/*" \
        -not -path "$ROOT_DIR/.git/*" \
        -not -path '*/node_modules/*'
)

if [[ ${#EXTRA_OUTPUT_DIRS[@]} -gt 0 ]]; then
    echo "Found extra output-like directories:" >&2
    printf '%s\n' "${EXTRA_OUTPUT_DIRS[@]}" >&2
    exit 1
fi

echo "Checking README sections..."
grep -E "(Project Overview|Structure|Usage|Output)" README.md >/dev/null

echo "Checking git integrity..."
git fsck --full

echo "Repository size:"
du -sh .

echo "Git object stats:"
git count-objects -v

echo "All cleanup checks passed."
