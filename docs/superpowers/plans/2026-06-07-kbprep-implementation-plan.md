# KBPrep Quality Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the missing quality-loop and self-evolving cleaning-dictionary system behind the host-neutral CLI.

**Architecture:** Add small worker modules with explicit responsibilities: converter capabilities, rule dictionaries, document type classification, quality loop orchestration, and feedback rule proposals. Keep AI review as a patch protocol; never make the core depend on a named agent.

**Tech Stack:** Python worker, JSON/JSONL rule stores, TypeScript CLI bridge, Vitest integration tests, existing MinerU/PyMuPDF conversion routes.

---

### Task 1: Capability Registry

**Files:**
- Create: `python/kbprep_worker/converter_capabilities.py`
- Modify: `python/kbprep_worker/diagnose/`
- Modify: `python/kbprep_worker/cli.py`
- Test: `src/worker.test.ts`

- [x] Add a `Capability` record with `source_type`, `extensions`, `route`, `dependencies`, `fallback`, `status`, and `preserves`.
- [x] Make `diagnose` include the chosen capability and reason.
- [x] Record selected capability in `diagnosis_report.json`.
- [x] Validate `docs/capability-matrix.md` against converter declarations during package checks.
- [x] Require capability declarations and the matrix to include named test evidence for verified claims.
- [x] Record actual conversion and fallback decisions in `conversion_report.json.route_decision`.
- [x] Make QR/CTA text pollution diagnosis use cleaning dictionaries instead of hardcoded regexes.
- [x] Move source title wrapper filters into `rules/base/title_filters.json`.
- [x] Add CLI exposure through `diagnose` output.
- [x] Test Markdown, code, PDF text layer, scanned PDF route, and unsupported binary media.

### Task 2: Rule Dictionary Loader

**Files:**
- Create: `python/kbprep_worker/rule_schema.py`
- Create: `python/kbprep_worker/rule_loader.py`
- Create: `rules/base/obvious_noise.json`
- Create: `rules/document_types/course.json`
- Create: `rules/templates/self_media_course.json`
- Test: `src/worker.test.ts`

- [x] Define rule fields and allowed actions.
- [x] Validate every loaded rule.
- [x] Record provenance on every applied rule.
- [x] Move image pollution/protection indicators into dictionaries.
- [x] Fail loudly on malformed project/user rules.
- [x] Test that template rules are inactive unless selected.

### Task 3: Document Type Classifier

**Files:**
- Create: `python/kbprep_worker/document_type.py`
- Modify: `python/kbprep_worker/stages/pipeline.py`
- Test: `src/worker.test.ts`

- [x] Classify at least `report`, `course`, `transcript`, `webpage`, `ebook`, `code`, and `unknown`.
- [x] Load document type format hints and content patterns from `rules/base/document_type_signals.json`.
- [x] Return reasons and confidence.
- [x] Use classifier output to select dictionaries.
- [x] Record document type detection in both `quality_report.json` and `run_metadata.json`.
- [x] Test that a normal report does not load course/self-media cleanup.

### Task 4: Quality Loop Controller

**Files:**
- Create: `python/kbprep_worker/quality_loop.py`
- Modify: `python/kbprep_worker/stages/pipeline.py`
- Modify: `python/kbprep_worker/prepare_publish.py`
- Test: `src/worker.test.ts`

- [x] Add named gates: `conversion_integrity`, `cleanup_safety`, `review_safety`, `export_readiness`.
- [x] Convert current `quality_report.json` checks into gate results.
- [x] Make CTA/QR pollution quality checks use the same cleaning dictionaries as cleanup.
- [x] Add direct text source-to-`converted.md` integrity evidence in `source_conversion_integrity.json`.
- [x] Add converted Markdown structure integrity checks for headings, tables, code blocks, and image references.
- [x] Block publish/export when strict errors remain.
- [x] Delay run-level Obsidian vault rendering until strict quality gates pass.
- [x] Add full `prepare` regression tests for lost source headings/tables and unsafe protected-body deletion.
- [x] Exclude strict-error runs from same-config cache reuse.
- [x] Emit `next_actions` summaries and executable `quality_tasks` cleanup/review task packages when gates fail.
- [x] Add configurable max iteration count.

### Task 5: Generic Review Protocol

**Files:**
- Modify: `src/adapters/ai_review/index.ts`
- Modify: `src/aiReview.ts`
- Modify: `python/kbprep_worker/prepare_artifacts.py`
- Test: `src/index.test.ts`
- Test: `src/worker.test.ts`

- [x] Keep `review_pack` host-neutral.
- [x] Validate AI/human patches before applying.
- [x] Mark `review_safety` checked after guarded patch application and quality rerun.
- [x] Remove named agent backend values from runtime config.
- [x] Add release-check guard against concrete agent backend names in runtime code.
- [x] Add tests with a fake external backend and malformed patch rejection.

### Task 6: Feedback Rule Proposals

**Files:**
- Create: `python/kbprep_worker/feedback.py`
- Modify: `python/kbprep_worker/cli.py`
- Create: `rules/user/proposed_rules.jsonl`
- Test: `src/worker.test.ts`

- [x] Parse user feedback plus run artifacts.
- [x] Generate discard/protect/review rule proposals.
- [x] Load feedback action intent terms from cleaning dictionaries instead of Python regex constants.
- [x] Require confirmation before promotion.
- [x] Test rerun behavior after accepting a rule.
- [x] Test that rejected rules are remembered but inactive.
- [x] Parse run artifacts enough to attach artifact context, examples, and body-text counterexamples.
- [x] Block acceptance when a proposed rule misses examples or matches counterexamples.
- [x] Use run artifacts to create a narrower literal follow-up proposal when broad discard rules hit counterexamples.
- [x] Load project-local `.kbprep/rules/user/accepted_rules.jsonl` without requiring environment variables.
- [x] Package empty `rules/user/*.jsonl` slots and load reviewed packaged accepted rules for customized skills.
- [x] Add `--rerun-after-accept` verification for accepted feedback rules when the affected source can be located from `latest.json`.
- [x] Reconstruct reruns for failed runs from `run_metadata.json` when `latest.json` is unavailable.
- [x] Apply accepted `source_pattern` feedback rules only when the current input source matches.
- [x] Use run artifacts to narrow broad proposals into safer document-type scoped follow-up rules.
- [x] Use run artifacts to narrow broad proposals into safer regex/source-pattern rules.

### Task 7: Obsidian Export Generalization

**Files:**
- Modify: `python/kbprep_worker/obsidian_kb/`
- Create: `rules/templates/obsidian_course_kb.json`
- Test: `src/worker.test.ts`

- [x] Make the default Obsidian export generic.
- [x] Move `认知/方法/案例` style terms and course/self-media curation terms into an optional template file.
- [x] Preserve source trace and quality report in the exported folder.
- [x] Test default output and template output separately.

### Task 8: Verification And Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/capability-matrix.md`
- Modify: `docs/quality-loop.md`
- Modify: `docs/feedback-learning.md`
- Modify: `.github/workflows/ci.yml`

- [x] Run `npm run build`.
- [x] Run `npx tsc -p tsconfig.json --noEmit`.
- [x] Run `npm test`.
- [x] Run `npm run pack:check`.
- [x] Check that README claims match the capability matrix and tests.

