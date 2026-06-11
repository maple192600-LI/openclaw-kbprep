# KBPrep Agent Notes

KBPrep is a local CLI project. Do not add business logic for a specific AI development agent host.

## Product Stage

Treat this project as a local self-use tool unless the owner explicitly changes the stage. Keep the main demo path stable, recoverable, and easy to verify. Do not expand it into a SaaS, cloud service, payment system, multi-tenant app, or complex permission system without owner approval.

## Highest Development References

These two files are the highest project development references:

1. `docs/kbprep-core-flow-design.md`
2. `docs/kbprep-full-flowchart.html`

The Markdown design document defines the development rules, quality gates, data artifacts, and acceptance standards. The HTML flowchart defines the end-to-end operating flow. When code, older docs, or plans conflict with these two files, treat the two files as the target direction and make the gap explicit before changing implementation.

Do not edit either file unless the owner explicitly orders it. Read them as references only.

## Project Goal

KBPrep converts local source files into clean, traceable Markdown for Obsidian or LLM knowledge-base workflows.

The intended pipeline is:

1. Detect file type and choose the best conversion route.
2. Convert to Markdown without losing source details.
3. Compare converted output with source evidence and report loss risk.
4. Classify document type.
5. Apply deterministic cleanup from rule dictionaries.
6. Use AI or human review only through review packs and guarded metadata patches.
7. Recheck quality before publishing the final Markdown or Obsidian deliverable.
8. Record user feedback as rule proposals before promotion.

The current development metric is not "produces Markdown once." The metric is that each change preserves the core quality loop: convert first, verify conversion, split when needed, clean with rules and protection rules, validate each block, generate repair tasks or rule proposals on failure, rerun only affected parts, then merge and publish only after final checks pass.

## Boundaries

- Do not create AI development agent host adapter code in this repository.
- Provide CLI commands, core flow docs, and package/runtime docs only.
- Let each calling environment package this project with its own external tooling.
- Do not hardcode self-media, platform, author, or course-brand cleanup in Python logic. Put reusable cleanup knowledge in `rules/`.
- Do not build OCR from scratch. Use the existing converter/OCR route and keep its quality evidence auditable.
- Do not let any tool path bypass the quality gates and write a final result directly.
- Do not treat user feedback as an accepted long-term rule until scope, positive evidence, negative examples, and owner or maintainer confirmation are recorded.

## Change Protocol

Before editing code, explain to the owner:

- What will change.
- Why it is needed.
- Which working feature or demo path could be affected.
- Whether there is a lighter alternative.

Keep each task small and reversible. Do not refactor unrelated code. For file, data, OCR, conversion, cleanup, or feedback-learning work, be extra conservative: preserve source evidence, audit discarded content, and make failure reasons understandable to a non-developer.

## Verification

After each implementation change, verify the affected demo path. Prefer existing commands when relevant:

## Main Commands

- `npm run dev:check`
- `npm run build`
- `npm test`
- `npm run pack:check`
- `npm run dev:full-check`

Use `kbprep-feedback` for review feedback. It writes proposed rules first. Only an explicit `kbprep-feedback --accept-proposal <id|latest>` may promote a proposal into accepted user cleanup rules.

If automated tests are not enough for the change, provide manual acceptance steps in product terms: how to start, what to upload or type, where to click or which CLI command to run, what success should look like, and which error text the owner should send back if it fails.

## Project Guardrails

- Run `npm run dev:check` for documentation, configuration, packaging, and narrow implementation changes.
- Run `npm run dev:full-check` for converter routes, quality gates, cleanup lifecycle, feedback promotion, release, dependency, or runtime changes.
- `npm run pack:check` also verifies protected design documents, project governance wiring, capability matrix drift, hardcoded cleanup terms, agent-independent runtime boundaries, audit guard checks, thresholds, and npm package contents.
- Do not claim a KBPrep output is accepted unless `quality_report.json` has no strict errors and the successful run published the expected `latest_outputs`.
- Do not promote a `partial` or `unsupported` capability to `verified` without golden fixtures and named test evidence in `python/kbprep_worker/converter_capabilities.py`.
- If a check cannot run, report the exact command, the reason it could not run, and the remaining manual acceptance steps.
