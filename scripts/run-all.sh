#!/usr/bin/env bash
# Run all 8 scenarios, 2 in parallel at a time.
#
# Credentials are read from .env (ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL,
# HTTPS_PROXY) — never hardcode them here.
#
# Usage:
#   ./scripts/run-all.sh                    # full step budgets
#   ./scripts/run-all.sh --steps 50         # override steps (validation)
#   ./scripts/run-all.sh --steps 50 -n 3    # override steps + trajectories
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

# Provider + model — auth comes from env vars
PROVIDER_ARGS=(
  --provider anthropic
  --model "${AGORA_MODEL:-rits/zai-org/glm-5-2-fp8}"
)

# Extra args passed through (e.g. --steps 50 -n 3)
EXTRA_ARGS=("$@")

SCENARIOS=(
  "scenarios/examples/pandemic.yaml"
  "scenarios/examples/market.yaml"
  "scenarios/examples/intelligence.yaml"
  "scenarios/examples/nuclear_war.yaml"
  "scenarios/examples/complexity.yaml"
  "scenarios/examples/mediterranean.yaml"
  "scenarios/examples/capitalism.yaml"
  "scenarios/examples/democracy.yaml"
)

LOGDIR="$ROOT/runs/logs"
mkdir -p "$LOGDIR"

run_pair() {
  local s1="$1" s2="$2"
  local name1 name2 log1 log2 pid1 pid2

  name1="$(basename "$s1" .yaml)"
  name2="$(basename "$s2" .yaml)"
  log1="$LOGDIR/${name1}.log"
  log2="$LOGDIR/${name2}.log"

  echo "[$(date +%H:%M:%S)] Starting: $name1 + $name2"

  uv run minimal-agora run "$s1" -n 1 "${PROVIDER_ARGS[@]}" "${EXTRA_ARGS[@]}" \
    > "$log1" 2>&1 &
  pid1=$!

  uv run minimal-agora run "$s2" -n 1 "${PROVIDER_ARGS[@]}" "${EXTRA_ARGS[@]}" \
    > "$log2" 2>&1 &
  pid2=$!

  local fail=0
  wait "$pid1" || { echo "  FAILED: $name1 (see $log1)"; fail=1; }
  wait "$pid2" || { echo "  FAILED: $name2 (see $log2)"; fail=1; }

  if [[ $fail -eq 0 ]]; then
    echo "[$(date +%H:%M:%S)] Done: $name1 + $name2"
  fi
  return $fail
}

echo "=== minimal-agora batch run ==="
echo "Model: ${AGORA_MODEL:-rits/zai-org/glm-5-2-fp8}"
echo "Extra args: ${EXTRA_ARGS[*]:-none}"
echo "Logs: $LOGDIR/"
echo ""

TOTAL_FAIL=0
for ((i=0; i<${#SCENARIOS[@]}; i+=2)); do
  run_pair "${SCENARIOS[$i]}" "${SCENARIOS[$i+1]}" || TOTAL_FAIL=1
done

echo ""
if [[ $TOTAL_FAIL -eq 0 ]]; then
  echo "=== All scenarios complete ==="
else
  echo "=== Some scenarios failed — check logs ==="
fi

echo ""
echo "Results:"
for s in "${SCENARIOS[@]}"; do
  name="$(basename "$s" .yaml)"
  # scenario names use hyphens in output dirs
  for d in runs/*/; do
    report="$d/report.txt"
    if [[ -f "$report" ]] && grep -q "$name\|$(echo "$name" | tr '_' '-')" "$d/report.json" 2>/dev/null; then
      echo "--- $name ---"
      cat "$report"
      echo ""
      break
    fi
  done
done
