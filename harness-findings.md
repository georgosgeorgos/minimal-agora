# Harness Engineering with Claude Code CLI

## Agent Isolation

Agents spawned separately have no shared context. Each sees only its prompt and the filesystem. Cross-agent communication is always explicit and mediated by the orchestrator.

The one shared surface is the **filesystem** — use `--allowedTools` to prevent write conflicts, or git worktrees for parallel writers.

## Non-Interactive Mode

`claude -p` runs Claude as a subprocess — no interactive session, no human prompts.

```bash
claude -p "Review src/auth.py for bugs"
```

## Custom System Prompts

```bash
# Replace entirely
claude -p --system-prompt "You are a code reviewer." "Review src/"

# Append to default
claude -p --append-system-prompt "Respond in bullet points." "Review src/"
```

## Output Formats

| Format | Flag | Use case |
|--------|------|----------|
| text | `--output-format text` | Plain text (default) |
| json | `--output-format json` | Full metadata + `result` field |
| stream-json | `--output-format stream-json` | Realtime streaming chunks |

```bash
claude -p --output-format json "Say hello" | jq -r '.result'
```

JSON output includes: `result`, `is_error`, `total_cost_usd`, `usage`, `stop_reason`, `num_turns`.

## Structured Output

Force the model to return typed data:

```bash
claude -p --output-format json \
  --json-schema '{"type":"object","properties":{"bugs":{"type":"array"}},"required":["bugs"]}' \
  "Find bugs in src/"
```

## Tool and Permission Control

```bash
claude -p \
  --permission-mode bypassPermissions \
  --allowedTools "Read Bash(grep *)" \
  --max-turns 10 \
  "Find all TODO comments"
```

| Mode | Behavior |
|------|----------|
| bypassPermissions | Auto-approve everything |
| auto | Auto-approve safe, prompt risky |
| acceptEdits | Auto-approve reads/edits |
| dontAsk | Skip anything needing approval |

## Verification Loop

The CLI has no built-in stop criteria. The harness owns the control flow.

```bash
MAX_RETRIES=3
attempt=0

while [ $attempt -lt $MAX_RETRIES ]; do
  claude -p --output-format json \
    --permission-mode bypassPermissions \
    --allowedTools "Read Edit" \
    --max-turns 5 \
    "Fix the type errors in src/utils.ts" > /dev/null

  if npx tsc --noEmit 2>&1; then
    echo "Passed."
    break
  fi

  attempt=$((attempt + 1))
done
```

Pattern: **agent acts** → **harness verifies** (tests, linter, type checker) → **loop or stop**.

## Best Practices

1. **Least privilege** — each agent gets only the tools it needs via `--allowedTools`
2. **Bound everything** — always set `--max-turns`, timeouts, and retry limits
3. **Verify externally** — run `tsc`, `pytest`, `grep`; don't ask the model to self-check
4. **Structured output** — use `--json-schema`, don't regex-parse natural language
5. **One agent, one job** — small focused prompts outperform multi-task prompts
6. **Idempotent agents** — retrying a failed agent shouldn't corrupt state
7. **Harness decides, model executes** — control flow lives in your script, not the prompt
8. **Log everything** — capture cost, tokens, duration, full JSON per call
9. **Handle failures** — empty results, API errors, and timeouts are all distinct cases
10. **Pin the model** — use a specific model version to avoid behavior drift

## Isolated Multi-Agent Harness

```bash
# Reviewer — read-only, structured output
review=$(claude -p --output-format json \
  --system-prompt "You are a code reviewer. Report bugs as JSON." \
  --allowedTools "Read" \
  --permission-mode bypassPermissions \
  "Review src/ for bugs" | jq -r '.result')

# Writer — separate context, only sees reviewer output you forward
echo "$review" | claude -p \
  --system-prompt "You are a code fixer. Fix only what is described." \
  --allowedTools "Read Edit" \
  --permission-mode bypassPermissions \
  "Fix these issues"
```
