#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${STATE_DIR:-$HOME/.local/state/milton}"
PID_DIR="${PID_DIR:-$STATE_DIR/logs/dev_up}"
VLLM_PID_FILE="${PID_DIR}/vllm.pid"

log() {
  echo "[dev_down] $*"
}

warn() {
  echo "[dev_down] WARN: $*" >&2
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

stop_from_pid() {
  local name="$1"
  local pid_file="$2"
  local match="$3"

  if [ ! -f "${pid_file}" ]; then
    warn "${name} pid file not found (${pid_file})."
    return 0
  fi

  local pid
  pid="$(cat "${pid_file}")"

  if ! kill -0 "${pid}" >/dev/null 2>&1; then
    warn "${name} not running (PID ${pid})."
    rm -f "${pid_file}"
    return 0
  fi

  local cmdline=""
  if [ -r "/proc/${pid}/cmdline" ]; then
    cmdline="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)"
  fi

  if [ -n "${match}" ] && [[ "${cmdline}" != *"${match}"* ]]; then
    warn "${name} pid ${pid} does not match expected command; skipping."
    return 0
  fi

  log "Stopping ${name} (PID ${pid})..."
  kill "${pid}" || true

  for _ in $(seq 1 10); do
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      rm -f "${pid_file}"
      log "${name} stopped."
      return 0
    fi
    sleep 1
  done

  warn "${name} did not exit; sending SIGKILL."
  kill -9 "${pid}" || true
  rm -f "${pid_file}"
}

stop_weaviate() {
  if [ ! -f "${ROOT_DIR}/docker-compose.yml" ]; then
    warn "docker-compose.yml not found; skipping Weaviate."
    return 0
  fi

  local docker_cmd
  docker_cmd="$(detect_docker_cmd || true)"
  if [ -z "${docker_cmd}" ]; then
    warn "Docker not available; skipping docker compose down."
    return 0
  fi

  log "Stopping Weaviate (${docker_cmd} compose down)..."
  if ! ${docker_cmd} compose down; then
    warn "Docker compose down failed."
  fi
}

main() {
  cd "${ROOT_DIR}"
  stop_from_pid "vLLM" "${VLLM_PID_FILE}" "scripts/start_vllm.py"
  stop_weaviate
}

main "$@"
