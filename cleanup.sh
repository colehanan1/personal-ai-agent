#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$ROOT_DIR/cleanup.log"
DEST_DIR="$ROOT_DIR/output"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

hash_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

exec > >(tee -a "$LOG_FILE") 2>&1

log "Starting cleanup in $ROOT_DIR"
mkdir -p "$DEST_DIR"

mapfile -t CANDIDATE_DIRS < <(
    find "$ROOT_DIR" -type d \
        \( -iname '*output*' -o -iname 'outputs' -o -iname 'out' -o -iname 'results' -o -iname 'result' \) \
        -not -path "$DEST_DIR" \
        -not -path "$DEST_DIR/*" \
        -not -path "$ROOT_DIR/.git/*" \
        -not -path '*/node_modules/*'
)

MERGE_DIRS=()
for dir in "${CANDIDATE_DIRS[@]}"; do
    if [[ "$dir" == "$DEST_DIR" ]]; then
        continue
    fi
    if [[ "$dir" == "$DEST_DIR/"* ]]; then
        continue
    fi
    MERGE_DIRS+=("$dir")
done

if [[ ${#MERGE_DIRS[@]} -eq 0 ]]; then
    log "No additional output directories found to merge."
else
    for SRC_DIR in "${MERGE_DIRS[@]}"; do
        log "Merging $SRC_DIR into $DEST_DIR"
        while IFS= read -r -d '' file; do
            rel_path="${file#"$SRC_DIR"/}"
            dest_path="$DEST_DIR/$rel_path"
            mkdir -p "$(dirname "$dest_path")"

            if [[ ! -e "$dest_path" ]]; then
                mv "$file" "$dest_path"
                continue
            fi

            if cmp -s "$file" "$dest_path"; then
                log "Duplicate file content found; removing $file"
                rm -f "$file"
                continue
            fi

            dest_dir="$(dirname "$dest_path")"
            base_name="$(basename "$dest_path")"
            name="$base_name"
            ext=""
            if [[ "$base_name" == *.* ]]; then
                name="${base_name%.*}"
                ext=".${base_name##*.}"
            fi

            i=1
            while :; do
                candidate="$dest_dir/${name}_dup${i}${ext}"
                if [[ ! -e "$candidate" ]]; then
                    log "Name collision; moving $file to $candidate"
                    mv "$file" "$candidate"
                    break
                fi
                i=$((i + 1))
            done
        done < <(find "$SRC_DIR" -type f -print0)

        find "$SRC_DIR" -type d -empty -delete
    done
fi

log "Deduplicating files in $DEST_DIR"
declare -A SEEN_HASHES=()
while IFS= read -r -d '' file; do
    file_hash="$(hash_file "$file")"
    if [[ -n "${SEEN_HASHES[$file_hash]+x}" ]]; then
        log "Removing duplicate content: $file (same as ${SEEN_HASHES[$file_hash]})"
        rm -f "$file"
    else
        SEEN_HASHES[$file_hash]="$file"
    fi
done < <(find "$DEST_DIR" -type f -print0)

find "$DEST_DIR" -type d -empty -delete

log "Cleanup complete."
