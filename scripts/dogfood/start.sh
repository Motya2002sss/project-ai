#!/usr/bin/env bash
set -euo pipefail

dogfood_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dogfood_root="$(cd "$dogfood_script_dir/../.." && pwd)"
source "$dogfood_script_dir/lib.sh"

dogfood_usage() {
  cat <<'EOF'
Запускает local iPhone dogfooding в одном терминале:
  1. PostgreSQL, Ollama при необходимости и FastAPI
  2. Cloudflare Quick Tunnel
  3. Expo в LAN-режиме

Использование:
  ./scripts/dogfood/start.sh

Остановка:
  Ctrl+C — Expo, FastAPI и созданный этим запуском tunnel остановятся вместе.

Перед первым единым запуском закройте старые dogfood-терминалы через Ctrl+C.
EOF
}

if test "$#" -gt 0; then
  if test "$#" -eq 1 && { test "$1" = "--help" || test "$1" = "-h"; }; then
    dogfood_usage
    exit 0
  fi
  echo "Неизвестный аргумент: $1" >&2
  dogfood_usage >&2
  exit 2
fi

for dogfood_command in curl lsof pgrep ps; do
  if ! command -v "$dogfood_command" >/dev/null 2>&1; then
    echo "Не найдена обязательная команда: $dogfood_command" >&2
    exit 1
  fi
done

if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Порт 8000 уже занят. Остановите старый FastAPI через Ctrl+C и повторите." >&2
  exit 1
fi

if pgrep -f 'cloudflared.*tunnel.*127\.0\.0\.1:8000' >/dev/null 2>&1; then
  echo "Quick Tunnel уже запущен. Остановите его старое окно через Ctrl+C и повторите." >&2
  exit 1
fi

if lsof -nP -iTCP:8081 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Порт 8081 уже занят Expo. Остановите старое окно Expo через Ctrl+C и повторите." >&2
  exit 1
fi

dogfood_owned_pids=()
dogfood_owned_files=()
dogfood_cleanup_done=0

dogfood_cleanup() {
  local dogfood_status="$1"
  local dogfood_pid

  if test "$dogfood_cleanup_done" -eq 1; then
    exit "$dogfood_status"
  fi
  dogfood_cleanup_done=1
  trap - EXIT INT TERM

  if test "${#dogfood_owned_pids[@]}" -gt 0; then
    echo
    echo "Останавливаю dogfood stack…"
    for dogfood_pid in "${dogfood_owned_pids[@]}"; do
      if kill -0 "$dogfood_pid" 2>/dev/null; then
        kill -TERM "$dogfood_pid" 2>/dev/null || true
      fi
    done
    for dogfood_pid in "${dogfood_owned_pids[@]}"; do
      wait "$dogfood_pid" 2>/dev/null || true
    done
  fi
  if test "${#dogfood_owned_files[@]}" -gt 0; then
    for dogfood_file in "${dogfood_owned_files[@]}"; do
      rm -f "$dogfood_file"
    done
  fi

  exit "$dogfood_status"
}

trap 'dogfood_cleanup $?' EXIT
trap 'dogfood_cleanup 130' INT TERM

dogfood_start_background() {
  local dogfood_label="$1"
  shift

  "$@" > >(
    awk -v dogfood_prefix="[$dogfood_label] " \
      '{ print dogfood_prefix $0; fflush() }'
  ) 2>&1 &
  dogfood_last_pid=$!
  dogfood_owned_pids+=("$dogfood_last_pid")
}

dogfood_child_is_running() {
  local dogfood_pid="$1"
  local dogfood_state

  kill -0 "$dogfood_pid" 2>/dev/null || return 1
  dogfood_state="$(ps -p "$dogfood_pid" -o state= 2>/dev/null)" || return 1
  [[ -n "$dogfood_state" && "$dogfood_state" != *Z* ]]
}

dogfood_forget_owned_pid() {
  local dogfood_finished_pid="$1"
  local dogfood_pid
  local dogfood_live_pid_count=0
  local -a dogfood_live_pids=()

  for dogfood_pid in "${dogfood_owned_pids[@]}"; do
    if test "$dogfood_pid" != "$dogfood_finished_pid"; then
      dogfood_live_pids+=("$dogfood_pid")
      dogfood_live_pid_count=$((dogfood_live_pid_count + 1))
    fi
  done
  if test "$dogfood_live_pid_count" -eq 0; then
    dogfood_owned_pids=()
  else
    dogfood_owned_pids=("${dogfood_live_pids[@]}")
  fi
}

