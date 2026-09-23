# OpenRouter DeepSeek 3 × 20 live runs — 2026-09-23

## Setup

Two existing examples were run with three trajectories and a 20-step budget each. Both used OpenRouter's `deepseek/deepseek-v4.1-flash` model with reasoning disabled. The API key came from the local environment at runtime; it was not copied into this repository or passed as a CLI argument.

The intelligence run started through the existing LiteLLM route while the named provider was being added:

```bash
uv run minimal-agora run scenarios/examples/intelligence.yaml -n 3 --steps 20 \
  --provider litellm --model openrouter/deepseek/deepseek-v4.1-flash \
  --disable-reasoning -o runs/openrouter-deepseek-2026-09-23-3x20-verified
```

The Mediterranean run exercised the new first-class CLI route:

```bash
uv run minimal-agora run scenarios/examples/mediterranean.yaml -n 3 --steps 20 \
  --provider openrouter -o runs/openrouter-deepseek-2026-09-23-3x20-verified
```

## Results

| Scenario | Saved steps | Outcome counts | Actor proposals saved | Resolver parse failures | State validation |
|---|---:|---|---:|---:|---|
| Intelligence | 20 × 3 | stagnation: 3 | 234 / 240 | 7 | none |
| Mediterranean | 20 × 3 | persian_dominance: 2; balance_of_power: 1 | 294 / 300 | 9 | 127 warnings for newly introduced fields |

Both commands exited 0. Each trajectory saved 20 contiguous full step records, 20 resolution records, a final state, and an aggregate `report.json`. The intelligence particle filter saved 8 of 9 scheduled resampling score files at steps 4, 9, and 14 (zero-based); one malformed critic response used the fallback score. The first score check produced different totals across all three particles, confirming that API responses were used. No particle duplication was triggered in this 20-step run.

The engine logged six missing actor proposals in each scenario. It saved a resolution for every step, but some resolver outputs failed JSON parsing and were replaced by fallback resolutions. Mediterranean's 127 validation warnings all concerned new state fields; no original-field type mismatch was logged. The engine currently applies warned deltas; [issue #73](https://github.com/georgosgeorgos/minimal-agora/issues/73) tracks schema policy, and [issue #76](https://github.com/georgosgeorgos/minimal-agora/issues/76) tracks retry and visibility for malformed model output. These outcomes are evidence of live execution, not robust outcome probabilities or fully validated domain trajectories.

The run directories under `runs/openrouter-deepseek-2026-09-23-3x20-verified/` are ignored by Git and contain the detailed step and report artifacts. Recorded step calls used 2,426,830 input and 314,958 output tokens across both scenarios; resampling critic calls are outside the saved step token totals.

## Verification

- `./init.sh`: 431 tests passed; Ruff clean. Five existing warnings come from degenerate statistical test data.
- `uv run ruff format --check src/ tests/`: passed.
- `uv run mypy src/minimal_agora/ --ignore-missing-imports`: passed.
- PR #75 CI: lint, Python 3.12 tests, Python 3.13 tests, and typecheck passed.
