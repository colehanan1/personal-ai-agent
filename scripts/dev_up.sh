#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
PID_DIR="${ROOT_DIR}/logs/dev_up"
VLLM_PID_FILE="${PID_DIR}/vllm.pid"
VLLM_LOG_FILE="${PID_DIR}/vllm.log"

log() {
  echo "[dev_up] $*"
}

warn() {
  echo "[dev_up] WARN: $*" >&2
}

die() {
  echo "[dev_up] ERROR: $*" >&2
  exit 1
}

python_bin() {
  if command -v python >/dev/null 2>&1; then
    echo "python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return 0
  fi
  return 1
}

ensure_conda_env() {
  if [ -z "${CONDA_DEFAULT_ENV:-}" ]; then
    die "Conda environment not active. Run: conda activate milton"
  fi
  if [ "${CONDA_DEFAULT_ENV}" != "milton" ]; then
    die "Conda env '${CONDA_DEFAULT_ENV}' active. Run: conda activate milton"
  fi
}

validate_env() {
  if [ ! -f "${ENV_FILE}" ]; then
    die ".env not found. Run: cp .env.example .env"
  fi

  local py
  py="$(python_bin)" || die "Python not found in PATH."
  "${py}" -m milton_orchestrator.env_validation \
    --env-file "${ENV_FILE}" \
    --repo-root "${ROOT_DIR}"
}

load_env_file() {
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
}

detect_docker_cmd() {
  if ! command -v docker >/dev/null 2>&1; then
    echo ""
    return 1
  fi

  if docker info >/dev/null 2>&1; then
    echo "docker"
    return 0
  fi

  if command -v sudo >/dev/null 2>&1; then
    if sudo -n docker info >/dev/null 2>&1; then
      echo "sudo docker"
      return 0
    fi
  fi

  echo ""
  return 1
}

start_weaviate() {
  if [ ! -f "${ROOT_DIR}/docker-compose.yml" ]; then
    warn "docker-compose.yml not found; skipping Weaviate."
    return 0
  fi

  local docker_cmd
  docker_cmd="$(detect_docker_cmd || true)"
  if [ -z "${docker_cmd}" ]; then
    die "Docker not available. Install Docker or run: sudo docker compose up -d"
  fi

  log "Starting Weaviate (${docker_cmd} compose up -d)..."
  if ! ${docker_cmd} compose up -d; then
    die "Docker compose up failed."
  fi
}

is_llm_up() {
  local base_url="$1"
  local py
  py="$(python_bin)" || return 1
  LLM_URL="${base_url}" "${py}" - <<'PY'
import os
import sys
import urllib.request

url = os.environ["LLM_URL"].rstrip("/") + "/v1/models"
try:
    with urllib.request.urlopen(url, timeout=2) as resp:
        sys.exit(0 if resp.status in (200, 401) else 1)
except Exception:
    sys.exit(1)
PY
}

start_vllm() {
  if [ ! -f "${ROOT_DIR}/scripts/start_vllm.py" ]; then
    warn "scripts/start_vllm.py not found."
    warn "Next step: add a vLLM start script or run your LLM and set LLM_API_URL."
    return 0
  fi

  mkdir -p "${PID_DIR}"

  if [ -f "${VLLM_PID_FILE}" ]; then
    local pid
    pid="$(cat "${VLLM_PID_FILE}")"
    if kill -0 "${pid}" >/dev/null 2>&1; then
      log "vLLM already running (PID ${pid})."
      return 0
    fi
    rm -f "${VLLM_PID_FILE}"
  fi

  local llm_url="${LLM_API_URL:-http://localhost:8000}"
  if is_llm_up "${llm_url}"; then
    log "LLM already reachable at ${llm_url}."
    return 0
  fi

  local py
  py="$(python_bin)" || die "Python not found in PATH."

  log "Starting vLLM..."
  nohup "${py}" scripts/start_vllm.py >"${VLLM_LOG_FILE}" 2>&1 &
  local pid=$!
  echo "${pid}" > "${VLLM_PID_FILE}"
  log "vLLM started with PID ${pid} (logs: ${VLLM_LOG_FILE})"
}

main() {
  cd "${ROOT_DIR}"
  ensure_conda_env
  validate_env
  load_env_file
  start_weaviate
  start_vllm
  log "Done. Next: python scripts/healthcheck.py"
}

main "$@"
