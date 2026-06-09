# KBPrep Host Decoupling

KBPrep is a source-to-clean-Markdown project. Host agents are packaging routes, not the project boundary. The core conversion, cleaning, quality gates, and Markdown/Obsidian output live in the Python worker.

The npm package is named `kbprep`. Host-specific plugin or skill wrappers should be generated outside the core project from the CLI and `skills/kbprep/SKILL.md`.

## Current Architecture

```text
KBPrep
+-- python/kbprep_worker/        core conversion, cleaning, quality gates
+-- src/runtime/                 Node runtime setup for the Python worker
+-- src/worker.ts                JSON stdin/stdout worker bridge
+-- src/adapters/standalone/     standalone CLI argument adapter
+-- skills/kbprep/               agent usage guide
+-- docs/install/                host packaging instructions
+-- docs/                        architecture and operating notes
```

The root `src/index.ts` exports host-neutral runtime helpers. It must not become a host-specific adapter entry.

## Adapter Rules

- Python worker code must not import OpenClaw, Codex, Claude Code, Cursor, or any other host SDK.
- `src/worker.ts` must stay a generic JSON bridge to the Python worker.
- `src/runtime/` may manage the local KBPrep Python runtime, but it must not assume that the caller is an OpenClaw plugin.
- `src/adapters/standalone/` may parse command-line flags and print JSON results.
- Future Codex, Claude Code, OpenClaw, Cursor, Hermes, or MCP support must be generated or maintained outside the core worker contract.
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

- A standalone CLI is the correct maintained entry point.
- Host-specific wrappers should stay optional and external to the core project.
- Project documentation should describe host boundaries and risk tags.
- AI review backend abstraction can be revisited after the stable local and OpenClaw paths are proven.

This branch reimplements the useful direction from the clean `main` baseline instead of cherry-picking the broken implementation.

## Non-Goals For This Step

- Do not rename the GitHub repository from code. If the repository slug changes later, update install URLs and GitHub Pages links in the same release.
- Do not move the local checkout yet.
- Do not make MCP the top-level architecture unless a real host needs it.
- Do not add concrete Codex, Claude Code, OpenClaw, or Hermes provider adapters to the core project. The source-level AI review backend interface is allowed so hosts can plug in their own reviewer without changing classification safety rules.
