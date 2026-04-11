---
name: iva-logtracer
description: Use when the user asks to trace an IVA or Nova `sessionId` or `conversationId`, analyze a saved `apps/iva_logtracer/output/iva_session/...` directory, explain turn latency or filler-to-agent silence, confirm KB or generic tool usage, or generate a diagnostic trace report across assistant_runtime, agent_service, NCA, AIG, GMG, cprc_srs, or cprc_sgs. Do not use for generic Kibana-only log searches with no trace workflow; route those to `kibana`.
---

# IVA Log Tracer

Trace IVA or Nova sessions with the repository runners under `apps/iva_logtracer/` without skipping routing, artifact verification, or output contract checks.

## References

- Read `references/commands.md` for supported commands and argument patterns.
- Read `references/report-contract.md` when the user expects a diagnostic report or you need the default output shape.
- Read `references/id-correlation.md` when you need to map IDs across components.
- Read `references/output-files.md` before interpreting saved trace output.
- Read `references/debugging-playbooks.md` when the user is asking for root cause analysis instead of a raw trace.
- Read `assets/session-summary-template.md` before delivering a trace summary.

## Workflow

1. Route the request before running anything.
   - Classify the input as `sessionId`, `conversationId`, saved trace directory, turn-level sequencing question, KB audit, generic tool audit, or broad debugging symptom.
   - Route generic Kibana-only requests to `kibana`.
   - Default to `scripts/diagnostic_report.py` unless the user explicitly wants raw logs, one narrow fact, or a specialized audit.
   - Use `scripts/kb_tool_audit.py` for KB-usage or KB-backed wrong-answer questions.
   - Use `scripts/toolcall_audit.py` for generic turn-level tool usage or tool/answer contradiction checks.
2. Resolve execution scope.
   - Confirm `lab` vs `production` when the target environment is materially ambiguous.
   - Confirm a time window only when the user gave a broad symptom without a stable ID or saved trace directory.
   - Change into `"$CP_TOOLS_HOME"` before running repository commands.
3. Run the trace or analyzer with explicit inputs.
   - Use `./apps/iva_logtracer/runners/run_trace.sh` for `sessionId` or `conversationId`.
   - Use `./apps/iva_logtracer/runners/run_turn.sh` only after a saved trace directory exists.
   - Add `--save-json` whenever you will run turn analysis, `toolcall_audit.py`, or follow-up tooling that needs `*_trace.json`.
   - Prefer explicit `--env`, `--last`, `--loaders`, and `--save-json` flags over implied defaults.
4. Verify artifacts before forming conclusions.
   - Confirm the output directory exists and contains the files required by the selected workflow.
   - Inspect `summary.json`, `combine.log`, and the relevant `{component}_message.log` files before concluding anything.
   - Escalate from the default report to turn analysis only when chronology or event sequencing still matters after reading the saved trace.
5. Deliver the right output contract.
   - For the default path, follow `references/report-contract.md` and treat the diagnostic document as the main deliverable.
   - For manual summaries, reuse `assets/session-summary-template.md` instead of improvising the report shape.
   - State the environment, input artifact, commands run, output directory, key findings, confidence level, and unresolved gaps.

## Constraints

- Do not guess the environment when the wrong target would change the result materially.
- Do not claim cross-component correlation without confirming the IDs in output files.
- Do not run `run_turn.sh` against a guessed or nonexistent session directory.
- Do not dump raw logs when a concise summary answers the request.
- Do not treat generic log search as an `iva-logtracer` task when `kibana` is the better fit.
- Do not deliver a free-form chat summary when a diagnostic document is expected.
- Do not present inferred root causes as confirmed facts; label them as `confirmed`, `likely`, or `unknown`.

## Validation

- Confirm the command completed successfully.
- Confirm the output directory or files referenced in the response actually exist.
- Confirm any stated error, timeout, retry, or latency issue is backed by trace output.
- Confirm the diagnostic document follows `references/report-contract.md`, including `Action Summary` before the deeper sections when the default report path is used.
- State clearly when the trace is incomplete because inputs, environment, or time range were missing.
