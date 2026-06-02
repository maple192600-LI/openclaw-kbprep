# Host-Agnostic Architecture

This document explains how kbprep went from a single-host OpenClaw plugin
(v0.4.x) to a host-agnostic skill with four interchangeable entry points
(v0.5.0+). It is intended for contributors adding a fifth host or
debugging cross-host behaviour.

## The Problem (v0.4.x)

- `peerDependencies.openclaw` made installation hard outside OpenClaw.
- `src/index.ts` imported `openclaw/plugin-sdk/tool-plugin` at module top.
- `src/aiReview.ts` called `context.api.runtime.subagent` directly.
- `envelope.py` docstring said "TypeScript layer" as if there was only one.
- Codex / Claude Code / Cursor users had no way to call kbprep.

## The Solution (v0.5.0)

The Python core (`python/kbprep_worker/`) is host-agnostic. It speaks
JSON-on-stdin, JSON-on-stdout, and emits JSONL logs to stderr. The
TypeScript layer is split into four adapters:

```
src/
├── index.ts                # OpenClaw plugin entry (legacy; re-exports below)
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
    ├── mcp/                # MCP server (Codex / Claude Code / Cursor)
    │   ├── server.ts
    │   └── bin.ts
    └── standalone/         # Standalone CLI (shell, cron, scripts)
        ├── cli.ts
        └── bin/
```

## How to Add a New Host

1. Create `src/adapters/<your-host>/<entry>.ts`.
2. Import `callWorker` from `../../worker.js` and
   `ensurePythonRuntime` from `../python_runtime.js`.
3. Map the host's protocol to the six core commands:
   `preflight`, `diagnose`, `prepare`, `apply-review`, `cleanup`, `prepare-batch`.
4. Add a bin entry in `package.json` `[bin]` if the host expects a CLI
   binary (e.g. `kbprep-mcp` for MCP).
5. If the host needs AI review, plug a new `AIReviewBackend` into
   `src/adapters/ai_review/index.ts:buildBackend()`.

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

## Why not just publish a separate npm package for each host?

Because the Python core is shared, and splitting the package would mean
duplicating `python/`, `docs/`, `skills/`, and `CHANGELOG.md` across
five packages. A monorepo with one `package.json` and one release
version keeps everything in sync.
