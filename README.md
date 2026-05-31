# KB Prep Tool

OpenClaw plugin for converting local raw source files into clean Markdown for Obsidian or LLM Wiki workflows.

The plugin focuses on preparation only: detect file type, convert as losslessly as possible, split by content structure, remove pollution, preserve concrete knowledge details, and keep discarded/review material traceable.

It does not build a RAG index, generate wiki pages, or download from remote platforms.

## Use It For One Thing

Give the plugin a local raw file. It produces readable Markdown for a knowledge base.

Default entry:

```text
kbprep_prepare(input_path, output_root)
```

Expected output:

- `original/`: original file backup
- `converted.md`: converted Markdown before cleaning
- `blocks.jsonl`: content blocks in original order
- `cleaned.md`: final readable Markdown
- `discarded.md`: removed pollution with reasons
- `review_needed.md`: uncertain content for manual review
- `quality_report.json`: retention and quality checks

Start with `mode="rules_only"`. Use `mode="rules_plus_review_pack"` only when you want an AI or human to review uncertain blocks. Use `mode="ai_review"` only when OpenClaw subagents are available and you accept the extra model call.

## Tools

- `kbprep_prepare`: main tool. Convert one local source file into clean Markdown.
- `kbprep_analyze`: optional read-only check for file type, PDF subtype, text quality, and route.
- `kbprep_preflight`: optional runtime check before large PDF/OCR work.
- `kbprep_apply_review`: optional guarded metadata patch for human/AI review results. It cannot rewrite source text.
- `kbprep_prepare_batch`: optional directory mode. It is for repeated local files, not platform harvesting.

For audio/video, v1 handles local subtitle, transcript, or ASR text files. It does not automatically download or transcribe binary media.
Batch runs write `batch_inventory.json`, so unsupported or skipped local files are visible instead of silently ignored. Audio/video binaries are marked as `media_binary_not_transcribed_in_v1`; unknown extensions are marked as unsupported.
Batch mode is conservative with heavy conversion files: PDF, image, MOBI, and legacy Office files are processed one at a time even when `convert_jobs` is greater than 1. Lightweight text/code/subtitle/modern Office XML files may use `convert_jobs`.

`quality_report.json` includes `detail_retention`, a block-level retention inventory for operation steps, tools/platforms, parameters, links, prompts, code, tables, and numeric details. Discarding blocks that contain these concrete knowledge signals is treated as a strict QA failure unless they are known pollution with no detail signal.
It also includes `output_retention`, which checks that links, parameter assignments, code blocks, and table blocks from kept/review/evidence blocks appear in their rendered destination: `cleaned.md`, `review_needed.md`, or `evidence/marketing_pages.md`. Missing rendered detail signals are strict QA failures.

GitHub-style source and config files such as `.py`, `.js`, `.ts`, `.sh`, `.ps1`, `.sql`, `.yaml`, `.toml`, and `.ini` are handled as direct code inputs. The plugin wraps the original file in a fenced Markdown code block so code, parameters, links, and failure-handling details stay intact.

Jupyter notebooks (`.ipynb`) are handled as structured local source files. Markdown cells are kept as Markdown, code cells are kept in fenced code blocks using the notebook language when available, and text outputs are preserved under per-cell output sections so tutorial parameters, examples, errors, and results remain readable.

## Runtime Selection

On first use, the plugin creates its own Python runtime at `.kbprep/venv` inside the plugin directory and installs the Python worker dependencies there. It does not install MinerU, torch, PyMuPDF, or other worker dependencies into system Python.

The plugin always runs the worker through this plugin-local `.kbprep/venv` in normal OpenClaw use. `python_path` is only an optional bootstrap interpreter used to create that venv; it is not treated as the dependency runtime.

The worker is also isolated from user-site packages (`PYTHONNOUSERSITE=1`), and MinerU is resolved only from the selected venv's `Scripts/` or `bin/` directory. A system-wide `mineru` on PATH is not used.
When an NVIDIA driver is detected and the plugin-local torch is CPU-only, setup installs pinned CUDA wheels (`torch==2.8.0`, `torchvision==0.23.0`, cu126 index) into `.kbprep/venv` and then re-checks torch in a fresh Python process. Set plugin config `device_override="cpu"` to skip CUDA wheel installation.
The setup result is written to `.kbprep/runtime-ready.json` so the selected Python path, CUDA action, and detected torch state are traceable.
The ready marker includes the plugin version, selected Python path, worker dependency spec, and `device_override`. If any of those no longer match, the plugin deletes only its own `.kbprep/venv` and marker, then rebuilds the runtime instead of reusing a stale or wrong environment.

