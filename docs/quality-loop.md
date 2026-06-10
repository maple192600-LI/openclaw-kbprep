# Quality Loop

KBPrep's target is not "convert once and clean once". The target is a gated loop.

## Required Flow

```text
analyze source
-> select conversion route
-> convert to Markdown
-> compare converted Markdown with source evidence
-> classify document type
-> load cleaning dictionaries
-> deterministic cleanup
-> quality check 1
-> generate review_pack for semantic review when needed
-> apply validated review patch
-> quality check 2
-> if failing, produce next cleanup/review task and repeat within a configured limit
-> export to Obsidian only after passing quality gates
```

## Gate Categories

Conversion integrity:

- missing chapters or headings: currently checked from direct text sources to `converted.md`, then from `converted.md` to the block trace
- missing tables: currently checked between `converted.md` and the block trace
- missing images or image references: currently checked between `converted.md` and the block trace
- missing code blocks: currently checked between `converted.md` and the block trace
- missing links
- missing parameter assignments
- OCR/text-layer rejection evidence

The structure check ignores Markdown fenced-code contents when detecting headings,
tables, and image references, so source code comments or literals do not produce
false chapter/table loss errors.

Direct text-like sources now also emit `source_conversion_integrity.json`.
That artifact compares the original source file with `converted.md` for
headings, Markdown tables, fenced code blocks, and image references before any
cleanup is allowed to pass. This check is intentionally limited to direct text
sources such as Markdown and plain text; PDF/OCR sources still rely on
conversion reports, text-layer/OCR evidence, and downstream structure checks.
For PDF and other routed conversions, reviewers should inspect
`conversion_report.json.route_decision` to verify whether the run used the
declared route, a diagnosed PDF text layer route, or a fallback such as
`mineru_ocr`.

`quality_report.json` now records structured `quality_gates`, `next_actions`,
and `quality_tasks`.
The implementation lives under `python/kbprep_worker/quality/`: `runner.py`
keeps the public `run_quality_check` orchestration, while conversion,
cleanup-safety, retention, Markdown signal, threshold, and gate-artifact logic
stay in focused modules.
Each gate is also written as a separate audit artifact under
`quality_gates/<gate>.json`, with the gate status, strict errors, warnings,
input artifacts, execution order, and whether that gate blocks publication.
The first implemented gate set is:

- `conversion_integrity`: converted Markdown text, headings, tables, code blocks, image references, and conversion evidence
- `cleanup_safety`: pollution residue, protected block deletion, over-discarding, and final-output retention
- `splitting_integrity`: broken code fences, tables, ordered lists, and block trace issues
- `review_safety`: reserved for validated AI/human patch application
- `export_readiness`: fails whenever strict quality errors remain

Each `quality_report.json` also records `quality_loop`:

- `current_iteration`: `prepare` starts at 1; each `apply_review` rerun increments it
- `previous_iteration`: the quality iteration this report follows
- `max_iterations`: configurable, default 3
- `can_continue`: true only when strict errors remain and the configured limit has not been reached
- `status`: `passed`, `needs_iteration`, or `iteration_limit_reached`

When strict errors remain at the configured limit, KBPrep adds
`E_QUALITY_ITERATION_LIMIT`, a `stop_iteration` next action, and a
`quality_loop` task. The run remains unpublished, and the user or calling agent
must inspect `quality_report.json`, `discarded.md`, and `review_needed.md`
before changing rules or source input.

`kbprep-prepare --repair-loop` is the CLI path for the same principle when a
user wants a usable Markdown file instead of a bare stop signal. On each failed
quality pass, KBPrep writes:

- `failure_diagnosis.json`: machine-readable failure type, stage, source file,
  strict errors, and evidence
- `repair_plan.md`: plain-language diagnosis, blocked publish reason, and next
  handling step
- `repair_actions.json`: executable safe actions such as copying discoverable
  Markdown assets or restoring wrongly discarded detail blocks

The repair loop never accepts cleanup rules automatically and never publishes a
final Markdown file while strict errors remain. Pollution residue becomes a rule
proposal or manual review task; table, code, heading, and conversion loss remain
blocked unless a deterministic fallback can prove the missing evidence returned.

Python worker quality gates now include a whole-package type check. `npm run
python:typecheck` runs mypy across `python/kbprep_worker`, including untyped
function bodies, so new Python worker code cannot be hidden outside a small
allowlist. Third-party libraries without stubs are handled by targeted mypy
overrides rather than by disabling worker-wide import checking.

`next_actions` is the compact machine-readable summary of what failed.
`quality_tasks` is the executable handoff package for a user or AI coding agent.
Each task names the failed gate, goal, background, files to read, allowed and
forbidden modifications, implementation steps, risks, test commands,
acceptance criteria, review steps, rollback plan, and the gate's strict errors
and warnings. This keeps the loop from becoming a vague "try again" instruction:
the next actor knows whether to fix conversion, cleanup dictionaries, splitting,
review patch validation, export blocking, or the iteration limit root cause.

When `export_readiness` fails, prepare keeps the run audit artifacts but does not
update `latest.json`, publish source-side final outputs, or render the run-level
Obsidian vault. Failed runs are also excluded from same-config cache reuse. Each run writes
`run_metadata.json` before conversion so feedback learning can reconstruct a
rerun even when a failed run never produced `latest.json`. After blockification,
the same metadata is updated with `document_type` and
`document_type_detection`, so later feedback and reruns can reuse the detected
document category instead of guessing from the filename.
When `source_identity` is present, feedback learning also uses it before
filename-prefix guessing. Repeated feedback from the same `source_domain`,
`site_name`, `origin`, or source URL can produce a keyed `source_pattern` such
as `source_domain:example.com`, keeping source-specific cleanup narrow without
hardcoding platform terms into Python.

Cleanup safety:

- useful body text removed as pollution
- detail blocks discarded without a pollution reason
- document-type rules applied to the wrong document
- protected terms removed

Pollution residue:

- page headers/footers
- navigation crumbs
- subscription or purchase calls
- source wrappers unrelated to the document theme
- duplicated OCR fragments

Semantic review:

- AI may classify, protect, or propose deletions
- AI must not rewrite source body text as a summary
- AI output must be validated before application
- every applied operation must be rechecked by quality gates
- after `apply_review`, `quality_report.json` marks `review_safety` as checked
  only when the guarded patch application completed and quality was rerun
- concrete agent backends are not part of the core; a caller-injected reviewer
  may only return the host-neutral JSON Patch protocol, and unsafe patch fields
  are rejected before `apply_review`

## Export Rule

Obsidian export is blocked when strict quality errors remain. A run may still emit audit files for diagnosis, but the run-level Obsidian vault is rendered only after strict quality gates pass.
When the Obsidian vault is rendered, its `_audit` folder carries the run
evidence needed to verify the final note: `quality_report.json`,
`conversion_report.json`, `diagnosis_report.json`, `run_metadata.json`,
`audit.md`, `source-map.jsonl`, and `source_conversion_integrity.json` when that
source-level check exists. This keeps the final Obsidian folder reviewable even
after temporary process folders are cleaned.
The Obsidian `_audit` folder also includes the `quality_gates/` directory, so a
reviewer can inspect each gate without reconstructing the full run directory.

## Implemented Source-Specific Feedback

Repeated feedback across runs now checks structured source identity before
falling back to filename prefixes. This lets KBPrep learn that a cleanup miss
belongs to one source family or domain, while still requiring proposal review
and acceptance before the rule affects future runs.