dogfood_wait_for_child_health() {
  local dogfood_pid="$1"
  local dogfood_url="$2"
  local dogfood_label="$3"
  local dogfood_max_attempts="$4"
  local dogfood_attempt
  local dogfood_child_status

  for ((dogfood_attempt = 1; dogfood_attempt <= dogfood_max_attempts; dogfood_attempt += 1)); do
    if curl --silent --fail --max-time 3 "$dogfood_url" >/dev/null 2>&1; then
      return 0
    fi
    if ! dogfood_child_is_running "$dogfood_pid"; then
      dogfood_child_status=0
      wait "$dogfood_pid" || dogfood_child_status=$?
      dogfood_forget_owned_pid "$dogfood_pid"
      echo "$dogfood_label завершился во время запуска (код $dogfood_child_status)." >&2
      return 1
    fi
    sleep 1
  done

  echo "$dogfood_label не стал доступен вовремя: $dogfood_url" >&2
  return 1
}

echo "Запускаю FastAPI и локальные зависимости…"
dogfood_start_background backend bash "$dogfood_script_dir/start-backend.sh"
dogfood_backend_pid="$dogfood_last_pid"
dogfood_wait_for_child_health \
  "$dogfood_backend_pid" \
  "http://127.0.0.1:8000/health" \
  "FastAPI" \
  180

echo "FastAPI готов. Запускаю Cloudflare Quick Tunnel…"
dogfood_tunnel_ready_file="$(
  mktemp "${TMPDIR:-/tmp}/ai-life-planner-tunnel-ready.XXXXXX"
)"
dogfood_owned_files+=("$dogfood_tunnel_ready_file")
dogfood_tunnel_ready=0
for dogfood_tunnel_attempt in 1 2; do
  : >"$dogfood_tunnel_ready_file"
  dogfood_start_background \
    tunnel \
    env DOGFOOD_TUNNEL_READY_FILE="$dogfood_tunnel_ready_file" \
    bash "$dogfood_script_dir/start-tunnel.sh"
  dogfood_tunnel_pid="$dogfood_last_pid"
  dogfood_tunnel_reaped=0

  for ((dogfood_attempt = 1; dogfood_attempt <= 180; dogfood_attempt += 1)); do
    dogfood_tunnel_url="$(<"$dogfood_tunnel_ready_file")"
    if [[ "$dogfood_tunnel_url" =~ ^https://([a-z0-9]|[a-z0-9][a-z0-9-]*[a-z0-9])\.trycloudflare\.com$ ]] && \
      dogfood_child_is_running "$dogfood_tunnel_pid" && \
      curl --silent --fail --max-time 5 "$dogfood_tunnel_url/health" >/dev/null 2>&1 && \
      dogfood_child_is_running "$dogfood_tunnel_pid"; then
      dogfood_tunnel_ready=1
      break
    fi
    if ! dogfood_child_is_running "$dogfood_tunnel_pid"; then
      dogfood_tunnel_status=0
      wait "$dogfood_tunnel_pid" || dogfood_tunnel_status=$?
      dogfood_forget_owned_pid "$dogfood_tunnel_pid"
      dogfood_tunnel_reaped=1
      echo "Quick Tunnel завершился во время запуска (код $dogfood_tunnel_status)." >&2
      break
    fi
    sleep 1
  done

  if test "$dogfood_tunnel_ready" -eq 1; then
    break
  fi

  if test "$dogfood_tunnel_reaped" -eq 0; then
    if dogfood_child_is_running "$dogfood_tunnel_pid"; then
      kill -TERM "$dogfood_tunnel_pid" 2>/dev/null || true
    fi
    wait "$dogfood_tunnel_pid" 2>/dev/null || true
    dogfood_forget_owned_pid "$dogfood_tunnel_pid"
  fi
  if test "$dogfood_tunnel_attempt" -eq 1; then
    echo "Первый Quick Tunnel не готов. Запрашиваю новый…"
  fi
done

if test "$dogfood_tunnel_ready" -ne 1; then
  echo "Quick Tunnel не стал доступен вовремя." >&2
  exit 1
fi

echo "Backend и tunnel готовы. Запускаю Expo; QR появится ниже."
echo "Для остановки всего stack нажмите Ctrl+C."
bash "$dogfood_script_dir/start-mobile.sh"
