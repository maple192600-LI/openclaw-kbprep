# KBPrep Agent Notes

KBPrep is a host-neutral local CLI project. Do not add business logic for a specific agent host.

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

## Boundaries

- Do not create Claude Code, Codex, OpenClaw, Hermes, or other host adapter code in this repository.
- Provide CLI commands, `skills/kbprep/SKILL.md`, and installation docs only.
- Let each host or user package the skill with that host's own skill/plugin creator.
- Do not hardcode self-media, platform, author, or course-brand cleanup in Python logic. Put reusable cleanup knowledge in `rules/`.
- Do not build OCR from scratch. Use the existing converter/OCR route and keep its quality evidence auditable.

## Main Commands

- `npm run build`
- `npm test`
- `npm run pack:check`

Use `kbprep-feedback` for review feedback. It writes proposed rules first. Only an explicit `kbprep-feedback --accept-proposal <id|latest>` may promote a proposal into accepted user cleanup rules.
