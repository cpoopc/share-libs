# grafana-report-fetching

Installable CLI for Grafana-backed report fetching, profile resolution, and daily core metrics pulls.

## Install

Recommended bootstrap from a `share-libs` checkout:

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

## Runtime Layout

By default this tool uses XDG directories:

- config: `~/.config/grafana-report-fetching/`
- cache: `~/.cache/grafana-report-fetching/`
- output: `~/.cache/grafana-report-fetching/output/`

Typical first commands:

```bash
grafana-report-fetching init
grafana-report-fetching doctor
grafana-report-fetching doctor --profile iva --real
grafana-report-fetching resolve-profile iva-prod
```

## Core Commands

```bash
grafana-report-fetching fetch --config /absolute/path/to/prod-weekly.config.yaml --section all --format json
grafana-report-fetching core-metrics-daily --day 2026-04-11
grafana-report-fetching core-metrics-daily --config /absolute/path/to/core-metrics-daily.yaml --output-dir /absolute/path/to/output
```

## Development

```bash
cd packages/grafana-report-fetching
uv sync --extra dev
pytest
python -m cptools_grafana_report_fetching.cli --help
```
