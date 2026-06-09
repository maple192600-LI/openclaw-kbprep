# KBPrep Target Gap Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the repository with KBPrep as a file-to-Obsidian-Markdown quality-loop CLI, not an agent adapter or self-media-specific cleaner.

**Architecture:** Keep the maintained surface host-neutral: Node CLI, Python worker, conversion registry, cleaning dictionaries, quality loop, review protocol, and feedback learning. Move domain-specific cleanup out of Python constants into rule dictionaries with provenance.

**Tech Stack:** TypeScript ESM CLI bridge, Python worker modules, Pytest/Vitest, MinerU, PyMuPDF, Obsidian Markdown outputs.

---

### Task 1: Prove The Current Boundary

**Files:**
- Modify: `README.md`
- Modify: `package.json`
- Modify: `src/index.ts`
- Modify: `.github/workflows/ci.yml`
- Create/modify: `docs/agent-neutral.md`

- [x] Remove host plugin dependency, manifest, scripts, and root exports.
- [x] Build with `npm run build`.
- [x] Run `npx tsc -p tsconfig.json --noEmit`.
- [x] Run `npm test`.
- [x] Confirm runtime/package code stays agent-neutral with `node scripts/check-agent-neutral-runtime.mjs`.

### Task 2: Stop Overclaiming File Support

**Files:**
- Create/modify: `docs/capability-matrix.md`
- Modify: `python/kbprep_worker/supported_formats.py`
- Modify: `python/kbprep_worker/diagnose/`
- Test: `src/worker.test.ts`

- [x] Create converter declarations for each supported source type.
- [x] Include route, dependency, fallback, preserve evidence, and current status.
- [x] Generate or validate `docs/capability-matrix.md` from declarations.
- [x] Require named test evidence in both converter declarations and `docs/capability-matrix.md`.
- [x] Add tests that unsupported formats are reported instead of silently accepted.
- [x] Record actual conversion and fallback decisions in `conversion_report.json.route_decision`.

### Task 3: Remove Hardcoded Domain Cleanup

**Files:**
- Modify: `python/kbprep_worker/clean_rules.py`
- Modify: `python/kbprep_worker/classify_blocks.py`
- Modify: `python/kbprep_worker/obsidian_kb/`
- Create: `rules/base/*.json`
- Create: `rules/document_types/*.json`
- Create: `rules/templates/*.json`
- Test: `src/worker.test.ts`

- [x] Move platform, self-media, course, and source-brand terms out of Python constants.
- [x] Load generic base rules by default.
- [x] Load domain templates only when selected by profile or classifier.
- [x] Add tests that domain/template rules are inactive unless selected.
- [x] Add release-check guard against reintroducing platform/marketing cleanup terms into Python worker logic.
- [x] Move document-type classification keyword signals out of Python regexes into a JSON dictionary.

### Task 4: Promote Quality Detection Into A Loop

**Files:**
- Modify: `python/kbprep_worker/stages/pipeline.py`
- Modify: `python/kbprep_worker/quality/`
- Create/modify: `docs/quality-loop.md`
- Test: `src/worker.test.ts`

- [x] Add conversion integrity checks for converted headings, tables, code blocks, and image references.
- [x] Add direct text source-to-converted Markdown integrity evidence.
- [x] Add cleanup safety gate after deterministic cleanup.
- [x] Add review safety gate after applying AI/human patches.
- [x] Report named quality gates and next actions in `quality_report.json`.
- [x] Block latest/source-side/Obsidian publication on strict quality errors.
- [x] Prevent failed same-config runs from being reused as successful cache hits.
- [x] Add tests for missing heading/table structure loss and normal structure preservation.
- [x] Add tests for export blocking after unsafe deletion and strict quality errors.

### Task 5: Add Feedback Learning

**Files:**
- Modify: `python/kbprep_worker/cli.py`
- Create: `python/kbprep_worker/feedback.py`
- Create: `python/kbprep_worker/rules.py`
- Create/modify: `docs/feedback-learning.md`
- Test: `src/worker.test.ts`

- [x] Add `feedback` command.
- [x] Read run artifacts and feedback text.
- [x] Produce rule proposals.
- [x] Require confirmation before accepted rules affect future runs.
- [x] Keep packaged `rules/user/*.jsonl` slots available for customized skill rule memory.
- [x] Apply accepted `source_pattern` feedback rules only to matching input source paths/names.
- [x] Add tests for proposed-only feedback, accepted discard, and accepted protect behavior.
- [x] Add rejected feedback memory tests.

