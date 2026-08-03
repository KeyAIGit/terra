#!/bin/bash

set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd -P)/common.sh"

if ! server_pid="$(ps_read_pid 2>/dev/null)"; then
  printf 'TERRA Pixel Streaming is not running (no valid PID file).\n'
  exit 0
fi

if ! kill -0 "$server_pid" 2>/dev/null; then
  rm -f -- "$PS_PID_FILE"
  printf 'Removed stale Pixel Streaming PID file.\n'
  exit 0
fi

ps_pid_is_server "$server_pid" || ps_fail "PID $server_pid does not belong to the TERRA localhost server; refusing to signal it"

kill -TERM "$server_pid"
attempt=0
while kill -0 "$server_pid" 2>/dev/null && [ "$attempt" -lt 50 ]; do
  attempt=$((attempt + 1))
  sleep 0.1
done

if kill -0 "$server_pid" 2>/dev/null; then
  kill -KILL "$server_pid"
fi
rm -f -- "$PS_PID_FILE"
printf 'TERRA Pixel Streaming stopped (PID %s).\n' "$server_pid"
