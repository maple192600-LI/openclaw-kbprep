# KBPrep

KBPrep is a local, host-neutral CLI for turning source files into quality-checked Obsidian Markdown.

The project boundary is the file-to-Markdown quality loop:

1. detect the input file type and the best conversion route
2. convert the source into Markdown with traceable intermediate artifacts
3. compare converted Markdown with the source so missing chapters, tables, images, links, code, and other details are caught early
4. classify the document type and load the matching cleaning dictionaries
5. run deterministic cleanup before asking an AI reviewer for semantic judgment
6. re-check quality after each cleanup/review pass
7. export to Obsidian only after the quality gate passes
8. turn user feedback into reusable cleaning dictionary proposals

`kbprep-prepare` classifies document type during the pipeline and uses that detected type when selecting cleanup dictionaries.

KBPrep does not maintain agent-specific adapters. Claude Code, Codex, OpenClaw, Hermes, or any other AI coding agent should call the CLI and package the repository in whatever skill/plugin format that host supports.

## Review Hardening

Current hardening rules:

- OCR normalization rules are data in `rules/base/ocr_normalization.json`.
- Heading levels are preserved by default; KBPrep does not guess structural heading repairs.
- Standalone AI review uses injected backends or a host-neutral external command protocol, and otherwise reports an explicit unavailable-backend warning.
- `python/kbprep_worker/stages/pipeline.py` is a small compatibility surface; implementation details are split into focused modules such as converters and audit helpers.

## Current State

The current codebase already has a Python worker, a Node CLI bridge, conversion routes, audit outputs, and a quality report. It is not yet the full target system. Known gaps are tracked in:

- [docs/capability-matrix.md](docs/capability-matrix.md)
- [docs/quality-loop.md](docs/quality-loop.md)
- [docs/feedback-learning.md](docs/feedback-learning.md)
- [docs/agent-neutral.md](docs/agent-neutral.md)

Do not claim a source format is fully supported unless the capability matrix links it to tests or fixtures.

## CLI

Standalone commands:

```bash
kbprep-preflight --help
kbprep-analyze --input ./source.pdf --output ./.kbprep/analyze
kbprep-prepare --input ./source.pdf --output ./.kbprep/source --force
kbprep-apply-review --run-dir ./.kbprep/source/runs/<run-id> --patch-file review.patch.json
kbprep-feedback --run-dir ./.kbprep/source/runs/<run-id> --feedback-text "下次删除「关注公众号」这种污染"
kbprep-cleanup --output ./.kbprep/source --dry-run
kbprep-batch --input ./sources --output ./.kbprep/batch
```

The CLI prints JSON envelopes for worker results. Failures use the same shape with `ok: false`, an error code, and optional warnings.

## Runtime

KBPrep creates its own Python runtime at `.kbprep/venv` inside the package directory. It installs worker dependencies there instead of using system Python packages.

Current worker dependencies include MinerU and PyMuPDF. KBPrep should use proven open-source converters and OCR tools where possible; it should not become a custom OCR project.

First-run setup is split into visible steps: create venv, upgrade packaging tools,
install worker dependencies, and run the setup-env probe. Advanced operators can
override the bootstrap Python with `KBPREP_BOOTSTRAP_PYTHON` or configured
`python_path`; setup timeout failures include stderr evidence.

For direct Python worker development:

```bash
uv pip install --system -e ./python
PYTHONPATH=python python -m kbprep_worker.cli --help
```

## Build And Test

```bash
npm install
npm run build
npm test
npm run pack:check
```

Use the release gate before publishing:

```bash
npm run release:check
```

When `F:\Obsidian-Vault` is available, run the isolated real-document smoke
suite as an additional local release check:

```bash
npm run vault:smoke
```

`vault:smoke` copies representative files to a temporary directory before
running prepare or batch. It must not write final Markdown or assets back into
the original Obsidian vault.

Worker scenario tests are split by domain under `src/test/scenarios/`; shared
fixture helpers live in `src/test/helpers/workerHarness.ts`.

## Agent Usage

Agents should treat KBPrep as a CLI tool plus documented protocols:

- call the CLI
- read `review_pack` when semantic review is needed
- return a validated patch or rule proposal
- let KBPrep apply the patch and run quality gates

The repository intentionally does not ship Claude Code, Codex, OpenClaw, or Hermes adapter logic.
