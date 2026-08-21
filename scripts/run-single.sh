#!/usr/bin/env bash
# Run a single scenario. Credentials from .env (env vars).
#
# Usage:
#   ./scripts/run-single.sh scenarios/examples/intelligence.yaml
#   ./scripts/run-single.sh scenarios/examples/intelligence.yaml --steps 50 -n 3
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <scenario.yaml> [extra args...]"
  exit 1
fi

SCENARIO="$1"
shift

uv run minimal-agora run "$SCENARIO" -n 1 \
  --provider anthropic \
  --model "${AGORA_MODEL:-rits/zai-org/glm-5-2-fp8}" \
  "$@"
