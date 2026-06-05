# KBPrep Standalone CLI

The standalone CLI uses the same Python worker as the OpenClaw adapter. It is for local files only.

## Commands

```bash
kbprep-preflight --workspace ./.kbprep/check
kbprep-analyze --input ./source.pdf --output ./.kbprep/source
kbprep-prepare --input ./source.pdf --output ./.kbprep/source --mode rules_only --force
kbprep-apply-review --run-dir ./.kbprep/source/runs/<run-id> --patch ./review.patch.json
kbprep-cleanup --output ./.kbprep/source --action finalize
kbprep-batch --input ./sources --output ./.kbprep/batch --mode rules_only
```

## Help

Every command supports `--help`:

```bash
kbprep-preflight --help
kbprep-analyze --help
kbprep-prepare --help
kbprep-apply-review --help
kbprep-cleanup --help
kbprep-batch --help
```

## Modes

- `rules_only`: local deterministic cleanup only.
- `rules_plus_review_pack`: local cleanup plus `review_pack.json` for human or external AI review.
- `ai_review`: only available when the host provides an AI review backend. The OpenClaw adapter supplies this through its subagent runtime; the standalone CLI does not yet call a generic LLM provider by itself.

## Output

`kbprep-prepare` writes process artifacts under the output directory and publishes a profile-specific final deliverable:

- Default `--profile curated_obsidian_kb`: use `latest_outputs.obsidian_dir` and `latest_outputs.obsidian_index`. `latest_outputs.final_md` is intentionally `null`.
- `--profile standard`: use `latest_outputs.final_md`, the source-side Markdown file beside the source.

Use `kbprep-cleanup --action finalize` only after checking `quality_report.json`, `discarded.md`, and `review_needed.md`. Finalize preserves the final deliverable: `obsidian/` for curated runs, or source-side Markdown/assets for standard runs.
