# KBPrep Host Decoupling

KBPrep is a source-to-clean-Markdown project. OpenClaw is a supported adapter and installation route, but the core conversion, cleaning, quality gates, and curated Obsidian output live in the Python worker.

The npm package is named `kbprep`. The `openclaw-kbprep` id remains the OpenClaw adapter/plugin id and the current GitHub repository slug; renaming the remote repository is an external GitHub operation, not a source-code refactor.

## Current Architecture

```text
KBPrep
+-- python/kbprep_worker/        core conversion, cleaning, quality gates
+-- src/runtime/                 Node runtime setup for the Python worker
+-- src/worker.ts                JSON stdin/stdout worker bridge
+-- src/adapters/openclaw/       OpenClaw tool registration
+-- src/adapters/standalone/     standalone CLI argument adapter
+-- skills/kbprep/               agent usage guide
+-- docs/                        architecture and operating notes
```

The root `src/index.ts` is intentionally only a compatibility shim for OpenClaw's existing `dist/index.js` extension entry.

## Adapter Rules

- Python worker code must not import OpenClaw, Codex, Claude Code, Cursor, or any other host SDK.
- `src/worker.ts` must stay a generic JSON bridge to the Python worker.
- `src/runtime/` may manage the local KBPrep Python runtime, but it must not assume that the caller is an OpenClaw plugin.
- `src/adapters/openclaw/` may register OpenClaw tools and read OpenClaw plugin config.
- `src/adapters/standalone/` may parse command-line flags and print JSON results.
- Future Codex, Claude Code, Cursor, or MCP support must be thin wrappers around the same worker contract.
- `C:\Users\Administrator\Documents\Projects\kbprep` is the development checkout. `.openclaw\workspace\openclaw-kbprep` is an OpenClaw install/runtime workspace and must not be treated as the source of truth for development.

## Python Dependency Installation

The npm/OpenClaw runtime creates a KBPrep-local `.kbprep/venv` automatically. For direct worker development, prefer `uv` for fast compatible dependency resolution:

```bash
uv pip install --system -e ./python
uv pip install --system -e "./python[cuda]"
```

The CUDA extra is only for GPU validation. Normal runtime setup omits `device_override` and lets KBPrep choose the best available CPU/GPU mode.

## Why PR #9 Was Not Merged

The earlier `feature/decouple-from-openclaw` branch had useful direction but was not a safe merge base. Its standalone CLI failed TypeScript typecheck, Node CI failed, version files drifted, compiled `dist/adapters/*` outputs were missing from the package, and the runtime still mixed host-agnostic naming with plugin-root assumptions.

The useful parts were retained as design guidance:

- A standalone CLI is a correct entry point.
- OpenClaw should be optional for non-OpenClaw CLI usage.
- Project documentation should describe host boundaries and risk tags.
- AI review backend abstraction can be revisited after the stable local and OpenClaw paths are proven.

This branch reimplements the useful direction from the clean `main` baseline instead of cherry-picking the broken implementation.

## Non-Goals For This Step

- Do not rename the GitHub repository from code. If the repository slug changes later, update install URLs and GitHub Pages links in the same release.
- Do not move the local checkout yet.
- Do not make MCP the top-level architecture unless a real host needs it.
- Do not add concrete Codex or Claude Code provider adapters until the standalone CLI and OpenClaw paths are stable. The source-level AI review backend interface is allowed so hosts can plug in their own reviewer without changing classification safety rules.
