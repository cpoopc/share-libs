# confluence-sync

Installable Confluence search, extraction, upload, and translation CLI.

## Install

Recommended bootstrap from a `share-libs` checkout:

```bash
bash packages/confluence-sync/install.sh
```

From a local checkout this installs the CLI in editable mode, so the installed command follows the current clone. Use `--release-cli` when you need to validate the packaged install path instead.

Manual fallback:

```bash
uv tool install --force --editable /path/to/share-libs/packages/confluence-sync
uv tool install --force git+ssh://git@github.com/cpoopc/share-libs.git#subdirectory=packages/confluence-sync
npx skills add https://github.com/cpoopc/share-libs --skill confluence -g -y
confluence-sync init
confluence-sync doctor
```

## Runtime Layout

By default this tool uses XDG directories:

- config: `~/.config/confluence-sync/`
- cache: `~/.cache/confluence-sync/`
- output: `~/.cache/confluence-sync/output/`

Typical first commands:

```bash
confluence-sync init
confluence-sync doctor
confluence-sync doctor --env production --real
```

## Core Commands

```bash
confluence-sync search "title~'API'" --space IVA
confluence-sync fetch 1048584582
confluence-sync extract markdown --dry-run
confluence-sync extract pdf --dry-run
confluence-sync extract test
confluence-sync upload --file /absolute/path/to/doc.md --space IVA --parent 123456789 --dry-run
confluence-sync translate download 1035120878
```

Optional:

- Install `mmdc` if you need Mermaid rendering during upload.

## Development

```bash
cd packages/confluence-sync
uv sync
pytest
python -m cptools_confluence_sync.cli --help
```
