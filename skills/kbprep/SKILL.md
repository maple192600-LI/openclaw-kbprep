---
name: kbprep
description: Convert local raw source files into clean Markdown for Obsidian or LLM Wiki workflows without summarizing away details. The OpenClaw plugin is the primary entry point; a standalone CLI is included for non-OpenClaw hosts.
---

# KBPrep Skill

## Purpose

KBPrep does one job: turn a local raw source file into readable, clean Markdown for later knowledge-base use.

It does not build indexes, generate final wiki articles, summarize source material, or fetch remote platform content. For YouTube, Douyin, Xiaohongshu, and similar sources, v1 expects a local subtitle, transcript, saved page, or exported text file.

## Entry Points

The OpenClaw plugin is the primary entry point. The same Python core is also accessible via:

- **OpenClaw plugin**: `kbprep_preflight`, `kbprep_analyze`, `kbprep_prepare`, `kbprep_apply_review`, `kbprep_cleanup`, `kbprep_prepare_batch`
- **Standalone CLI** (for non-OpenClaw hosts and shell scripts): `kbprep-prepare`, `kbprep-analyze`, `kbprep-preflight`, `kbprep-apply-review`, `kbprep-cleanup`, `kbprep-batch`
- **Python API** (for Python scripts and notebooks): `from kbprep_worker.cli` or `subprocess.run(["python", "-m", "kbprep_worker.cli", ...])`

All three entry points share the same Python worker (`kbprep_worker/`), the same JSON envelope on stdout, and the same plugin-local venv.

## Tool Order (any entry point)

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
- `openclaw`: OpenClaw subagent (used by the OpenClaw plugin path).
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
