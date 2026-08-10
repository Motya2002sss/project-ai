#!/usr/bin/env bash

dogfood_read_env_value() {
  local key="$1"
  local env_file="$2"

  test -f "$env_file" || return 1

  awk -v wanted="$key" '
    index($0, wanted "=") == 1 {
      sub(/^[^=]*=/, "")
      value = $0
      found = 1
    }
    END {
      if (!found) exit 1
      printf "%s", value
    }
  ' "$env_file"
}

dogfood_extract_tunnel_url() {
  awk '
    {
      if (match($0, /https:\/\/([a-z0-9]|[a-z0-9][a-z0-9-]*[a-z0-9])\.trycloudflare\.com/)) {
        candidate = substr($0, RSTART, RLENGTH)
        suffix = substr($0, RSTART + RLENGTH, 1)
        if (suffix !~ /[A-Za-z0-9.-]/) {
          print candidate
          found = 1
          exit
        }
      }
    }
    END { if (!found) exit 1 }
  '
}

dogfood_write_mobile_env() {
  local tunnel_url="$1"
  local env_file="$2"
  local env_dir
  local temp_file

  if [[ ! "$tunnel_url" =~ ^https://([a-z0-9]|[a-z0-9][a-z0-9-]*[a-z0-9])\.trycloudflare\.com$ ]]; then
    return 1
  fi

  env_dir="$(dirname "$env_file")"
  test -d "$env_dir" || return 1

  temp_file="$(mktemp "$env_dir/.env.dogfood.XXXXXX")" || return 1
  chmod 600 "$temp_file"
  if ! printf 'EXPO_PUBLIC_API_BASE_URL=%s\n' "$tunnel_url" >"$temp_file"; then
    rm -f "$temp_file"
    return 1
  fi
  mv "$temp_file" "$env_file"
}

dogfood_write_curl_auth_config() {
  local token="$1"
  local config_file="$2"

  if [[ ! "$token" =~ ^[-A-Za-z0-9._~+/=]+$ ]]; then
    return 1
  fi

  (
    umask 077
    printf 'header = "Authorization: Bearer %s"\n' "$token" >"$config_file"
  )
}

dogfood_wait_for_health() {
  local health_url="$1"
  local max_attempts="$2"
  local retry_delay="$3"
  local attempt

  for ((attempt = 1; attempt <= max_attempts; attempt += 1)); do
    if curl --silent --fail --max-time 10 "$health_url" >/dev/null 2>&1; then
      return 0
    fi
    if test "$attempt" -lt "$max_attempts"; then
      sleep "$retry_delay"
    fi
  done

  return 1
}

dogfood_wait_for_health_while_process_alive() {
  local health_url="$1"
  local child_pid="$2"
  local max_attempts="$3"
  local retry_delay="$4"
  local attempt
  local child_status

  for ((attempt = 1; attempt <= max_attempts; attempt += 1)); do
    if curl --silent --fail --max-time 10 "$health_url" >/dev/null 2>&1 && \
      kill -0 "$child_pid" 2>/dev/null; then
      return 0
    fi

    if ! kill -0 "$child_pid" 2>/dev/null; then
      child_status=0
      wait "$child_pid" || child_status=$?
      if test "$child_status" -eq 0; then
        return 1
      fi
      return "$child_status"
    fi

    if test "$attempt" -lt "$max_attempts"; then
      sleep "$retry_delay"
    fi
  done

  return 1
}

dogfood_warm_ollama() {
  local base_url="${1%/}"
  local model="$2"
  local payload

  if [[ ! "$model" =~ ^[A-Za-z0-9._:-]+$ ]]; then
    return 1
  fi

  payload="$(printf '{"model":"%s","think":false,"stream":false,"keep_alive":"24h","messages":[{"role":"user","content":"ready"}],"options":{"num_predict":1,"temperature":0}}' "$model")"
  curl --silent --fail --max-time 60 \
    -H 'Content-Type: application/json' \
    --data "$payload" \
    "$base_url/api/chat" >/dev/null
}
