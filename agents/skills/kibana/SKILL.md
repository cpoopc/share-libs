---
name: kibana
description: Use when the task requires generic Kibana or Elasticsearch log search, export, index discovery, or connectivity checks with Lucene or KQL queries. Do not use for IVA or Nova session tracing; route those to `iva-logtracer`.
---

# kibana

Use the installed `kibana-query` CLI. Treat this skill as a routing and command-shaping layer, not as a substitute implementation.

Install once on a new machine with:

```bash
bash tools/python/libs/kibana/install.sh
```

Manual fallback:

```bash
uv tool install git+ssh://git@github.com/cpoopc/share-libs.git#subdirectory=tools/python/libs/kibana
npx skills add /path/to/share-libs --skill kibana -g -y
kibana-query init
kibana-query doctor
```

## Scope Boundaries

- Use this skill for generic Lucene or KQL searches, raw log exports, index discovery, and basic Kibana connectivity checks.
- Do not use this skill for IVA or Nova cross-component trace workflows. Use `iva-logtracer` for `sessionId`, `conversationId`, turn analysis, or diagnostic reports.
- Do not assume a `cp-tools` checkout exists. The installed CLI is the primary runtime surface.

## References

- Read `references/commands.md` for installed-command usage patterns and common query shapes.

## Workflow

1. Route the request first.
   - Use `kibana-query search` for generic log hunting.
   - Use `kibana-query export` when the user needs a saved JSON or Markdown artifact.
   - Use `kibana-query indices` when index discovery matters.
   - Use `kibana-query test` for basic connectivity validation.
   - Route IVA or Nova tracing questions to `iva-logtracer`.
2. Resolve environment scope.
   - Prefer explicit `--env lab` or `--env production` when the target environment matters.
   - Run `kibana-query doctor --env ...` when auth, env file selection, or XDG layout is unclear.
   - Run `kibana-query init` on a fresh machine before the first real query.
3. Run the narrowest command that answers the request.
   - Add `--last` whenever the user supplied a time window.
   - Add `--count` when the user only needs a count.
   - Add `--index` only when the default pattern is wrong for the target logs.
   - Prefer predefined queries such as `recent_errors`, `recent_warnings`, `exceptions`, and `slow_requests` when they match the request.
4. Validate before concluding.
   - Confirm the command completed successfully.
   - Confirm any exported file actually exists before referencing it in the response.
   - Distinguish raw log evidence from your inference.

## Constraints

- Do not assume `cp-tools` or repo-local runner scripts are available.
- Do not switch to `iva-logtracer` unless the task actually requires trace correlation across IVA or Nova components.
- Do not guess the environment when the wrong environment would materially change the result.
- Do not claim zero results prove absence without checking time window, index pattern, and query shape.
- Do not dump large raw log payloads when a concise summary answers the request.

## Validation

- Confirm `kibana-query doctor` is clean enough when configuration is in doubt.
- Confirm exported output paths exist before referencing them.
- Confirm the selected command path matches one of the cases in `references/commands.md`.
- State clearly when the result is limited by missing credentials, environment ambiguity, or a too-broad query.
