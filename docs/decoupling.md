# Host-Agnostic Architecture

This document explains how kbprep went from a single-host OpenClaw plugin
(v0.4.x) to a host-agnostic skill with three interchangeable entry points
(v0.5.0+). It is intended for contributors adding a wrapper for a fourth
host or debugging cross-host behaviour.

## The Problem (v0.4.x)

- `peerDependencies.openclaw` made installation hard outside OpenClaw.
- `src/index.ts` imported `openclaw/plugin-sdk/tool-plugin` at module top.
- `src/aiReview.ts` called `context.api.runtime.subagent` directly.
- `envelope.py` docstring said "TypeScript layer" as if there was only one.
- Non-OpenClaw users (shell scripts, Python scripts, Claude Code, Codex) had no way to call kbprep.

## The Solution (v0.5.0)

The Python core (`python/kbprep_worker/`) is host-agnostic. It speaks
JSON-on-stdin, JSON-on-stdout, and emits JSONL logs to stderr. The
TypeScript layer is split into:

```
src/
├── index.ts                # OpenClaw plugin entry (legacy; unchanged for v0.4.x compat)
├── aiReview.ts             # OpenClaw AI review glue (legacy)
├── errors.ts               # Error / warning codes (KBPREP_E_* / KBPREP_W_*)
├── worker.ts               # Python worker spawner (host-agnostic)
└── adapters/
    ├── python_runtime.ts   # venv management (host-agnostic)
    ├── ai_review/          # AI review backend abstraction
    │   ├── backend.ts      # AIReviewBackend Protocol
    │   ├── local_rules.ts  # Default: no AI call
    │   ├── openclaw_subagent.ts  # OpenClaw subagent (legacy default)
    │   ├── claude_code.ts  # shells out to `claude` CLI
    │   ├── codex.ts        # shells out to `codex` CLI
    │   └── index.ts        # factory
    └── standalone/         # Standalone CLI (shell, cron, scripts)
        ├── cli.ts
        └── bin/
```

## Entry Points (priority order)

| Priority | Entry point | When to use | Token cost |
|---|---|---|---|
| 1 (primary) | **OpenClaw plugin** | OpenClaw users; auto-registered tools | Zero (host-managed) |
| 2 | **Standalone CLI** | Shell scripts, cron, Makefiles, self-media operators | Zero (subprocess only) |
| 3 | **Python API** | Python scripts, Jupyter notebooks | Zero (in-process) |
| 4 (optional) | **A fourth-host plugin** (e.g. Claude Code plugin) | Each non-OpenClaw host's own plugin system | Per host (usually low) |

Each host should pick its own way to invoke the same Python core. The pattern is:

1. The host has a plugin / extension / skill system.
2. The plugin ships a thin TypeScript or Python wrapper that maps the host's tool format onto the six core commands.
3. The wrapper shells out to the Python worker (`python -m kbprep_worker.cli <command> --json-stdin`).

## How to Add a New Host Wrapper

1. Create a wrapper directory: `src/adapters/<your-host>/` (TS) or `wrappers/<your-host>/` (Python).
2. Import `callWorker` from `../../worker.js` and `ensurePythonRuntime` from `../python_runtime.js`.
3. Map the host's protocol to the six core commands:
   `preflight`, `diagnose`, `prepare`, `apply-review`, `cleanup`, `prepare-batch`.
4. If the host needs AI review, plug a new `AIReviewBackend` into
   `src/adapters/ai_review/index.ts:buildBackend()`.
5. Add a bin entry in `package.json` `[bin]` if the host expects a CLI
   binary.
6. Document the host-specific install path in `README.md` and `skills/kbprep/SKILL.md`.

## AI Review Backend Selection

| Backend | When to use | Requires |
|---|---|---|
| `local_rules` | Default; no AI call. Use when you want a deterministic baseline. | Nothing |
| `openclaw` | OpenClaw users who want LLM review inside OpenClaw. | OpenClaw runtime |
| `claude_code` | Claude Code users; shells out to `claude --print`. | `claude` CLI on PATH |
| `codex` | OpenAI Codex users; shells out to `codex exec`. | `codex` CLI on PATH + `OPENAI_API_KEY` |

Selection order: explicit `ai_review_backend` config > `KBPREP_AI_REVIEW_BACKEND` env > `"local_rules"`.

## Compatibility Guarantees

- v0.5.0 keeps the OpenClaw plugin's tool surface byte-for-byte identical.
  Existing OpenClaw users see no change.
- `KBPREP_E_*` / `KBPREP_W_*` are the canonical codes. Legacy `E_*` /
  `W_*` codes are accepted in error envelopes and normalized to the
  prefixed form by `normalizeErrorCode()` in `src/errors.ts`.
  They will be removed in v1.0.0.
- The JSON envelope on stdout is stable: `{ok, data, metrics, warnings, error?}`.
- The Python CLI command set (`setup-env`, `preflight`, `diagnose`,
  `prepare`, `apply-review`, `cleanup`, `prepare-batch`) is stable.

## Migration Guide for OpenClaw Users

You do not need to do anything. Reinstall the plugin in OpenClaw and the
new version drops in. The six tools you know (`kbprep_preflight`, etc.)
work exactly as before. The only visible change is the version number.

## Why Not One Entry Point?

Splitting by entry point lets each host's plugin system stay simple:

- OpenClaw users get the 6 tools auto-registered in OpenClaw — no work needed.
- Shell users get `kbprep-prepare` as a familiar CLI command.
- Python users get `subprocess.run(["python", "-m", "kbprep_worker.cli", ...])` as a stable Python entry.

A single super-wrapper that tries to be all things ends up with a fat
config layer and a slow startup (every host's protocol parser is
imported even when only one is needed).
