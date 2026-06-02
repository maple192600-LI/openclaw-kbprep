# Curated Obsidian KB Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `curated_obsidian_kb` profile that turns cleaned source documents into a text-first Obsidian wiki while removing author/identity/marketing noise without rewriting source knowledge paragraphs.

**Architecture:** Keep the existing conversion pipeline intact. Add a post-cleaning curation layer that only changes block metadata/status and generated heading display text, then render an `obsidian/` folder with index, full body, topic notes, and audit files.

**Tech Stack:** TypeScript OpenClaw plugin entry, Python `kbprep_worker` pipeline, Vitest integration tests, Obsidian Markdown output conventions.

---

### Task 1: Lock Behavior With Tests

**Files:**
- Modify: `src/worker.test.ts`

- [x] Add a focused Python-module test for `apply_curated_obsidian_policy()` and `render_obsidian_vault()`.
- [x] Verify the test fails before the new module exists.
- [x] Add a main-pipeline integration test for `kbprep_prepare(..., profile="curated_obsidian_kb")`.
- [x] Verify the integration test fails before pipeline wiring exists.

### Task 2: Add Curated Obsidian Policy And Renderer

**Files:**
- Create: `python/kbprep_worker/obsidian_kb.py`
- Modify: `python/kbprep_worker/render_outputs.py`

- [x] Implement author bio and identity wrapper detection.
- [x] Drop image-only artifacts for text-first KB output.
- [x] Sanitize generated heading display text by removing author/name prefixes.
- [x] Render `obsidian/00-索引.md`, `01-完整正文.md`, `认知/`, `方法/`, `案例/`, and `_audit/`.
- [x] Keep source knowledge paragraphs verbatim.
- [x] Write `source-map.jsonl` for block-to-note traceability.

### Task 3: Wire The Profile Through The Plugin

**Files:**
- Modify: `python/kbprep_worker/prepare.py`
- Modify: `python/kbprep_worker/quality.py`
- Modify: `python/kbprep_worker/apply_patch.py`
- Modify: `src/index.ts`
- Modify: `src/aiReview.ts`

- [x] Apply curated policy after ordinary block/image cleaning.
- [x] Publish `obsidian/` into both run and latest outputs.
- [x] Make quality gates treat intentional author/image removal as known non-body pollution.
- [x] Re-render Obsidian outputs after guarded review patches.
- [x] Expose `curated_obsidian_kb` in the tool schema.
- [x] Add AI review instructions for author bios, identity wrappers, and continuity risk.

### Task 4: Verify And Document

**Files:**
- Modify: `README.md`

- [x] Document the new profile and Obsidian folder structure.
- [x] Run targeted tests for curated Obsidian behavior.
- [x] Run full `npm test`.
- [x] Run `npm run plugin:validate`.
- [x] Re-process the user's sample source with `profile="curated_obsidian_kb"` and compare against the manual-cleaned reference.

### Task 5: Tighten Against The Manual Reference

**Files:**
- Modify: `python/kbprep_worker/obsidian_kb.py`
- Modify: `python/kbprep_worker/quality.py`
- Modify: `src/worker.test.ts`

- [x] Remove table-of-contents windows and adjacent TOC headings.
- [x] Drop brand-program packaging such as super-label/course/community-operating descriptions.
- [x] Drop OCR layout tables while keeping method/data comparison tables.
- [x] Re-run the user sample and compare structural metrics against the manual-cleaned file.
