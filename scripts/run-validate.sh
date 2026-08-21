#!/usr/bin/env bash
# Quick validation: 50 steps per scenario, all 8, 2 at a time.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/run-all.sh" --steps 50
