#!/bin/bash

set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd -P)/common.sh"

ps_verify_dependencies
ps_verify_build
ps_require_command curl
ps_require_command lsof

mkdir -p "$PS_STATE_DIR" "$PS_LOG_DIR"

if existing_pid="$(ps_read_pid 2>/dev/null)" && ps_pid_is_server "$existing_pid"; then
  printf 'TERRA Pixel Streaming is already running (PID %s).\n' "$existing_pid"
  "$PS_SCRIPT_DIR/check_local.sh"
  exit 0
fi

if [ -f "$PS_PID_FILE" ]; then
  rm -f -- "$PS_PID_FILE"
fi

for port in "$PS_PLAYER_PORT" "$PS_STREAMER_PORT"; do
  listeners="$(ps_port_listener_pids "$port")"
  [ -z "$listeners" ] || ps_fail "TCP port $port is already in use by PID(s): $listeners"
done

printf 'Starting localhost-only TERRA Pixel Streaming...\n'
nohup "$PS_NODE_BIN" "$PS_SERVER" \
  --config "$PS_CONFIG" \
  --infra-root "$PS_INFRA_ROOT" \
  --log-dir "$PS_LOG_DIR" \
  >> "$PS_CONSOLE_LOG" 2>&1 &
server_pid=$!
pid_temp="$PS_PID_FILE.$$"
printf '%s\n' "$server_pid" > "$pid_temp"
mv -f -- "$pid_temp" "$PS_PID_FILE"

attempt=0
while [ "$attempt" -lt 50 ]; do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    tail -n 40 "$PS_CONSOLE_LOG" >&2 || true
    rm -f -- "$PS_PID_FILE"
    ps_fail "Pixel Streaming process exited before becoming healthy"
  fi
  if /usr/bin/curl --fail --silent --max-time 1 \
      "http://127.0.0.1:${PS_PLAYER_PORT}/terra-health" >/dev/null 2>&1; then
    "$PS_SCRIPT_DIR/check_local.sh"
    printf '\nBrowser: http://127.0.0.1:%s/player.html\n' "$PS_PLAYER_PORT"
    printf 'Unreal flags: -PixelStreamingURL=ws://127.0.0.1:%s -RenderOffScreen -ForceRes -ResX=1920 -ResY=1080\n' "$PS_STREAMER_PORT"
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 0.2
done

"$PS_SCRIPT_DIR/stop_local.sh" >/dev/null 2>&1 || true
tail -n 40 "$PS_CONSOLE_LOG" >&2 || true
ps_fail "Pixel Streaming did not become healthy within 10 seconds"
