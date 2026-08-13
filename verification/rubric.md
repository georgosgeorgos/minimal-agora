# Evaluator Rubric

Use this rubric after implementation and before final acceptance.

## Verification Commands

```bash
# Full verification
uv run pytest tests/ -v && uv run ruff check src/ tests/

# Quick smoke test
uv run pytest tests/ -v -x  # stop on first failure

# Single test
uv run pytest tests/test_models.py -v -k "test_name"
```

## Scoring

| Category | Question | Score (0-2) | Notes |
| --- | --- | --- | --- |
| Correctness | Does the implemented behavior match the requested feature? |  |  |
| Verification | Did `pytest` and `ruff` both pass with evidence? |  |  |
| Scope discipline | Did the session stay inside the chosen feature scope? |  |  |
| Reliability | Does `./init.sh` succeed after the changes? |  |  |
| Maintainability | Is the code and documentation clear enough for the next session? |  |  |
| Handoff readiness | Are progress.md, features.json, and handoff.md up to date? |  |  |

## Worldsim-Specific Checks

| Check | Pass? | Notes |
| --- | --- | --- |
| Both example scenarios load without validation errors |  |  |
| Workspace setup creates correct directory structure |  |  |
| Agent prompts include rules and wildcard instructions |  |  |
| Entity state merges correctly into shared world state |  |  |
| Outcome classification returns correct labels |  |  |

## Verdict

- Accept
- Revise
- Block

## Required Follow-Up

- Missing evidence:
- Required fixes:
- Next review trigger:
