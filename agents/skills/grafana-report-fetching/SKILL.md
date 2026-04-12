---
name: grafana-report-fetching
description: "Use when a task needs Grafana-backed data extraction, profile resolution, config-driven metrics fetches, or daily core metrics pulls via the installed `grafana-report-fetching` CLI."
---

# Grafana Report Fetching

Use the installed `grafana-report-fetching` CLI. Treat this skill as a routing and command-shaping layer, not as a substitute implementation.

Install once on a new machine with:

```bash
bash packages/grafana-report-fetching/install.sh
```

Manual fallback:

```bash
uv tool install git+ssh://git@github.com/cpoopc/share-libs.git#subdirectory=packages/grafana-report-fetching
npx skills add https://github.com/cpoopc/share-libs --skill grafana-report-fetching -g -y
grafana-report-fetching init
grafana-report-fetching doctor
```

## Scope Boundaries

- Use this skill for Grafana profile resolution, doctor/init flows, config-driven report fetches, and daily core metrics pulls.
- Do not assume `cp-tools`, `apps/data-reports`, or repo-local scripts are available.
- Prefer the installed CLI even when a local compatibility wrapper exists.
- Do not use this skill for Kibana or Elasticsearch log search; route those to `kibana`.

## References

- Read `references/commands.md` for installed-command usage patterns.

## Terms

- `source_id`: the canonical runtime identifier used by `GrafanaClient.from_env(source_id)`
- `profile`: a human-facing environment choice such as `iva-prod`, `rc-int`, or `default`
- `alias`: an alternate user-facing name that resolves to the same canonical `source_id`

Profiles and aliases are a CLI/runtime convenience. The underlying contract is still `GRAFANA_<SOURCE_ID>_*`.

## Workflow

1. Route the request first.
   - Use `grafana-report-fetching resolve-profile` when the user names a profile or alias and you need the canonical `source_id`.
   - Use `grafana-report-fetching doctor` when env selection, alias resolution, or credentials are unclear.
   - Use `grafana-report-fetching fetch` for config-driven multi-section Grafana pulls.
   - Use `grafana-report-fetching core-metrics-daily` for the standard daily IVA metrics report.
2. Resolve environment scope.
   - Run `grafana-report-fetching init` on a fresh machine before the first real command.
   - Use explicit `--env production` or `--env lab` when environment ambiguity matters.
   - Use `doctor --real` when you need an actual `/api/health` connectivity check.
3. Run the narrowest command that answers the request.
   - Prefer `resolve-profile` over hand-maintaining alias maps.
   - Pass an explicit `--config` when the workflow depends on repo-local report YAML.
4. Validate before concluding.
   - Confirm the selected profile normalized to the expected `source_id`.
   - Confirm claimed output files exist.
   - Distinguish missing credentials from network or query failures.

## Constraints

- Do not assume a `cp-tools` checkout exists.
- Do not overwrite existing `GRAFANA_<SOURCE_ID>_*` values by hand; let the CLI perform any supported fallback mapping.
- Do not guess the canonical `source_id` when `resolve-profile` can tell you.
- Do not report a generic Grafana failure before distinguishing missing credentials, network or DNS blockage, and query errors.

## Validation

- Confirm `grafana-report-fetching doctor` is clean enough when configuration is in doubt.
- Confirm `resolve-profile` returns the expected profile and canonical `source_id`.
- Confirm the fetch or core-metrics command exits successfully.
- Confirm any claimed output file path exists before citing it.
