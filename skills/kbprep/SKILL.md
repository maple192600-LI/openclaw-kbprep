---
name: kbprep
description: Convert local raw source files into clean Markdown for Obsidian or LLM Wiki workflows without summarizing away details.
---

# KBPrep Skill

## Purpose

KBPrep does one job: turn a local raw source file into readable, clean Markdown for later knowledge-base use.

It does not build indexes, generate final wiki articles, summarize source material, or fetch remote platform content. For YouTube, Douyin, Xiaohongshu, and similar sources, v1 expects a local subtitle, transcript, saved page, or exported text file.

## Current Safety Contracts

- Treat KBPrep as host-neutral. Do not add OpenClaw, Claude, Codex, or other host adapter logic to this repository.
- OCR normalization is rule-dictionary driven through `rules/base/ocr_normalization.json`.
- Heading levels are preserved unless a future explicit rule with source evidence is added.
- AI review must use a host-injected backend or the standalone external command protocol. If neither is configured, report the warning and use review packs.

## Operator Workflow

1. Run `kbprep-preflight` once for the workspace or output root.
2. Run `kbprep-analyze` on the source file.
3. Run `kbprep-prepare` on one representative file.
4. Check `quality_report.json` and confirm there are no strict errors.
5. Check `discarded.md` and `review_needed.md`; do not finalize while `review_needed.md` has unresolved content.
6. Confirm the profile-specific final deliverable:
   - `curated_obsidian_kb`: use `latest_outputs.obsidian_dir` and `latest_outputs.obsidian_index`; `latest_outputs.final_md` should be `null`.
   - `standard`: use `latest_outputs.final_md`, the source-side Markdown beside the source file.
7. Use `kbprep-feedback` when user review finds a repeated cleanup miss or mistaken deletion.
8. Run `kbprep-cleanup --action finalize` only after the user accepts the result.
9. Use `kbprep-batch` only after one representative sample passes the same checks.

Do not accept fake closure:

- Do not approve a run by reading only `cleaned.md`.
- Do not ignore `quality_report.json` strict errors.
- Do not run finalize while `review_needed.md` has content unless the user explicitly accepts it with `confirm_review_needed=true`.
- Do not run batch before a representative sample passes.

## Tools

### `kbprep-preflight`

Read-only runtime readiness check before conversion. It reports:

- Python version and selected worker runtime.
- MinerU availability and version for PDF/Office/image conversion.
- Device mode, GPU/CPU hints, model-cache status, memory, disk space, and workspace write permission.

Always check `python_executable`, `mineru_path`, `torch`, `torch_cuda_available`, `torch_cuda_version`, `torch_device_count`, and `mineru_device` before a heavy PDF/Office run. In normal use, `python_executable` must point to the KBPrep-local `.kbprep/venv` runtime. Do not ask ordinary users to choose CPU or GPU: omit `device_override` and let KBPrep select the best available mode. Set `device_override="cpu"` only when GPU setup is explicitly unwanted.

Runtime rule: KBPrep creates and runs its own `.kbprep/venv` inside the package directory. `python_path` is only an optional bootstrap interpreter for creating that venv; it is not the dependency runtime. The worker must resolve MinerU beside the KBPrep-local venv Python and must not fall back to a system-wide MinerU or unrelated Python environment.

If full conversion dependencies are missing, text-like files may still work, but PDF/Office/image conversion should be treated as not ready until preflight is clean enough for the intended file type.

## Language Coverage

KBPrep v0.5 is tuned for Simplified Chinese self-media, course, and knowledge-base material. English support is best-effort and includes English step markers, URLs, CLI flags, prompts, and common subscription/join CTA patterns. Other languages are not yet tested. Check `quality_report.json` `language_detected` before accepting non-Chinese runs.

### `kbprep-analyze`

Read-only diagnosis. It detects:

- Broad source family: PDF, Word, PPT, Markdown, TXT, subtitle/transcript, image, audio, video, or unknown.
- PDF subtype: text-layer, scanned/image-only, mixed image/text, garbled text layer, or PPT-export-like.
- Text profile: short text, long text, tutorial, meeting/interview, transcript, note, or ebook/long report.
- OCR recommendation and text quality warnings.

### `kbprep-prepare`

Single-file conversion and cleaning pipeline.

When the source came from a known site, export, or platform, pass provenance so source-scoped cleanup can stay narrow:

```bash
kbprep-prepare --input ./source.md --output ./.kbprep/source --source-url "https://example.com/course/lesson-1" --source-domain "example.com" --site-name "Example Course"
```

For converter-backed formats such as PDF, Word, PPT, Excel, EPUB, and images, KBPrep first preserves the original file, then validates obvious container problems before invoking the heavy converter. A corrupted or mislabeled `.docx`, `.pptx`, `.xlsx`, or `.epub` fails with `E_CONVERT_INPUT_INVALID` and must not publish `cleaned.md` or `latest.json`.

For saved HTML, Markdown notes, modern Office XML, and EPUB sources, image references are not treated as disposable decoration. Local or embedded image assets should be copied into `images/` and the Markdown should point at those portable paths. Links in HTML/EPUB should remain Markdown links.

Modes:

- `rules_only`: deterministic conversion and conservative cleaning.
- `rules_plus_review_pack`: also writes `review_pack.json` for AI or human review.
- `ai_review`: asks a caller-injected generic review backend to classify review-pack blocks, then applies a guarded JSON Patch. Text cannot be rewritten.

