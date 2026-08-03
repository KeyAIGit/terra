#!/bin/bash

set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd -P)/common.sh"

ps_verify_dependencies
export PATH="$PS_NODE_ROOT/bin:$PATH"

printf 'Installing exact npm dependency graph with %s...\n' "$(node --version)"
(cd "$PS_INFRA_ROOT" && npm ci)

printf 'Building official UE5.8 signalling server and frontend...\n'
(cd "$PS_INFRA_ROOT" && npm run build:all:cjs)

ps_verify_build
printf 'Pixel Streaming localhost dependency build is ready. No service was started.\n'
