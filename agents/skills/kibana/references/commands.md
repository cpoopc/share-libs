# kibana commands

Use the installed `kibana-query` CLI. Default runtime layout:

- config: `~/.config/kibana-query/`
- cache: `~/.cache/kibana-query/`

## First-time setup

```bash
kibana-query init
kibana-query doctor
kibana-query doctor --env production
kibana-query test --env production
```

`init` creates:

- `~/.config/kibana-query/.env.example`
- `~/.config/kibana-query/.env.lab`
- `~/.config/kibana-query/.env.production`

Expected credentials:

```bash
KIBANA_URL=https://kibana.example.com
KIBANA_USERNAME=your-username
KIBANA_PASSWORD=your-password
KIBANA_INDEX=*:*-logs-*
```

## Core commands

```bash
# Generic search
kibana-query search 'level:ERROR' --env production --last 1h

# Predefined query
kibana-query search recent_errors --env lab --last 30m

# Only count matching logs
kibana-query search 'message:*timeout*' --env production --last 1h --count

# Export to JSON
kibana-query export 'trace_id:abc123' --env production --last 24h --format json --output ./trace.json

# Export to Markdown
kibana-query export 'message:*timeout*' --env lab --last 2h --format markdown --output ./timeouts.md

# List matching indices
kibana-query indices '*logs*' --env production

# Connectivity smoke test
kibana-query test --env lab
```

## Smart query behavior

- A 36-character UUID is treated as `conversationId:"..."`
- A value starting with `s-` is treated as `sessionId:"..."`
- Unquoted known ID fields such as `request_id:abc` are auto-quoted
- Predefined queries:
  - `recent_errors`
  - `recent_warnings`
  - `exceptions`
  - `slow_requests`

## Common query patterns

```bash
# Errors in the last hour
kibana-query search 'level:ERROR' --last 1h

# Service-specific investigation
kibana-query search 'kubernetes.container.name:payment* AND level:ERROR' --last 1h

# Timeout investigation
kibana-query search 'message:*timeout*' --last 1h

# Follow a trace
kibana-query search 'trace_id:xyz123' --last 24h

# Discover available indices first
kibana-query indices '*air*' --env production
```

## Query notes

- Prefer explicit `--last` to keep the result set bounded.
- Use `--index` only when the default pattern is too broad or wrong.
- Use `--format json` when another tool or follow-up step will parse the output.
- Use `export` instead of `search --output ...` when the user explicitly wants a file artifact.
