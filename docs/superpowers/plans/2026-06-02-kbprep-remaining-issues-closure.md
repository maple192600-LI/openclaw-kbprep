# KBPrep Remaining Issues Closure Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining KBPrep v0.5.0 review items that were not handled by the first hardening pass.

**Architecture:** Keep the project host-decoupled without breaking the current OpenClaw adapter. Add explicit backend seams, docs, and CI guards where full external platform changes are outside the local repo.

**Tech Stack:** TypeScript ESM, Python worker modules, Vitest, GitHub Actions, npm scripts, OpenClaw plugin validation.

---

## Tasks

- [ ] Add a generic AI review backend interface and adapt the OpenClaw subagent to that interface.
- [ ] Split `diagnose/` PDF analysis into focused helper functions while preserving output keys.
- [ ] Normalize public TypeScript worker error codes to `E_*` while accepting legacy Python compatibility codes.
- [ ] Rename npm package to `kbprep` and document that `openclaw-kbprep` remains only the OpenClaw adapter/plugin id; local code cannot rename the remote GitHub repository.
- [ ] Add a CI/package guard for tracked `dist/` so committed runtime output cannot drift from TypeScript source.
- [ ] Add known-issues/roadmap documentation for current open GitHub issues and remaining large refactors.
- [ ] Expand standalone CLI docs with real command list and help examples.
- [ ] Rebuild `dist` and run full verification.

## Acceptance

- Existing OpenClaw AI review tests still pass through the new backend adapter.
- `diagnose/` has no single monolithic PDF function doing all page counting, text-health, PPT similarity, and routing logic inline.
- TypeScript worker-created errors use `E_*` names; old `KBPREP_*` names remain accepted only for compatibility.
- Package name is `kbprep`; OpenClaw adapter id remains `openclaw-kbprep` and is documented as adapter identity.
- CI checks `dist` drift after build.
- README points readers to known issues and full CLI usage.
- `npm test`, `npm run build`, `npm run plugin:validate`, and `npm run pack:check` pass.