Run `kbprep_preflight` before heavy PDF/Office conversion and check:

- `python_executable`
- `runtime_isolated`
- `pymupdf`
- `pdf_text_layer_available`
- `mineru_path`
- `mineru`
- `torch`
- `torch_cuda_available`
- `torch_cuda_version`
- `torch_device_count`
- `mineru_device`

If these fields show CPU torch but you expected GPU, the plugin-local `.kbprep/venv` was not prepared with CUDA torch. Re-run `kbprep_preflight` after setup, or delete `.kbprep/venv` and let the plugin rebuild it.

PDF routing is staged. Trusted text-layer PDFs and PPT-exported PDFs with a healthy text layer use the lightweight `pdf_text_layer` converter first, preserving page/slide order evidence without invoking MinerU. This path requires PyMuPDF in the selected Python environment. Scanned, image-heavy, garbled, legacy Office, MOBI, and image inputs still route to MinerU/OCR when diagnosis says the text layer is missing or unsafe.

For trusted PDF text layers, the converter also unwraps common hard line breaks inside Chinese paragraphs, so PDF layout wraps such as split words or mid-sentence line breaks do not become broken Markdown paragraphs. Structural lines such as titles, lists, code fences, tables, and page markers remain separate.

Some PDFs contain an embedded text layer that exists but is not readable because of custom font encoding. Diagnosis treats high replacement-character or non-common-Unicode ratios as an untrusted garbled text layer and routes those files to MinerU/OCR instead of publishing broken Markdown.

If a PDF looks trustworthy during diagnosis but the later text-layer conversion still produces unreadable Markdown, `kbprep_prepare` automatically saves that rejected text-layer output as `converted.pdf_text_layer.rejected.md`, reruns MinerU in OCR mode, and records `W_PDF_TEXT_LAYER_FALLBACK_TO_OCR` in `conversion_report.json`.

Internal PDF page markers are kept as block/page metadata for traceability, but they are not rendered into `cleaned.md` or long-document `parts/` files. The readable Markdown output should contain knowledge content, not conversion comments.

When a useful source/cover block also contains standalone promotional lines such as public-account follow prompts, companion-video ads, or update-channel notices, those lines are split into `discarded.md` while the rest of the source metadata and tutorial body stays in `cleaned.md`.

EPUB routing is also lightweight. EPUB files are extracted from their spine-ordered XHTML/HTML chapters into Markdown with headings, lists, paragraphs, and table-like text preserved. MOBI remains on the heavy conversion route.

For large PDF/PPT-style conversions, set plugin config `mineru_timeout_seconds` when the default 1140 seconds is too short or too long for your machine. If MinerU times out, `prepare` returns `E_TIMEOUT` and keeps `original/`, `diagnosis_report.json`, and `error_report.json` for review.

## Build

```bash
npm install
npm run plugin:build
npm run plugin:validate
npm test
```

## Install From GitHub

```bash
openclaw plugins install git:github.com/maple192600-LI/openclaw-kbprep
openclaw gateway restart
openclaw plugins inspect openclaw-kbprep --runtime --json
```

This repository includes the compiled `dist/` runtime because OpenClaw managed installs require readable JavaScript runtime files for native plugins. Local dependency folders, local Python runtimes, raw source documents, and generated conversion outputs remain ignored.

## OpenClaw Plugin Lifecycle Checks

OpenClaw discovers plugins from config/install metadata, then activates the entry module and registers tools at runtime.
For this plugin the entry is `./dist/index.js`, exposed through `package.json` `openclaw.extensions`.

Use these checks when changing or installing the plugin:

```bash
npm run plugin:build
npm run plugin:validate
openclaw plugins inspect openclaw-kbprep --runtime --json
```

`openclaw plugins list` is useful for discovery, but it can show stale registry metadata and does not prove the running Gateway has registered the tools. The runtime inspect output must show:

- `status: "loaded"`
- `shape: "non-capability"`
- `toolNames`: `kbprep_preflight`, `kbprep_analyze`, `kbprep_prepare`, `kbprep_apply_review`, `kbprep_prepare_batch`
- `configSchema: true`

After install, config, or code changes, restart the Gateway before testing the plugin from chat or channels.
