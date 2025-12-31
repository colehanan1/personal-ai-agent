#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs/services"

log() {
  echo "[stop_all] $*"
}

warn() {
  echo "[stop_all] WARN: $*" >&2
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

  local cmdline
  cmdline="$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)"

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

main() {
  stop_from_pid "Dashboard" "${LOG_DIR}/dashboard.log.pid" "milton-dashboard"
stop_from_pid "API server" "${LOG_DIR}/api_server.log.pid" "scripts/start_api_server.py"
stop_from_pid "vLLM" "${LOG_DIR}/vllm.log.pid" "scripts/start_vllm.py"

  local docker_cmd=""
  if [ -n "${DOCKER_CMD:-}" ]; then
    docker_cmd="${DOCKER_CMD}"
  elif [ "${DOCKER_SUDO:-}" = "1" ]; then
    docker_cmd="sudo docker"
  fi

  if command -v docker >/dev/null 2>&1; then
    if [ -z "${docker_cmd}" ] && docker info >/dev/null 2>&1; then
      docker_cmd="docker"
    elif [ -z "${docker_cmd}" ] && command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
      docker_cmd="sudo docker"
    fi

    if [ -n "${docker_cmd}" ]; then
      log "Stopping Docker services (${docker_cmd} compose down)..."
      if ! ${docker_cmd} compose down; then
        warn "Docker compose down failed."
      fi
    else
      warn "Docker not accessible. Run: sudo docker compose down"
    fi
  else
    warn "Docker not found; skipping docker compose down."
  fi
}

main "$@"
