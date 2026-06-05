# KBPrep Known Issues And Roadmap

This file tracks known product and engineering gaps that are not hidden defects.

## Release 0.5.1 Hardening Closed In `codex/kbprep-0.5.1-hardening`

- `#2`: AI review now routes through a reusable backend abstraction. OpenClaw remains the default adapter; `local_rules`, `claude_code`, and `codex` are explicit backend names for future provider implementations.
- `#3`: `python/kbprep_worker/prepare.py` is now a thin orchestrator entrypoint with the heavy pipeline moved into stage modules.
- `#4`: `docs/index.html` no longer carries inline CSS; page styling lives in `docs/assets/style.css`.
- `#5`: `device_override` no longer exposes `auto`. Unset means automatic CPU/GPU selection; `cpu` and `cuda` are advanced forced overrides.
- `#6`: README/SKILL now state supported language scope, quality reports include `language_detected`, and English detail-signal/CTA handling has test coverage.
- `#7`: uv-based worker installation is documented and CI caches uv/Python dependency paths.
- `#8`: MinerU/PyMuPDF/torch constraints use compatible ranges, with scheduled dependency-upgrade CI coverage.

## Post-Release Roadmap

- Add real non-OpenClaw provider implementations behind the `AIReviewBackend` interface.
- Continue splitting `python/kbprep_worker/stages/pipeline.py` into smaller stage-specific files after the release branch is stable.
- Expand language-specific signal tests beyond the current Chinese/English coverage.

## Closed Workflow Risks

- Default `curated_obsidian_kb` delivery is intentionally Obsidian-first: `latest_outputs.final_md` stays `null`, while `latest_outputs.obsidian_dir`, `latest_outputs.obsidian_index`, and `final_artifact_type="obsidian_dir"` identify the final deliverable.
- `kbprep_cleanup(action="finalize")` must preserve the profile-specific final deliverable: `obsidian/` for curated runs, source-side Markdown/assets for standard runs.

## Adapter Naming

The project package is `kbprep`. The OpenClaw adapter/plugin id remains `openclaw-kbprep`, and the current GitHub repository slug is still `openclaw-kbprep`. Renaming the remote repository requires a GitHub repository settings change plus documentation URL updates.

## Tracked `dist`

`dist/` is intentionally committed because OpenClaw managed installs need readable JavaScript runtime files. CI now rebuilds and checks `dist` for drift so source and compiled runtime cannot silently diverge.
