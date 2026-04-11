# Commands

Run all repository commands from `"$CP_TOOLS_HOME"`.

## Primary Trace Command

Use `run_trace.sh` for any request that starts from `sessionId` or `conversationId`.

```bash
cd "$CP_TOOLS_HOME"
./apps/iva_logtracer/runners/run_trace.sh s-abc123xyz --env production
./apps/iva_logtracer/runners/run_trace.sh s-abc123xyz --env production --last 48h
./apps/iva_logtracer/runners/run_trace.sh s-abc123xyz --env production --loaders assistant_runtime nca aig
./apps/iva_logtracer/runners/run_trace.sh 123e4567-e89b-12d3-a456-426614174000 --env production
./apps/iva_logtracer/runners/run_trace.sh s-abc123xyz --env production --save-json
```

## Turn Analysis

Use `run_turn.sh` only after `run_trace.sh --save-json` has created a saved session output directory with `*_trace.json` files.

```bash
cd "$CP_TOOLS_HOME"
./apps/iva_logtracer/runners/run_trace.sh s-xxx --env production --save-json
./apps/iva_logtracer/runners/run_turn.sh ./apps/iva_logtracer/output/iva_session/s-xxx-yyy/
./apps/iva_logtracer/runners/run_turn.sh ./apps/iva_logtracer/output/iva_session/s-xxx-yyy/ --html
./apps/iva_logtracer/runners/run_turn.sh ./apps/iva_logtracer/output/iva_session/s-xxx-yyy/ --format markdown
```

## KB Audit

Use the skill-local script when you need a deterministic answer to "did AIR call KB, what did KB return, and did the final answer contradict it?"

```bash
cd "$CP_TOOLS_HOME"
python3 agents/skills/iva-logtracer/scripts/kb_tool_audit.py \
  ./apps/iva_logtracer/output/iva_session/20260323_s-xxx-yyy/
```

## Generic Tool Audit

Use the skill-local script when you need a turn-level summary of generic server/client tool calls across one or more saved trace directories, including heuristic contradiction checks between tool results and the final answer. The trace directories must include `*_trace.json`, so run `run_trace.sh --save-json` first.

```bash
cd "$CP_TOOLS_HOME"
./apps/iva_logtracer/runners/run_trace.sh s-xxx --env production --save-json
python3 agents/skills/iva-logtracer/scripts/toolcall_audit.py \
  ./apps/iva_logtracer/output/iva_session/20260323_s-xxx-yyy/

python3 agents/skills/iva-logtracer/scripts/toolcall_audit.py \
  ./apps/iva_logtracer/output/iva_session/20260323_s-xxx-yyy/ \
  ./apps/iva_logtracer/output/iva_session/20260323_s-yyy-zzz/ \
  --format json
```

## Diagnostic Report

Use the skill-local script as the default output path for trace investigations. The report now starts with an `Action Summary`, then a `Final Verdict`, `Session Scorecard`, `Turn Summary Matrix`, and `Expanded Timelines` before the deeper evidence sections. Read `references/report-contract.md` for the expected section meanings and attribution rules. The trace directories must include `*_trace.json`, so run `run_trace.sh --save-json` first.

```bash
cd "$CP_TOOLS_HOME"
./apps/iva_logtracer/runners/run_trace.sh s-xxx --env production --save-json
python3 agents/skills/iva-logtracer/scripts/diagnostic_report.py \
  ./apps/iva_logtracer/output/iva_session/20260323_s-xxx-yyy/

python3 agents/skills/iva-logtracer/scripts/diagnostic_report.py \
  ./apps/iva_logtracer/output/iva_session/20260323_s-xxx-yyy/ \
  --reported-symptom "AIR answered wrong" \
  --lang zh \
  --format json \
  --output /tmp/iva-diagnostic.json
```

## Command Selection

- Start with `run_trace.sh` for session correlation, component coverage, and initial debugging.
- Add `--last` when the user gives a time window or the default range risks missing the event.
- Add `--loaders` when the user only cares about specific components such as `aig`, `gmg`, or `cprc_srs`.
- Add `--save-json` when the trace output may need turn analysis, tool auditing, or deeper offline review.
- Use `scripts/diagnostic_report.py` by default when the expected output is a standard investigation document.
- Add `--reported-symptom` when the user gave a complaint such as "AIR answered wrong" so the report can explicitly map symptom to evidence.
- Add `--lang zh|en` when you want the markdown report localized for humans. Keep `json` output for stable machine-readable fields.
- The diagnostic document should include final verdict, diagnostic snapshot, basic judgment, AI diagnosis report, component coverage, Nova/start-conversation, assistant configuration, correlation IDs, speech linkage, turn diagnostics, and recommended next actions whenever the logs contain those signals.
- Use `run_turn.sh` only when the user asks for turn-level analysis or timeline output, and only after `--save-json`.
- Use `scripts/toolcall_audit.py` when the user wants a normalized view of tool usage across client/server tools or across multiple sampled traces.
- Use `scripts/kb_tool_audit.py` when the bug report is specifically about KB usage or KB-backed wrong answers.

## Common Command Patterns

### Trace a problematic session

```bash
cd "$CP_TOOLS_HOME"
./apps/iva_logtracer/runners/run_trace.sh s-problematic-session --env production
```

### Check likely errors in trace output

```bash
grep -i "error\\|exception\\|timeout" apps/iva_logtracer/output/iva_session/*/combine.log
grep -i "timeout\\|failed" apps/iva_logtracer/output/iva_session/*/nca_message.log
```

### Focus on LLM-related services

```bash
cd "$CP_TOOLS_HOME"
./apps/iva_logtracer/runners/run_trace.sh s-xxx --env production --loaders aig gmg
grep -i "error\\|timeout" apps/iva_logtracer/output/iva_session/*/gmg_message.log
```

### Focus on speech services

```bash
cd "$CP_TOOLS_HOME"
./apps/iva_logtracer/runners/run_trace.sh s-xxx --env production --loaders assistant_runtime cprc_srs cprc_sgs
grep -i "error\\|confidence" apps/iva_logtracer/output/iva_session/*/cprc_srs_message.log
```

## Prerequisites

The runners expect credentials in `apps/iva_logtracer/.env.{env}`.

- `KIBANA_URL`
- `KIBANA_USERNAME`
- `KIBANA_PASSWORD`

Supported environments:

- `.env.lab`
- `.env.production`