Use `ai_review` only when contextual judgment matters, such as deciding whether "platform", "account", "side project", "group", or "community" is real tutorial content or marketing pollution.

### `kbprep-apply-review`

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

### `kbprep-feedback`

Records review feedback as a proposed cleanup rule.

Use it when the user says:

- this kind of pollution should be deleted next time
- this was mistakenly deleted and should be protected
- this pattern should be reviewed before publication

`kbprep-feedback` writes `.kbprep/rules/user/proposed_rules.jsonl` in the current project by default. It must not directly affect future runs until the proposal is reviewed and promoted with `kbprep-feedback --accept-proposal <id|latest>`. Promotion validates proposal examples and counterexamples first; a rule that would match a counterexample is rejected instead of being loaded. When evidence supports it, the failed acceptance response appends a narrower follow-up proposal to review. Promoted rules are stored in `.kbprep/rules/user/accepted_rules.jsonl` and loaded by deterministic cleanup.

When a broad discard proposal hits counterexamples and the affected run has a detected document type, the follow-up proposal is narrowed to that `document_type`. Review that narrower proposal instead of accepting the broad one.

Use `--scope source_pattern --source-pattern "<source-fragment>"` when the feedback should apply only to a specific source family, site export, domain, or filename pattern. `source_pattern` matches source identity, not body text. Source identity always includes input path, source path, and file name; when `kbprep-prepare` receives provenance, it can also include `source_url`, `source_domain`, and `site_name`. Use keyed patterns such as `source_domain:example.com` when the rule must only match one identity field. `pattern` still matches the body text to discard, review, or protect.

When the same feedback pattern appears in multiple runs, KBPrep should prefer a narrow repeated-feedback proposal using shared `source_identity` fields such as `source_domain` or `site_name` before falling back to filename prefixes. Do not promote repeated feedback as a broad `user` or `global` rule unless the user explicitly accepts that blast radius.

Portable learned rules may also live in the packaged skill/rules directory:

```text
rules/user/
  proposed_rules.jsonl
  accepted_rules.jsonl
  rejected_rules.jsonl
```

The packaged `rules/user/accepted_rules.jsonl` file is loaded by deterministic cleanup and is included in `npm run pack:check`. Keep it empty by default for a clean public package; copy only reviewed, reusable accepted rules there when intentionally distributing a customized skill.

Prefer `kbprep-feedback --accept-proposal <id|latest> --rerun-after-accept` when the original run came from `kbprep-prepare`. The rerun verification proves whether the new rule removed discard patterns or preserved protect patterns in `cleaned.md`. If rerun metadata is unavailable, report that gap instead of claiming the feedback rule is proven.

If the user rejects a proposal, run `kbprep-feedback --reject-proposal <id|latest> --reject-reason "<reason>"`. Rejected proposals are stored in `.kbprep/rules/user/rejected_rules.jsonl`; they are feedback memory only and must not be loaded as cleanup rules.

When repeated accepted feedback belongs to the same document type, use `kbprep-feedback --suggest-dictionary-updates --rules-dir ./.kbprep/rules/user` to generate review-only `dictionary_suggestions.jsonl`. Before promoting more rules, run `kbprep-feedback --summarize-promotion-history --target-rules-dir ./rules` and check failed or unverified document types. Promote only after review with `kbprep-feedback --promote-dictionary-suggestion --document-type <type> --confirm-dictionary-update --rerun-after-promotion --rules-dir ./.kbprep/rules/user --target-rules-dir ./rules`. If failed promotion history exists, do not continue unless the user explicitly approves `--allow-failed-promotion-history` after reviewing failed regression samples. After fixing failed samples, run `kbprep-feedback --resolve-promotion-failures --document-type <type> --confirm-failure-resolved --representative-run-dir <dir> --target-rules-dir ./rules`; only a passing rerun should append a resolution record. The promotion must report representative rerun results and append `promotion_history.jsonl`; if rerun provenance is missing, say the dictionary was written but regression proof is unavailable.

### `kbprep-cleanup`

Removes intermediate artifacts after the user accepts a result. It must never delete the source file or the profile-specific final deliverable.

Actions:

- `finalize`: keep the final deliverable plus a tiny manifest under `output_root`; delete process/audit files such as `runs/`, `original/`, `converted.md`, `blocks.jsonl`, `discarded.md`, `review_needed.md`, `quality_report.json`, `parts/`, `images/`, and batch process files. In curated mode, keep `obsidian/`; in standard mode, keep the source-side Markdown/assets.
- `expired`: remove old run history, defaulting to older than 7 days.
- `all`: remove known intermediate artifacts without checking acceptance state.

If `review_needed.md` still has content, `finalize` should stop unless `confirm_review_needed=true` is explicitly provided.

### `kbprep-batch`

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

For `profile="curated_obsidian_kb"`, the final deliverable is `obsidian/`, entered through `obsidian/00-索引.md`; `final_md` is intentionally `null`. For `profile="standard"`, the final deliverable is the source-side final Markdown. After `kbprep-cleanup --action finalize`, only the final deliverable and a small manifest such as `kbprep_manifest.json` or `kbprep_batch_manifest.json` should remain.

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
