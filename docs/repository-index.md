# KBPrep Repository Index

Last updated: 2026-06-07

This index is the working map for developers and AI coding agents. It describes the current repository boundary, runtime shape, source entry points, output contracts, and the checks that must pass before a change is considered safe.

## Project Boundary

KBPrep is a local document-preparation toolkit. Its job is to turn local raw source files into clean, traceable Markdown or an Obsidian-ready knowledge-base folder.

KBPrep is not a RAG indexer, remote downloader, summarizer, or final article writer. It should preserve concrete source knowledge details, remove obvious pollution, and keep discarded or uncertain content auditable.

KBPrep does not ship host-specific agent adapter logic. Claude Code, Codex, OpenClaw, Hermes, or another AI coding host should call the standalone CLI and package `skills/kbprep/SKILL.md` using that host's own skill/plugin creator.

## Quick Facts

- Runtime package: Node.js ESM package, Node `>=22`.
- Core worker: Python package under `python/kbprep_worker`.
- Main host surfaces: standalone Node CLI and direct Python worker CLI.
- Default output profile: `standard`.
- Default final deliverable: source-side Markdown beside the source file.
- Generic Obsidian deliverable: `output_root/obsidian/` when `profile="obsidian_kb"`.
- Legacy course/self-media Obsidian template: `output_root/obsidian/` when `profile="curated_obsidian_kb"`.
- Tests: Vitest for TypeScript behavior and Python worker smoke tests in CI.
- Build output: committed `dist/`, required by npm-installed CLI usage.
- Internal packaging exclusion: `docs/.npmignore` excludes `docs/kbprep-project-map-report.html` from npm packages.

## Architecture

```text
Standalone CLI commands
        |
        v
src/adapters/standalone/
        |
        v
src/worker.ts
        |
        v
python -m kbprep_worker.cli <command> --json-stdin
        |
        v
python/kbprep_worker/* pipeline modules
        |
        v
output_root audit files + profile-specific final deliverable
```

The TypeScript layer is a host/CLI adapter and subprocess bridge. The deterministic conversion, cleaning, quality, batch, and cleanup logic lives in Python.

## Primary Entry Points

| Path | Responsibility |
| --- | --- |
| `src/index.ts` | Package entry. Exports host-neutral CLI/runtime helpers. |
| `src/adapters/standalone/cli.ts` | Shared standalone CLI command implementation. |
| `src/adapters/standalone/bin/*.ts` | Executable wrappers for `kbprep-preflight`, `kbprep-analyze`, `kbprep-prepare`, `kbprep-apply-review`, `kbprep-feedback`, `kbprep-cleanup`, and `kbprep-batch`. |
| `src/worker.ts` | Spawns `python -m kbprep_worker.cli`, passes JSON stdin, captures JSON stdout, logs stderr JSONL, handles timeout/cancel/error envelopes. |
| `src/runtime/pythonRuntime.ts` | Creates and resolves the package-local `.kbprep/venv` runtime and runtime marker. |
| `src/runtime/subprocess.ts` | Shared managed subprocess runner for worker, runtime setup, and external AI review command timeout behavior. |
| `python/kbprep_worker/cli.py` | Python command dispatcher for `setup-env`, `preflight`, `diagnose`, `prepare`, `apply-review`, `feedback`, `prepare-batch`, and `cleanup`. |

## Standalone CLI Surface

The npm package exposes these binaries:

- `kbprep-preflight`
- `kbprep-analyze`
- `kbprep-prepare`
- `kbprep-apply-review`
- `kbprep-feedback`
- `kbprep-cleanup`
- `kbprep-batch`

The standalone CLI is the primary and recommended interface. AI coding hosts should call it instead of relying on repository-maintained host adapters.

## Python Pipeline Map

The public `python/kbprep_worker/prepare.py` module is a compatibility entrypoint. The single-file prepare implementation is in `python/kbprep_worker/stages/pipeline.py`.

Current single-file stage order:

1. `env_check`: check runtime readiness for the selected profile.
2. `original_preserve`: hash and preserve the original file.
3. `diagnose`: detect source type and conversion route.
4. `convert`: direct text, Office XML, EPUB, PDF text layer, or MinerU/OCR conversion.
5. `normalize`: normalize converted Markdown.
6. `blockify`: turn text into traceable ordered blocks.
7. `classify_blocks`: classify block type and protection metadata.
8. `clean_rules`: apply deterministic cleaning rules.
9. `image_clean`: handle image artifacts and references.
10. `render_outputs`: write cleaned, discarded, review, evidence, and profile outputs.
11. `split`: create chunks/parts for long outputs.
12. `quality_check`: write `quality_report.json`, strict errors, warnings, runtime metadata, and language signals.
13. `publish_latest_outputs`: publish top-level latest files only after successful quality gates.

## Key Python Modules

