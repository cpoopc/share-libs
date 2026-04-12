# confluence commands

Use the installed `confluence-sync` CLI. Default runtime layout:

- config: `~/.config/confluence-sync/`
- cache: `~/.cache/confluence-sync/`
- output: `~/.cache/confluence-sync/output/`

## First-time setup

```bash
confluence-sync init
confluence-sync doctor
confluence-sync doctor --env production --real
```

Created files include:

- `~/.config/confluence-sync/.env`
- `~/.config/confluence-sync/.env.lab`
- `~/.config/confluence-sync/.env.production`
- `~/.config/confluence-sync/config.yaml`

Expected env values:

```bash
CONFLUENCE_URL=https://wiki.ringcentral.com
CONFLUENCE_USERNAME=your-email@example.com
CONFLUENCE_TOKEN=your-token
CONFLUENCE_OUTPUT_DIR=/path/to/export/root
```

## Core commands

```bash
# Search pages with CQL
confluence-sync search "title~'API'" --space IVA

# Fetch a single page body as Markdown
confluence-sync fetch 1048584582

# Extract configured spaces using config.yaml
confluence-sync extract markdown --dry-run
confluence-sync extract pdf --dry-run
confluence-sync extract test

# Upload one Markdown file
confluence-sync upload --file /absolute/path/to/doc.md --space IVA --parent 123456789 --dry-run

# Upload one OpenAPI file
confluence-sync upload --openapi /absolute/path/to/openapi.yaml --space IVA --parent 123456789 --dry-run

# Translate a page
confluence-sync translate download 1035120878
confluence-sync translate translate 1035120878 --backend tencent --dry-run
```

## Notes

- `upload` forwards to the packaged Markdown or OpenAPI uploader and automatically injects the XDG `config.yaml` unless you pass `--config` yourself.
- `extract` supports `markdown`, `pdf`, and `test`; it uses the XDG `config.yaml` by default.
- `translate` also receives the XDG `config.yaml` by default.
- `doctor --config /absolute/path/to/config.yaml` lets a local wrapper validate a non-XDG config.
- Install `mmdc` separately if you need rendered Mermaid output during upload; otherwise Mermaid blocks remain unrendered.
