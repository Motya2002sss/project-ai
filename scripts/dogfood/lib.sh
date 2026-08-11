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

dogfood_quick_tunnel_resolve_target() {
  local tunnel_url="$1"
  local tunnel_label
  local tunnel_host
  local tunnel_ip

  if [[ ! "$tunnel_url" =~ ^https://([a-z0-9]|[a-z0-9][a-z0-9-]*[a-z0-9])\.trycloudflare\.com($|/) ]] || \
    ! command -v dig >/dev/null 2>&1; then
    return 1
  fi

  tunnel_label="${BASH_REMATCH[1]}"
  tunnel_host="${tunnel_label}.trycloudflare.com"
  tunnel_ip="$(
    dig +time=2 +tries=1 +short @1.1.1.1 "$tunnel_host" A 2>/dev/null |
      awk -F . '
        NF == 4 &&
        $1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ &&
        $3 ~ /^[0-9]+$/ && $4 ~ /^[0-9]+$/ {
          print
          exit
        }
      '
  )"
  test -n "$tunnel_ip" || return 1

  printf '%s:443:%s\n' "$tunnel_host" "$tunnel_ip"
}

dogfood_curl_health() {
  local health_url="$1"
  local max_time="${2:-10}"
  local resolve_target

  if curl --silent --fail --max-time "$max_time" "$health_url" >/dev/null 2>&1; then
    return 0
  fi

  resolve_target="$(dogfood_quick_tunnel_resolve_target "$health_url")" || return 1

  curl --silent --fail --max-time "$max_time" \
    --resolve "$resolve_target" \
    "$health_url" >/dev/null 2>&1
}

dogfood_wait_for_health() {
  local health_url="$1"
  local max_attempts="$2"
  local retry_delay="$3"
  local attempt

  for ((attempt = 1; attempt <= max_attempts; attempt += 1)); do
    if dogfood_curl_health "$health_url" 10; then
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
    if dogfood_curl_health "$health_url" 10 && \
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

dogfood_connected_vpn_name() {
  awk -F '"' '
    /\(Connected\)/ {
      if (NF >= 3 && length($2) > 0) {
        print $2
      } else {
        print "VPN"
      }
      found = 1
      exit
    }
    END { if (!found) exit 1 }
  '
}