| Path | Responsibility |
| --- | --- |
| `python/kbprep_worker/preflight.py` | Runtime readiness checks and device/runtime reporting. |
| `python/kbprep_worker/diagnose/` | Source type and quality diagnosis package: format/text helpers, PDF analysis, and runtime-facing command entry points. |
| `python/kbprep_worker/detect.py` | Lightweight source family detection. |
| `python/kbprep_worker/pdf_text.py` | PDF text-layer conversion fast path. |
| `python/kbprep_worker/mineru_adapter.py` | MinerU/OCR conversion integration. |
| `python/kbprep_worker/prepare_runtime.py` | Runtime snapshots, cache keys, and converter environment checks. |
| `python/kbprep_worker/prepare_diagnosis.py` | Diagnosis reports and source-title derivation for rendering. |
| `python/kbprep_worker/render_outputs.py` | Standard cleaned/discarded/review output rendering. |
| `python/kbprep_worker/obsidian_kb/` | Obsidian curation/output package. `__init__.py` is a compatibility export facade; `context.py` carries explicit template context; `policy.py` orchestrates curation; `signals.py` owns predicates; `body_notes.py` renders vault files; `titles.py`, `frontmatter.py`, and `links.py` carry formatting helpers. |
| `python/kbprep_worker/quality/` | Quality gate package: runner orchestration, conversion integrity, cleanup safety, retention, Markdown signal helpers, thresholds, and gate artifacts. |
| `python/kbprep_worker/feedback/` | Feedback learning package: rule proposals, accept/reject flow, source-scope inference, dictionary suggestions, promotion history, and rerun verification. |
| `python/kbprep_worker/apply_patch.py` | Guarded review metadata patching. |
| `python/kbprep_worker/prepare_batch.py` | Directory scan, sample-first batch processing, progress/results/failures output. |
| `python/kbprep_worker/cleanup.py` | Finalize/expired/all cleanup lifecycle without deleting source files or accepted final deliverables. |

## Output Contract

Successful runs write audit/process files under `output_root` and publish a profile-specific final deliverable.

Common process and audit files:

```text
output_root/
  original/
  converted.md
  conversion_report.json
  blocks.jsonl
  cleaned.md
  discarded.md
  review_needed.md
  images/
  audit.md
  quality_report.json
  latest.json
  runs/<run_id>/
```

Generic Obsidian output:

```text
output_root/obsidian/
  00-索引.md
  <source-title>.md
  Notes/
  _audit/
```

Generic `profile="obsidian_kb"` output uses `rules/templates/obsidian_generic.json` by default.

Legacy `profile="curated_obsidian_kb"` output keeps the optional course/self-media categories from `rules/templates/obsidian_course_kb.json`, such as `认知/`, `方法/`, and `案例/`.

For `profile="obsidian_kb"`, callers must use `latest_outputs.final_artifact_type="obsidian_dir"`, `latest_outputs.obsidian_dir`, `latest_outputs.obsidian_index`, and `latest_outputs.obsidian_complete`. `latest_outputs.final_md` is intentionally `null`.

For `profile="curated_obsidian_kb"`, callers must use `latest_outputs.final_artifact_type="obsidian_dir"`, `latest_outputs.obsidian_dir`, `latest_outputs.obsidian_index`, and `latest_outputs.obsidian_complete`. `latest_outputs.final_md` is intentionally `null`.

For `profile="standard"`, callers must use `latest_outputs.final_artifact_type="markdown"` and `latest_outputs.final_md`.

`cleaned.md` alone is process material. It is not proof that the run is accepted.

## Batch Contract

`kbprep-batch` scans a directory, ignores dependency/build/cache/runtime folders, runs a representative sample first, and stops if the sample fails. Each source file gets its own output root under:

```text
<batch_output_root>/files/<source-stem>_<hash>/
```

Batch acceptance should read `results.json`, not a top-level `cleaned.md`.

Obsidian-profile batch successes include `final_artifact_type="obsidian_dir"`, `batch_obsidian_dir`, `batch_obsidian_index`, and usually `batch_obsidian_complete`. Standard successes include `final_artifact_type="markdown"` and `batch_final_md`.

## Cleanup Contract

`kbprep-cleanup --action finalize` keeps the accepted final deliverable and a small manifest. It removes process/audit material only after acceptance.

It must stop when `review_needed.md` still has content unless `confirm_review_needed=true` is explicitly provided. That flag is an acceptance override, not a normal shortcut.

In curated mode, finalize preserves `obsidian/`. In standard mode, finalize preserves the source-side Markdown and assets.

## AI Review Contract

The AI review path must flow through `AIReviewBackend` and the review pipeline. AI or human review may only patch block metadata such as `status`, `risk_tags`, `reason`, and `confidence`.

Review must not rewrite source text, remove trace metadata, or bypass protected blocks such as operation steps, prompts, code, tables, concrete examples, links, parameters, and numbers.

## Directory Map

