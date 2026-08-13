# Clean State Checklist

- [x] The standard startup path still works (`./init.sh`).
- [x] The standard verification path still runs (`uv run pytest tests/ -v && uv run ruff check src/ tests/`).
- [x] Current progress is recorded in the progress log.
- [x] Feature state reflects what is actually passing versus unverified.
- [x] No half-finished step is left undocumented.
- [x] The next session can continue without manual repair.
