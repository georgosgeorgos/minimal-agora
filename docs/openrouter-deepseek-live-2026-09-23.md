# OpenRouter DeepSeek live validation — 2026-09-23

## Setup and scope

- Provider: LiteLLM routed to OpenRouter; model: `openrouter/deepseek/deepseek-v4.1-flash`.
- Credentials: `OPENROUTER_API_KEY` supplied from the local environment; no key was copied into this repository or passed on the command line.
- Run size: one trajectory, three steps per existing example; output under `runs/openrouter-deepseek-2026-09-23-three-step/` (ignored by Git).
- Command pattern: `minimal-agora run scenarios/examples/<name>.yaml -n 1 --steps 3 --provider litellm --model openrouter/deepseek/deepseek-v4.1-flash --disable-reasoning -o runs/openrouter-deepseek-2026-09-23-three-step`.
- These short runs validate the live provider path and artifact production. Their one-trajectory outcomes do not estimate outcome probabilities or validate long-term scenario behavior.

## Results

| Scenario | Steps | Actor proposals | Outcome | State validation warnings |
|---|---:|---:|---|---|
| intelligence | 3 | 12 | stagnation | none |
| mediterranean | 3 | 15 | balance_of_power | none |
| pandemic | 3 | 9 | controlled | none |
| market | 3 | 15 | oligopoly | none |
| complexity | 3 | 9 | minimal | none |
| democracy | 3 | 9 | autocracy_persists | none |
| capitalism | 3 | 9 | command_economy | three step-level warning events |
| nuclear_war | 3 | 12 | stable_deterrence | none |

All eight commands exited successfully. Each run saved three full step records, three resolution records, a final state, and `report.json`. Across the runs there were 90 actor proposals, 16 critique records, and 24 resolution records. Recorded usage was 219,284 input and 35,402 output tokens. At the [OpenRouter listed model rates](https://openrouter.ai/deepseek/deepseek-v4.1-flash) on this date, this corresponds to about $0.047 before provider-specific billing and caching effects; it is an estimate, not a billing record.

The first one-step intelligence smoke run used the provider's default 2,048-token output limit and lost three of four actor proposals because generation reached that limit. `--disable-reasoning` sent `reasoning: {enabled: false}` to OpenRouter. A repeat one-step run produced all four actor proposals, one critique, a resolution, and a report. The eight three-step runs above used that setting.

Capitalism's resolved state deltas contained strings for `world.global_trade_volume` (initially integer) and `economic_concepts.banking_system` (initially boolean), plus new `monetary_systems` fields. The engine logged schema warnings but applied the changes. Treat that scenario's state and outcome as a provider-path check, not a domain-valid result. [Issue #73](https://github.com/georgosgeorgos/minimal-agora/issues/73) tracks state-delta enforcement.

## Verification

- `./init.sh`: dependency sync, Ruff, and 422 tests passed; five pre-existing degenerate-statistics warnings.
- `uv run pytest tests/ -q`: 422 passed.
- `uv run ruff check src/ tests/`, `uv run ruff format --check src/ tests/`, and `uv run mypy src/minimal_agora/ --ignore-missing-imports`: passed.
