# KBPrep

Source-to-clean-Markdown preparation for Obsidian and LLM Wiki workflows.

KBPrep turns a local raw source file (PDF, DOCX, PPT, EPUB, Markdown, code, subtitle, image, …) into readable, audit-friendly Markdown for downstream knowledge-base use. It does **not** build a RAG index, generate wiki pages, or download from remote platforms. Scope is intentionally narrow: prepare the source so a human or downstream tool can read it well.

**Host-agnostic.** Run it as an OpenClaw plugin, an MCP server (Codex / Claude Code / Cursor), a standalone CLI, or a Python library. The Python core is the same in every case; only the host adapter changes. See [`docs/decoupling.md`](docs/decoupling.md) for the architecture.

## Quick Start

### OpenClaw (existing users)

```bash
openclaw plugins install openclaw-kbprep
```

Then call `kbprep_preflight`, `kbprep_analyze`, `kbprep_prepare`, etc. from your OpenClaw agent. The six-tool surface is byte-for-byte identical to v0.4.x.

### Codex / Claude Code / Cursor (MCP)

Add to your MCP client config:

```json
{
  "mcpServers": {
    "kbprep": { "command": "kbprep-mcp" }
  }
}
```

Your agent can then call `kbprep_prepare(input_path, output_root)` etc. exactly as if they were OpenClaw tools.

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
# or, after `pip install -e .` on the package itself:
kbprep --help   # the `kbprep` console script
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

## What It Does

Give KBPrep a local raw file. It produces:

- `original/`: original file backup
- `converted.md`: converted Markdown before cleaning
- `blocks.jsonl`: content blocks in original order
- `cleaned.md`: final readable Markdown
- source-side final Markdown: a direct-use `.md` file next to the source file
- `discarded.md`: removed pollution with reasons
- `review_needed.md`: uncertain content for manual review
- `images/`: copied local or embedded image assets referenced by the Markdown output
- `quality_report.json`: retention and quality checks

For daily use, the source-side final Markdown is the file to move into or keep in your knowledge base. For example, `OpenClaw橙皮书.pdf` publishes `OpenClaw橙皮书.md` beside the source file. If the source itself is already Markdown, the plugin publishes `name.cleaned.md` instead of overwriting the original note. Image assets for that final file are copied beside the source as `name.assets/`.

## The Quality Gate

KBPrep's differentiator is the 8-check quality gate in `python/kbprep_worker/quality.py`:

- `protected_block_loss_strict: 0`
- `operation_step_loss_strict: 0`
- `prompt_loss_strict: 0`
- `code_block_loss_strict: 0`
- `table_loss_strict: 0`
- `qr_image_in_cleaned_strict: 0`
- `cta_in_cleaned_strict: 0`
- `discard_ratio_strict: 0.45`

Any block that carries a "knowledge signal" (operation step, tool/platform, parameter, link, prompt, code, table, number/metric) and gets dropped fails the gate. The retention check then verifies that the surviving kept/review/evidence blocks actually contain the same detail signals — defending against "the classifier was right but the renderer dropped it" bugs.

## AI Review (optional)

Three interchangeable LLM backends for the `ai_review` mode:

- `local_rules` (default): no AI call. `review_pack.json` is produced; apply edits manually.
- `openclaw`: OpenClaw subagent (legacy default).
- `claude_code`: shells out to the `claude` CLI.
- `codex`: shells out to the `codex` CLI (OpenAI Codex).

Configure via `ai_review_backend: "claude_code"` in your kbprep config, or `KBPREP_AI_REVIEW_BACKEND` environment variable.

## Cleanup

When you're satisfied with a result, run:

```text
kbprep_cleanup(output_root, action="finalize")
```

Finalize removes the temporary audit/process material under `output_root` (`runs/`, `original/`, `converted.md`, `blocks.jsonl`, `discarded.md`, `review_needed.md`, `quality_report.json`, `parts/`, `images/`, batch work folders). It keeps the source file, the source-side final Markdown, source-side assets, and a tiny `kbprep_manifest.json` or `kbprep_batch_manifest.json`. If `review_needed.md` still has content, finalize stops unless `confirm_review_needed=true` is passed.

If you're not sure yet, do nothing: the default `artifact_policy="keep_latest"` keeps only a short review window. You can also run `kbprep_cleanup(output_root, action="expired", older_than_days=7)` to remove old run history, or `action="all"` to remove known intermediate artifacts without touching source files.

## Documentation

- [`docs/decoupling.md`](docs/decoupling.md) — host-agnostic architecture, how to add a new host
- [`docs/risk-tags.md`](docs/risk-tags.md) — `risk_tags` enum (block-level + page-level)
- [`skills/kbprep/SKILL.md`](skills/kbprep/SKILL.md) — agent-facing skill description
- [`CHANGELOG.md`](CHANGELOG.md) — version history
- [`docs/index.html`](docs/index.html) — public showcase page (enable GitHub Pages on `docs/` to publish)

## Showcase

![KB Prep Tool showcase](docs/showcase-preview.png)

Public showcase page source: [`docs/index.html`](docs/index.html). For local preview:

```bash
npm run docs:serve
```

Then open the printed `http://127.0.0.1:.../` URL.

## License

MIT — see [`LICENSE`](LICENSE).
