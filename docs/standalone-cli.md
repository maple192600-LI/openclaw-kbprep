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

`kbprep-prepare` writes process artifacts under the output directory and publishes human-facing final outputs beside the source file when the profile requires it. Use `kbprep-cleanup --action finalize` only after checking `review_needed.md`.
