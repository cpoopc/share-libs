# grafana-report-fetching Commands

## Fresh Machine

```bash
grafana-report-fetching init
grafana-report-fetching doctor
grafana-report-fetching doctor --profile iva --real
```

## Resolve a Human Alias

```bash
grafana-report-fetching resolve-profile iva-prod
grafana-report-fetching resolve-profile rc-int --format text
```

## Config-Driven Fetch

```bash
grafana-report-fetching fetch --config /absolute/path/to/prod-weekly.config.yaml --section all --format json
grafana-report-fetching fetch --config /absolute/path/to/prod-weekly.config.yaml --section call_health --list-panels
grafana-report-fetching fetch --config /absolute/path/to/prod-weekly.config.yaml --output /absolute/path/to/report.md
```

## Daily Core Metrics

```bash
grafana-report-fetching core-metrics-daily --day 2026-04-11
grafana-report-fetching core-metrics-daily --config /absolute/path/to/core-metrics-daily.yaml --output-dir /absolute/path/to/output
```
