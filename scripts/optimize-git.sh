#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$ROOT_DIR/cleanup.log"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

exec > >(tee -a "$LOG_FILE") 2>&1

cd "$ROOT_DIR"
log "Starting git optimization in $ROOT_DIR"

if [[ "${1:-}" == "--strip-blobs" ]]; then
    max_size="${2:-10M}"
    log "Requested history rewrite to strip blobs larger than $max_size"
    if ! git filter-repo --help >/dev/null 2>&1; then
        log "git-filter-repo not installed. Install via: pip install git-filter-repo"
        exit 1
    fi
    log "Rewriting history to strip large blobs (this is destructive)"
    git filter-repo --strip-blobs-bigger-than "$max_size" --force
fi

git reflog expire --expire=now --all
log "Reflog expired"

git gc --aggressive --prune=now
log "Git GC complete"
