# cptools-kibana

Installable Kibana or Elasticsearch query CLI for generic log search, export, index discovery, and connectivity checks.

## Install

Recommended bootstrap from a `share-libs` checkout:

```bash
bash tools/python/libs/kibana/install.sh
```

From a local checkout this installs the CLI in editable mode, so the installed command follows the current clone. Use `--release-cli` when you need to validate the packaged install path instead.

Manual fallback:

```bash
uv tool install --force --editable /path/to/share-libs/tools/python/libs/kibana
uv tool install --force git+ssh://git@github.com/cpoopc/share-libs.git#subdirectory=tools/python/libs/kibana
npx skills add https://github.com/cpoopc/share-libs --skill kibana -g -y
kibana-query init
kibana-query doctor
```

## Runtime Layout

By default the CLI uses XDG directories:

- config: `~/.config/kibana-query/`
- cache: `~/.cache/kibana-query/`

Typical first commands:

```bash
kibana-query init
kibana-query doctor
kibana-query test --env production
```

## Core Commands

```bash
kibana-query search 'level:ERROR' --env production --last 1h
kibana-query export 'trace_id:abc123' --env production --last 24h --format json --output ./trace.json
kibana-query indices '*logs*' --env production
```

Predefined queries:

- `recent_errors`
- `recent_warnings`
- `exceptions`
- `slow_requests`

## Development

```bash
cd tools/python/libs/kibana
uv sync
pytest
python -m cptools_kibana.cli --help
```
