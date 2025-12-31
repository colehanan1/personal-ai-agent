#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs/services"

mkdir -p "${LOG_DIR}"

log() {
  echo "[start_all] $*"
}

warn() {
  echo "[start_all] WARN: $*" >&2
}

ensure_conda() {
  if command -v conda >/dev/null 2>&1; then
    return 0
  fi

  if [ -f "${HOME}/miniconda3/etc/profile.d/conda.sh" ]; then
    # shellcheck disable=SC1090
    source "${HOME}/miniconda3/etc/profile.d/conda.sh"
    return 0
  fi

  if [ -f "${HOME}/anaconda3/etc/profile.d/conda.sh" ]; then
    # shellcheck disable=SC1090
    source "${HOME}/anaconda3/etc/profile.d/conda.sh"
    return 0
  fi

  warn "Conda not found. Install Miniconda/Anaconda or update this script."
  return 1
}

is_up() {
  local url="$1"
  local code
  code="$(curl -s -o /dev/null -w "%{http_code}" "${url}" || true)"
  if [ "${code}" = "200" ] || [ "${code}" = "401" ]; then
    return 0
  fi
  return 1
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local max_seconds="$3"

  log "Waiting for ${name} (${url})..."
  for _ in $(seq 1 "${max_seconds}"); do
    if is_up "${url}"; then
      log "${name} is up."
      return 0
    fi
    sleep 1
  done

  warn "${name} did not become ready within ${max_seconds}s."
  return 1
}

start_background() {
  local name="$1"
  local cmd="$2"
  local log_file="$3"

  log "Starting ${name}..."
  nohup bash -c "${cmd}" >"${log_file}" 2>&1 &
  local pid=$!
  echo "${pid}" > "${log_file}.pid"
  log "${name} started with PID ${pid} (logs: ${log_file})"
}

main() {
  cd "${ROOT_DIR}"

  if ! ensure_conda; then
    exit 1
  fi

  if command -v docker >/dev/null 2>&1; then
    log "Ensuring Weaviate is running (docker compose up -d)"
    if ! docker compose up -d; then
      warn "Docker compose failed. Weaviate may be down."
    fi
  else
    warn "Docker not found. Skipping Weaviate startup."
  fi

  if is_up "http://localhost:8000/v1/models"; then
    log "vLLM already running on port 8000."
  else
    start_background "vLLM" \
      "cd '${ROOT_DIR}' && conda run -n milton python scripts/start_vllm.py" \
      "${LOG_DIR}/vllm.log"
  fi

  if is_up "http://localhost:8001/api/system-state"; then
    log "API server already running on port 8001."
  else
    start_background "API server" \
      "cd '${ROOT_DIR}' && conda run -n milton python scripts/start_api_server.py" \
      "${LOG_DIR}/api_server.log"
  fi

  if is_up "http://localhost:3000"; then
    log "Dashboard already running on port 3000."
  else
    if ! command -v npm >/dev/null 2>&1; then
      warn "npm not found. Install Node.js 18+ to run the dashboard."
    else
      if [ ! -d "${ROOT_DIR}/milton-dashboard/node_modules" ]; then
        log "Installing dashboard dependencies..."
        (cd "${ROOT_DIR}/milton-dashboard" && npm install)
      fi
      start_background "Dashboard" \
        "cd '${ROOT_DIR}/milton-dashboard' && npm run dev" \
        "${LOG_DIR}/dashboard.log"
    fi
  fi

  wait_for_url "vLLM" "http://localhost:8000/v1/models" 180 || true
  wait_for_url "API server" "http://localhost:8001/api/system-state" 60 || true
  wait_for_url "Dashboard" "http://localhost:3000" 30 || true

  log "Done. Open http://localhost:3000"
}

main "$@"