| Path | Meaning |
| --- | --- |
| `.github/workflows/` | CI, Python matrix smoke checks, dependency upgrade schedule. |
| `AGENTS.md` | Agent-neutral project instructions for Codex and other AI coding tools. |
| `dist/` | Compiled JavaScript runtime committed for npm-installed CLI usage. |
| `docs/` | Public docs, operator workflows, known issues, showcase page, and this repository index. |
| `docs/install/` | Host-specific installation notes only; no host adapter business logic. |
| `docs/superpowers/plans/` | Implementation plans and project governance notes. |
| `python/kbprep_worker/` | Core deterministic worker implementation. |
| `scripts/` | Package and docs helper scripts. |
| `skills/kbprep/` | Operator skill shipped with the package. |
| `src/` | TypeScript package entry, standalone CLI, worker bridge, runtime helpers, and tests. Worker scenario tests live in `src/test/scenarios/*.test.ts`; `src/test/helpers/workerHarness.ts` carries the shared Python/fixture harness. |

## Packaging Boundary

`package.json` includes the runtime files needed by installed users: `dist/`, Python worker files, rule dictionaries, skill files, public docs, README, changelog, license, and package metadata.

Do not package local dependency folders, local Python runtimes, raw source documents, generated conversion outputs, or internal review reports. `docs/kbprep-project-map-report.html` stays in the repository as internal review material but is excluded from npm packages by `docs/.npmignore`.

## Development Commands

Use these from the repository root:

```bash
npm test
npm run build
npx tsc -p tsconfig.json --noEmit
npm run pack:check
```

For docs preview:

```bash
npm run docs:serve
```

For direct Python worker smoke testing:

```bash
python -m kbprep_worker.cli preflight --json-stdin
python -m kbprep_worker.cli diagnose --json-stdin
python -m kbprep_worker.cli prepare --json-stdin
```

The Python commands require JSON input on stdin and the correct Python environment.

## CI Map

`.github/workflows/ci.yml` runs on pull requests, pushes to `main`, scheduled dependency checks, and manual dispatch. The main CI job uses Node 22 and Python 3.12, installs Python worker dependencies with `uv`, and runs:

- `npm ci`
- `npm run build`
- `npx tsc -p tsconfig.json --noEmit`
- `npm test`
- `npm run pack:check`
- standalone CLI smoke checks
- Python worker smoke checks

There is also a Python help/import matrix across Python 3.10 through 3.13.

## Where To Look

| Need | Start here |
| --- | --- |
| Standalone CLI behavior | `src/adapters/standalone/cli.ts`, `src/adapters/standalone/bin/` |
| Worker subprocess failures | `src/worker.ts`, `src/runtime/subprocess.ts`, stderr JSONL logs under output root |
| Runtime/Python/MinerU setup | `src/runtime/pythonRuntime.ts`, `src/runtime/subprocess.ts`, `python/kbprep_worker/preflight.py`, `python/kbprep_worker/prepare_runtime.py` |
| Source diagnosis problems | `python/kbprep_worker/diagnose/`, `python/kbprep_worker/detect.py` |
| PDF conversion quality | `python/kbprep_worker/pdf_text.py`, `python/kbprep_worker/mineru_adapter.py`, `quality_report.json` |
| Marketing/noise cleanup | `python/kbprep_worker/obsidian_kb/`, `python/kbprep_worker/quality/cleanup_safety.py`, `rules/` |
| Generic Obsidian template behavior | `python/kbprep_worker/obsidian_template.py`, `rules/templates/obsidian_generic.json` |
| Bad title or generic note name | `python/kbprep_worker/prepare_diagnosis.py`, `python/kbprep_worker/obsidian_kb/` |
| Missing final deliverable | `python/kbprep_worker/prepare_artifacts.py`, `python/kbprep_worker/cleanup.py`, `latest.json` |
| Batch behavior | `python/kbprep_worker/prepare_batch.py`, `results.json`, `failures.json`, `progress.json` |
| Package contents | `package.json`, `docs/.npmignore`, `scripts/check-pack.mjs` |
| Operator acceptance rules | `skills/kbprep/SKILL.md`, `docs/kbprep-operator-workflows.md` |
| Agent install instructions | `docs/install/` |

## Review Checklist For Future Changes

Before accepting a change, verify:

- The change keeps KBPrep host-neutral and does not add host adapter business logic.
- Source-side, top-level, run-level, and Obsidian outputs still mean different things.
- Obsidian-profile callers do not consume `cleaned.md` or expect `final_md`.
- Source-derived titles are used for complete Obsidian body notes; generic names like `01-完整正文.md` must not reappear.
- Marketing, author, CTA, and wrapper cleanup does not discard concrete method/case/tool/detail content silently.
- Any discarded or uncertain content remains inspectable in `discarded.md`, `review_needed.md`, or `obsidian/_audit/`.
- Quality gates check converted/OCR output when a bad PDF text layer is superseded.
- Batch processing keeps sample-first safety and per-file outputs.
- Cleanup never deletes the source file or an accepted final deliverable.
- Tests, docs, and `dist/` stay aligned with source changes.
