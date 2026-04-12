---
name: confluence
description: Use when the task requires Confluence page search, single-page fetch, space extraction, Markdown or OpenAPI upload, or page translation via the installed `confluence-sync` CLI. Do not assume a `cp-tools` checkout exists.
---

# confluence

Use the installed `confluence-sync` CLI. Treat this skill as a routing and command-shaping layer, not as a substitute implementation.

Install once on a new machine with:

```bash
bash packages/confluence-sync/install.sh
```

Manual fallback:

```bash
uv tool install git+ssh://git@github.com/cpoopc/share-libs.git#subdirectory=packages/confluence-sync
npx skills add /path/to/share-libs --skill confluence -g -y
confluence-sync init
confluence-sync doctor
```

## Scope Boundaries

- Use this skill for generic Confluence search, extract, upload, fetch, and translation tasks.
- Do not assume `cp-tools`, `apps/confluence`, or repo-local runners are available.
- Prefer MCP fallback only when the installed CLI path is blocked or the user explicitly wants MCP-specific behavior.

## References

- Read `references/commands.md` for installed-command usage patterns.

## Workflow

1. Route the request first.
   - Use `confluence-sync search` for CQL search.
   - Use `confluence-sync fetch` for a single page body converted to Markdown.
   - Use `confluence-sync extract` for space export workflows.
   - Use `confluence-sync upload` for Markdown or OpenAPI upload.
   - Use `confluence-sync translate` for page translation workflows.
2. Resolve environment scope.
   - Run `confluence-sync init` on a fresh machine before the first real command.
   - Run `confluence-sync doctor --env ...` when auth, env file selection, config, or output roots are unclear.
   - Use `confluence-sync doctor --real` when you need to confirm live Confluence connectivity.
3. Run the narrowest command that answers the request.
   - Prefer `--dry-run` before real upload or bulk extract when the user did not explicitly ask to skip preview.
   - Use absolute file paths for upload inputs.
   - Use explicit `--env production` or `--env lab` when environment ambiguity matters.
4. Validate before concluding.
   - Confirm exported files or upload targets actually exist.
   - Distinguish raw page content or search output from your inference.

## Constraints

- Do not assume Mermaid rendering is available unless `mmdc` is installed and `doctor` confirms the environment is ready.
- Do not perform a real upload when a dry-run is the safer default and the user did not ask to skip preview.
- Do not invent Confluence page IDs, parent IDs, or space keys.
- Do not claim extraction or upload succeeded without checking the generated files or response output.

## Validation

- Confirm `confluence-sync doctor` is clean enough when configuration is in doubt.
- Confirm upload inputs use absolute paths.
- Confirm the selected command path matches one of the cases in `references/commands.md`.
- State clearly when the result is limited by missing credentials, missing `mmdc`, or lack of Confluence permissions.
