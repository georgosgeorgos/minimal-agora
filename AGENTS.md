# AGENTS.md

This repository is designed for long-running coding-agent work. The goal is not
to maximize raw code output. The goal is to leave the repo in a state where the
next session can continue without guessing.

## Repository Structure

| Path | Purpose |
|------|---------|
| `AGENTS.md` | Agent workflow, working rules, session protocol |
| `CLAUDE.md` | Symlink to AGENTS.md |
| `init.sh` | Standard startup: install, verify, optionally run |
| `harness-findings.md` | Harness engineering reference (CLI, isolation, patterns) |
| `quality.md` | Quality standards and guidelines |
| `state/features.json` | Source of truth for feature state and verification |
| `state/progress.md` | Session log and current verified status |
| `session/checklist.md` | Session checklist |
| `session/handoff.md` | Session handoff notes |
| `verification/rubric.md` | Evaluator rubric for acceptance review |

## Startup Workflow

Before writing code:

1. Confirm the working directory with `pwd`.
2. Read `state/progress.md` for the latest verified state and next step.
3. Read `state/features.json` and choose the highest-priority unfinished feature.
4. Review recent commits with `git log --oneline -5`.
5. Run `./init.sh`.
6. Run the required smoke or end-to-end verification before starting new work.

If baseline verification is already failing, fix that first. Do not stack new
feature work on top of a broken starting state.

## Working Rules

- Work on one feature at a time.
- Do not mark a feature complete just because code was added.
- Keep changes within the selected feature scope unless a blocker forces a
  narrow supporting fix.
- Do not silently change verification rules during implementation.
- Prefer durable repo artifacts over chat summaries.
- Commit after each atomic change. Do not batch unrelated changes into one commit.

## Definition Of Done

A feature is done only when all of the following are true:

- the target behavior is implemented
- the required verification actually ran
- evidence is recorded in `state/features.json` or `state/progress.md`
- the repository remains restartable from the standard startup path

## End Of Session

Before ending a session:

1. Update `state/progress.md`.
2. Update `state/features.json`.
3. Record any unresolved risk or blocker.
4. Commit with a descriptive message once the work is in a safe state.
5. Leave the repo clean enough for the next session to run `./init.sh`
   immediately.
