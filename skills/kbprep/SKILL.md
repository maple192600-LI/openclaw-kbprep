---
name: kbprep
description: Convert local raw source files into clean Markdown for Obsidian or LLM Wiki workflows without summarizing away details.
---

# KBPrep Skill

## Purpose

KBPrep does one job: turn a local raw source file into readable, clean Markdown for later knowledge-base use.

It does not build indexes, generate final wiki articles, summarize source material, or fetch remote platform content. For YouTube, Douyin, Xiaohongshu, and similar sources, v1 expects a local subtitle, transcript, saved page, or exported text file.

## Operator Workflow

1. Run `kbprep_preflight` once for the workspace or output root.
2. Run `kbprep_analyze` on the source file.
3. Run `kbprep_prepare` on one representative file.
4. Check `quality_report.json` and confirm there are no strict errors.
5. Check `discarded.md` and `review_needed.md`; do not finalize while `review_needed.md` has unresolved content.
6. Confirm the profile-specific final deliverable:
   - `curated_obsidian_kb`: use `latest_outputs.obsidian_dir` and `latest_outputs.obsidian_index`; `latest_outputs.final_md` should be `null`.
   - `standard`: use `latest_outputs.final_md`, the source-side Markdown beside the source file.
7. Run `kbprep_cleanup(action="finalize")` only after the user accepts the result.
8. Use `kbprep_prepare_batch` only after one representative sample passes the same checks.

Do not accept fake closure:

- Do not approve a run by reading only `cleaned.md`.
- Do not ignore `quality_report.json` strict errors.
- Do not run finalize while `review_needed.md` has content unless the user explicitly accepts it with `confirm_review_needed=true`.
- Do not run batch before a representative sample passes.

## Tools

### `kbprep_preflight`

Read-only runtime readiness check before conversion. It reports:

- Python version and selected worker runtime.
- MinerU availability and version for PDF/Office/image conversion.
- Device mode, GPU/CPU hints, model-cache status, memory, disk space, and workspace write permission.

Always check `python_executable`, `mineru_path`, `torch`, `torch_cuda_available`, `torch_cuda_version`, `torch_device_count`, and `mineru_device` before a heavy PDF/Office run. In normal use, `python_executable` must point to the KBPrep-local `.kbprep/venv` runtime. If the user expects GPU but preflight shows CPU torch, rerun setup/preflight so the KBPrep-local venv installs CUDA torch, or set `device_override="cpu"` when GPU is not wanted.

Runtime rule: KBPrep creates and runs its own `.kbprep/venv` inside the package directory. `python_path` is only an optional bootstrap interpreter for creating that venv; it is not the dependency runtime. The worker must resolve MinerU beside the KBPrep-local venv Python and must not fall back to a system-wide MinerU or unrelated Python environment.

If full conversion dependencies are missing, text-like files may still work, but PDF/Office/image conversion should be treated as not ready until preflight is clean enough for the intended file type.

### `kbprep_analyze`

Read-only diagnosis. It detects:

- Broad source family: PDF, Word, PPT, Markdown, TXT, subtitle/transcript, image, audio, video, or unknown.
- PDF subtype: text-layer, scanned/image-only, mixed image/text, garbled text layer, or PPT-export-like.
- Text profile: short text, long text, tutorial, meeting/interview, transcript, note, or ebook/long report.
- OCR recommendation and text quality warnings.

### `kbprep_prepare`

Single-file conversion and cleaning pipeline.

For converter-backed formats such as PDF, Word, PPT, Excel, EPUB, and images, KBPrep first preserves the original file, then validates obvious container problems before invoking the heavy converter. A corrupted or mislabeled `.docx`, `.pptx`, `.xlsx`, or `.epub` fails with `E_CONVERT_INPUT_INVALID` and must not publish `cleaned.md` or `latest.json`.

For saved HTML, Markdown notes, modern Office XML, and EPUB sources, image references are not treated as disposable decoration. Local or embedded image assets should be copied into `images/` and the Markdown should point at those portable paths. Links in HTML/EPUB should remain Markdown links.

Modes:

- `rules_only`: deterministic conversion and conservative cleaning.
- `rules_plus_review_pack`: also writes `review_pack.json` for AI or human review.
- `ai_review`: asks an OpenClaw subagent to classify review-pack blocks, then applies a guarded JSON Patch. Text cannot be rewritten.

