#!/bin/bash

set -euo pipefail

PS_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
TERRA_PROJECT_ROOT="$(cd "$PS_SCRIPT_DIR/../.." && pwd -P)"
PS_INFRA_ROOT="$TERRA_PROJECT_ROOT/Tools/PixelStreamingInfrastructure-UE5.8"
PS_NODE_ROOT="$TERRA_PROJECT_ROOT/Tools/.runtime/node-v22.14.0-darwin-arm64"
PS_NODE_BIN="$PS_NODE_ROOT/bin/node"
PS_NPM_BIN="$PS_NODE_ROOT/bin/npm"
PS_CONFIG="$PS_SCRIPT_DIR/localhost-config.json"
PS_LOCK="$PS_SCRIPT_DIR/dependency-lock.json"
PS_SERVER="$PS_SCRIPT_DIR/localhost-server.cjs"
PS_STATE_DIR="$TERRA_PROJECT_ROOT/Saved/PixelStreaming"
PS_PID_FILE="$PS_STATE_DIR/localhost.pid"
PS_CONSOLE_LOG="$PS_STATE_DIR/localhost-console.log"
PS_LOG_DIR="$PS_STATE_DIR/logs"
PS_EXPECTED_COMMIT="1d1e515e97c026d1f376f329d5f005f58eabb234"
PS_EXPECTED_BRANCH="UE5.8"
PS_EXPECTED_REPOSITORY="https://github.com/EpicGames/PixelStreamingInfrastructure.git"
PS_EXPECTED_RELEASE="0.1.0"
PS_EXPECTED_NODE="v22.14.0"
PS_PLAYER_PORT="8080"
PS_STREAMER_PORT="8888"

ps_fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

ps_require_file() {
  [ -f "$1" ] || ps_fail "Required file is missing: $1"
}

ps_require_command() {
  command -v "$1" >/dev/null 2>&1 || ps_fail "Required command is unavailable: $1"
}

ps_read_pid() {
  [ -f "$PS_PID_FILE" ] || return 1
  local pid
  pid="$(tr -d '[:space:]' < "$PS_PID_FILE")"
  case "$pid" in
    ''|*[!0-9]*) return 1 ;;
  esac
  printf '%s\n' "$pid"
}

ps_pid_is_server() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null || return 1
  ps -p "$pid" -o command= 2>/dev/null | grep -F -- "$PS_SERVER" >/dev/null 2>&1
}

ps_port_listener_pids() {
  /usr/sbin/lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null || true
}

ps_verify_dependencies() {
  ps_require_command git
  ps_require_file "$PS_LOCK"
  ps_require_file "$PS_CONFIG"
  ps_require_file "$PS_SERVER"
  [ -d "$PS_INFRA_ROOT/.git" ] || ps_fail "Official Pixel Streaming checkout is missing: $PS_INFRA_ROOT"
  ps_require_file "$PS_INFRA_ROOT/RELEASE_VERSION"
  ps_require_file "$PS_INFRA_ROOT/NODE_VERSION"
  ps_require_file "$PS_INFRA_ROOT/package-lock.json"
  ps_require_file "$PS_NODE_BIN"

  local actual_commit actual_branch actual_remote actual_release actual_node declared_node
  actual_commit="$(git -C "$PS_INFRA_ROOT" rev-parse HEAD)"
  actual_branch="$(git -C "$PS_INFRA_ROOT" rev-parse --abbrev-ref HEAD)"
  actual_remote="$(git -C "$PS_INFRA_ROOT" remote get-url origin)"
  actual_release="$(tr -d '[:space:]' < "$PS_INFRA_ROOT/RELEASE_VERSION")"
  declared_node="$(tr -d '[:space:]' < "$PS_INFRA_ROOT/NODE_VERSION")"
  actual_node="$("$PS_NODE_BIN" --version)"

  [ "$actual_commit" = "$PS_EXPECTED_COMMIT" ] || ps_fail "Pixel Streaming commit drift: $actual_commit"
  case "$actual_branch" in
    "$PS_EXPECTED_BRANCH"|HEAD) ;;
    *) ps_fail "Pixel Streaming branch drift: $actual_branch" ;;
  esac
  [ "$actual_remote" = "$PS_EXPECTED_REPOSITORY" ] || ps_fail "Pixel Streaming origin drift: $actual_remote"
  [ "$actual_release" = "$PS_EXPECTED_RELEASE" ] || ps_fail "Pixel Streaming release drift: $actual_release"
  [ "$declared_node" = "$PS_EXPECTED_NODE" ] || ps_fail "Infrastructure NODE_VERSION drift: $declared_node"
  [ "$actual_node" = "$PS_EXPECTED_NODE" ] || ps_fail "Local Node runtime drift: $actual_node"

  "$PS_NODE_BIN" - "$PS_LOCK" <<'NODE'
const fs = require('node:fs');
const lock = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const expected = {
  schema_version: 1,
  repository: 'https://github.com/EpicGames/PixelStreamingInfrastructure.git',
  branch: 'UE5.8',
  commit: '1d1e515e97c026d1f376f329d5f005f58eabb234',
  release: '0.1.0',
  checkout: 'Tools/PixelStreamingInfrastructure-UE5.8'
};
for (const [key, value] of Object.entries(expected)) {
  if (lock[key] !== value) throw new Error(`dependency-lock drift: ${key}`);
}
if (lock.node?.version !== 'v22.14.0'
    || lock.node?.platform !== 'darwin-arm64'
    || lock.node?.runtime !== 'Tools/.runtime/node-v22.14.0-darwin-arm64'
    || lock.node?.archive_sha256 !== 'e9404633bc02a5162c5c573b1e2490f5fb44648345d64a958b17e325729a5e42') {
  throw new Error('dependency-lock drift: node');
}
NODE

  if [ -n "$(git -C "$PS_INFRA_ROOT" status --porcelain --untracked-files=no)" ]; then
    ps_fail "Tracked files in the official dependency checkout were modified"
  fi
}

ps_verify_build() {
  ps_require_file "$PS_INFRA_ROOT/Common/dist/cjs/pixelstreamingcommon.js"
  ps_require_file "$PS_INFRA_ROOT/Signalling/dist/cjs/pixelstreamingsignalling.js"
  ps_require_file "$PS_INFRA_ROOT/SignallingWebServer/dist/index.js"
  ps_require_file "$PS_INFRA_ROOT/SignallingWebServer/www/player.html"
  ps_require_file "$PS_INFRA_ROOT/SignallingWebServer/www/player.js"
}
