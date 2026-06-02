---
name: kbprep
description: Convert local raw source files into clean Markdown for Obsidian or LLM Wiki workflows without summarizing away details. Host-agnostic: works as an OpenClaw plugin, MCP server, standalone CLI, or Python API.
---

# KBPrep Skill

## Purpose

KBPrep does one job: turn a local raw source file into readable, clean Markdown for later knowledge-base use.

It does not build indexes, generate final wiki articles, summarize source material, or fetch remote platform content. For YouTube, Douyin, Xiaohongshu, and similar sources, v1 expects a local subtitle, transcript, saved page, or exported text file.

## Host-Agnostic Design

KBPrep runs on **four interchangeable host entry points**. Pick the one that matches your agent runtime:

| Entry point | When to use | Where it lives |
|---|---|---|
| **OpenClaw plugin** | You use OpenClaw as your agent gateway. | `dist/index.js` (this npm package) |
| **MCP server** | You use Codex, Claude Code, Cursor, or any MCP-compatible agent. | `kbprep-mcp` binary (stdio transport) |
| **Standalone CLI** | You run kbprep from a shell, Makefile, or cron. | `kbprep-prepare` / `kbprep-analyze` / etc. |
| **Python API** | You write a Python script that imports the worker. | `from kbprep_worker import prepare` |

All four entry points share the same Python worker (`kbprep_worker/`), the same JSON envelope on stdout, and the same `~/.cache/kbprep` runtime. The TypeScript host layer is split into adapters under `src/adapters/`.

## Tool Order (any host)

1. Run `kbprep_preflight` once for the workspace or output root.
2. Run `kbprep_analyze` on the source file.
3. Run `kbprep_prepare` on one file.
4. Check `quality_report.json`, `audit.md`, `cleaned.md`, and `discarded.md`.
5. Use the source-side final Markdown beside the source file as the daily result.
6. Run `kbprep_cleanup(action="finalize")` after the user accepts the result.
7. Use `kbprep_prepare_batch` only after one representative sample passes.

## Tools

### `kbprep_preflight`

Read-only runtime readiness check before conversion. Reports Python version, MinerU availability/version, device mode, GPU/CPU hints, model-cache status, memory, disk space, and workspace write permission.

Always check `python_executable`, `mineru_path`, `torch`, `torch_cuda_available`, `torch_cuda_version`, `torch_device_count`, and `mineru_device` before a heavy PDF/Office run. In OpenClaw use, `python_executable` must point to the plugin-local `.kbprep/venv` runtime. If the user expects GPU but preflight shows CPU torch, rerun setup/preflight so the plugin-local venv installs CUDA torch, or set `device_override="cpu"` when GPU is not wanted.

### `kbprep_analyze`

Read-only diagnosis. Detects broad source family, PDF subtype, text profile, OCR recommendation.

### `kbprep_prepare`

Single-file conversion and cleaning pipeline. Modes:

- `rules_only`: deterministic conversion and conservative cleaning (default; always available).
- `rules_plus_review_pack`: also writes `review_pack.json` for AI or human review.
- `ai_review`: also runs an LLM review pass; the LLM backend is configurable.

### `kbprep_apply_review`

Apply a JSON Patch 1.0 patch to a `review_pack.json` produced by `kbprep_prepare`.

### `kbprep_cleanup`

Cleanup intermediate artifacts (`finalize` / `expired` / `all` actions).

### `kbprep_prepare_batch`

Batch conversion of a directory; `sample_first` defaults to `true` — the first file's result is treated as a representative sample and the batch stops on failure.

## AI Review Backends

`mode=ai_review` is configurable via `ai_review_backend`:

- `local_rules` (default): no AI call. `review_pack.json` is still produced; apply edits manually.
- `openclaw`: legacy default for OpenClaw users; calls the OpenClaw subagent runtime.
- `claude_code`: shells out to the `claude` CLI (Claude Code).
- `codex`: shells out to the `codex` CLI (OpenAI Codex).

Set via `kbprep` config (`ai_review_backend: "claude_code"`) or `KBPREP_AI_REVIEW_BACKEND` environment variable.

## Expected Output

- `original/`: original file backup
- `converted.md`: converted Markdown before cleaning
- `blocks.jsonl`: content blocks in original order
- `cleaned.md`: final readable Markdown
- source-side final Markdown: a direct-use `.md` file next to the source file, named from the source file stem
- `discarded.md`: removed pollution with reasons
- `review_needed.md`: uncertain content for manual review
- `images/`: copied local or embedded image assets referenced by the Markdown output
- `quality_report.json`: retention and quality checks

## Installing

### OpenClaw (existing users)

```bash
# OpenClaw auto-loads the plugin from its plugins directory.
openclaw plugins install openclaw-kbprep
```

### Codex / Claude Code / Cursor (MCP)

Add to your MCP client config (e.g. `~/.config/claude-code/mcp.json`):

```json
{
  "mcpServers": {
    "kbprep": { "command": "kbprep-mcp" }
  }
}
```

### Standalone CLI

```bash
npm install -g openclaw-kbprep
kbprep-prepare --input paper.pdf --output /tmp/out
kbprep-analyze --input paper.pdf
kbprep-preflight
```

### Python API

```bash
pip install -e ./python
```

```python
import json, subprocess
proc = subprocess.run(
    ["python", "-m", "kbprep_worker.cli", "prepare", "--json-stdin"],
    input=json.dumps({"input_path": "paper.pdf", "output_root": "/tmp/out"}),
    capture_output=True, text=True, check=True,
)
envelope = json.loads(proc.stdout)
```
