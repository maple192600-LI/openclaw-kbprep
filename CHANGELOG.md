# Changelog

## 0.5.0

- Added a host-agnostic Node runtime layer for the Python worker.
- Moved OpenClaw tool registration into `src/adapters/openclaw/`.
- Added standalone CLI entry points: `kbprep-preflight`, `kbprep-analyze`, `kbprep-prepare`, `kbprep-apply-review`, `kbprep-cleanup`, and `kbprep-batch`.
- Marked OpenClaw as an optional peer dependency for non-OpenClaw CLI usage.
- Added host-decoupling and risk-tag documentation.

## 0.4.4

- Added curated Obsidian knowledge-base output.
- Strengthened marketing-wrapper cleanup and audit outputs.
- Preserved source-side final Markdown and cleanup lifecycle behavior.
