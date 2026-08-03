#!/bin/bash

set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd -P)/common.sh"

dependencies_only=false
if [ "${1:-}" = "--dependencies-only" ]; then
  dependencies_only=true
elif [ "$#" -ne 0 ]; then
  ps_fail "Usage: $0 [--dependencies-only]"
fi

ps_verify_dependencies
ps_verify_build
"$PS_NODE_BIN" --check "$PS_SERVER" >/dev/null

if [ "$dependencies_only" = true ]; then
  printf 'Dependency/build check passed: UE5.8 %s, release %s, Node %s.\n' \
    "$PS_EXPECTED_COMMIT" "$PS_EXPECTED_RELEASE" "$PS_EXPECTED_NODE"
  exit 0
fi

ps_require_command curl
ps_require_command lsof

server_pid="$(ps_read_pid 2>/dev/null)" || ps_fail "Pixel Streaming is not running: no valid PID file"
ps_pid_is_server "$server_pid" || ps_fail "PID file does not point to the TERRA localhost server"

health_file="$PS_STATE_DIR/health.$$.json"
cleanup_health() {
  rm -f -- "$health_file"
}
trap cleanup_health EXIT HUP INT TERM

/usr/bin/curl --fail --silent --show-error --max-time 2 \
  "http://127.0.0.1:${PS_PLAYER_PORT}/terra-health" > "$health_file"

health_counts="$("$PS_NODE_BIN" - "$health_file" <<'NODE'
const fs = require('node:fs');
const health = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const expected = {
  ok: true,
  bind_address: '127.0.0.1',
  player_port: 8080,
  streamer_port: 8888,
  max_players: 1,
  ice_servers: 0,
  stun: false,
  turn: false,
  sfu: false,
  rest_api: false
};
for (const [key, value] of Object.entries(expected)) {
  if (health[key] !== value) {
    throw new Error(`Unsafe health value ${key}=${JSON.stringify(health[key])}; expected ${JSON.stringify(value)}`);
  }
}
if (!Number.isInteger(health.streamers) || !Number.isInteger(health.players)) {
  throw new Error('Health counts are invalid');
}
if (health.players > 1) {
  throw new Error(`Player limit violated: ${health.players}`);
}
process.stdout.write(`${health.streamers} ${health.players}\n`);
NODE
)"
streamer_count="${health_counts%% *}"
player_count="${health_counts#* }"

for port in "$PS_PLAYER_PORT" "$PS_STREAMER_PORT"; do
  listener_lines="$(/usr/sbin/lsof -nP -a -p "$server_pid" -iTCP:"$port" -sTCP:LISTEN -Fn 2>/dev/null || true)"
  [ -n "$listener_lines" ] || ps_fail "PID $server_pid is not listening on expected TCP port $port"
  if ! printf '%s\n' "$listener_lines" | grep -F "n127.0.0.1:$port" >/dev/null 2>&1; then
    ps_fail "Port $port is not bound exactly to 127.0.0.1"
  fi
  if printf '%s\n' "$listener_lines" | grep -E "n(\*|\[::\]|0\.0\.0\.0):$port" >/dev/null 2>&1; then
    ps_fail "Public/wildcard listener detected on port $port"
  fi
done

for forbidden_port in 8889 3478 19303; do
  if /usr/sbin/lsof -nP -a -p "$server_pid" -iTCP:"$forbidden_port" -sTCP:LISTEN >/dev/null 2>&1; then
    ps_fail "Forbidden SFU/STUN/TURN listener detected on port $forbidden_port"
  fi
  if /usr/sbin/lsof -nP -a -p "$server_pid" -iUDP:"$forbidden_port" >/dev/null 2>&1; then
    ps_fail "Forbidden SFU/STUN/TURN UDP socket detected on port $forbidden_port"
  fi
done

printf 'Healthy: PID %s; browser 127.0.0.1:%s; streamer 127.0.0.1:%s; streamers=%s; players=%s/1.\n' \
  "$server_pid" "$PS_PLAYER_PORT" "$PS_STREAMER_PORT" "$streamer_count" "$player_count"