Use `ai_review` only when contextual judgment matters, such as deciding whether "platform", "account", "side project", "group", or "community" is real tutorial content or marketing pollution.

### `kbprep_apply_review`

Applies a JSON Patch to block metadata after human or AI review.

Allowed changes:

- `status`: only `keep`, `discard`, `evidence`, or `review`
- `risk_tags`: list of strings; `add` may append one string
- `reason`: string
- `confidence`: number from 0 to 1

Forbidden changes:

- Source text
- Page or line trace
- Protected blocks such as operation steps, prompts, code, tables, tool instructions, concrete examples, links, parameters, and numbers.
- Invalid metadata that would make a block disappear from all rendered outputs.

### `kbprep_cleanup`

Removes intermediate artifacts after the user accepts a result. It must never delete the source file or the profile-specific final deliverable.

Actions:

- `finalize`: keep the final deliverable plus a tiny manifest under `output_root`; delete process/audit files such as `runs/`, `original/`, `converted.md`, `blocks.jsonl`, `discarded.md`, `review_needed.md`, `quality_report.json`, `parts/`, `images/`, and batch process files. In curated mode, keep `obsidian/`; in standard mode, keep the source-side Markdown/assets.
- `expired`: remove old run history, defaulting to older than 7 days.
- `all`: remove known intermediate artifacts without checking acceptance state.

If `review_needed.md` still has content, `finalize` should stop unless `confirm_review_needed=true` is explicitly provided.

### `kbprep_prepare_batch`

Directory processing. It runs one sample first and stops if that sample fails quality gates. This prevents one bad rule or converter choice from damaging a whole batch.

Each source file gets its own output directory under `<batch_output_root>/files/`. Do not read `<batch_output_root>/cleaned.md` after a batch. Use `results.json`:

- Curated success entries have `final_artifact_type="obsidian_dir"`, `batch_obsidian_dir`, and `batch_obsidian_index`.
- Standard success entries have `final_artifact_type="markdown"` and `batch_final_md`.

## Output

Each successful run writes a profile-specific final deliverable. The top-level output files and `runs/<run_id>/` are audit/process material:

```text
<output_root>/
  original/
    <sha256>.<ext>
  converted.md
  conversion_report.json
  blocks.jsonl
  cleaned.md
  discarded.md
  review_needed.md
  images/
  audit.md
  quality_report.json
  parts/
  review_pack.json
  latest.json
  runs/<run_id>/
    converted.md
    conversion_report.json
    normalized.md
    blocks.jsonl
    cleaned.md
    discarded.md
    review_needed.md
    images/
    evidence/
    chunks/
    parts/
    audit.md
    quality_report.json
    chunk_manifest.jsonl
    review_pack.json
```

For `profile="curated_obsidian_kb"`, the final deliverable is `obsidian/`, entered through `obsidian/00-索引.md`; `final_md` is intentionally `null`. For `profile="standard"`, the final deliverable is the source-side final Markdown. After `kbprep_cleanup(action="finalize")`, only the final deliverable and a small manifest such as `kbprep_manifest.json` or `kbprep_batch_manifest.json` should remain.

For short files, `parts/` may be empty. For long files, parts are cut by headings and natural content boundaries, not by page number. `parts/parts_manifest.json` records `part_id`, `heading_path`, `block_ids`, and `char_count`; reading `part_001.md`, `part_002.md`, ... in manifest order should reconstruct `cleaned.md` after removing frontmatter. Top-level files are updated only after a run has no strict quality errors.

Batch output:

```text
<batch_output_root>/
  progress.json
  failures.json
  results.json
  files/
    <source-stem>_<hash>/
      cleaned.md
      obsidian/
      discarded.md
      review_needed.md
      quality_report.json
      runs/<run_id>/
```

## Cleaning Policy

Remove from the main body:

- QR codes, scan-to-join text, buying prompts, trial cards, discounts, platform UI, irrelevant headers/footers, repeated TOCs, watermarks, and unrelated marketing covers.

Preserve in the main body:

- Steps, workflows, tool/platform/account setup, parameters, prompts, code, tables, cases, failure lessons, caveats, judgment criteria, links, and numbers.

If unsure, mark `review`; do not delete.

## Quality Rule

`cleaned.md` alone is not proof. A run is valid only when `quality_report.json` has no strict errors, the discarded/review files make sense on inspection, and the profile-specific final deliverable exists.
