#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "==> Working directory: $PWD"

echo "==> Syncing dependencies"
uv sync --group dev

echo "==> Running lint check"
uv run ruff check src/ tests/

echo "==> Running test suite"
uv run pytest tests/ -v

echo "==> Checking claude CLI availability"
if command -v claude &> /dev/null; then
  echo "    claude CLI found: $(command -v claude)"
else
  echo "    WARNING: claude CLI not found — agent invocation will fail"
  echo "    Install Claude Code: https://docs.anthropic.com/en/docs/claude-code"
fi

echo "==> Baseline verification complete"
echo ""
echo "To run a simulation:"
echo "  uv run minimal-agora run scenarios/examples/intelligence.yaml -n 3"
echo "  uv run minimal-agora run scenarios/examples/mediterranean.yaml -n 3 -m population"
