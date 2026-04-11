# Output Files

Use this reference after `run_trace.sh` finishes.

## Output Directory

Trace output is written under:

```text
apps/iva_logtracer/output/iva_session/{YYYYMMDD}_{sessionId}-{conversationId}/
```

Do not guess the directory name. Confirm it exists before running follow-up commands.

## Common Files

| File | Purpose |
|---|---|
| `combine.log` | Chronologically merged logs across traced components |
| `summary.json` | Session metadata, discovered IDs, and log counts |
| `{component}_message.log` | Per-component logs for focused inspection |
| `ai_analysis/` | Preprocessed files for AI-assisted analysis |

## How To Read Them

- Start with `summary.json` to confirm the trace resolved the expected IDs.
- Use `combine.log` to reconstruct the cross-service timeline.
- Use `{component}_message.log` when the issue appears isolated to one component.
- Use `ai_analysis/` only when a downstream analysis step needs structured inputs.

## Common Signals

| Pattern | Meaning |
|---|---|
| `level:ERROR` | Explicit errors |
| `timeout` | Service timeout or slow dependency |
| `exception` | Unhandled exception |
| `latency > 5000` | Slow response path |
| `retry` | Transient instability or repeated attempts |
