# KBPrep Known Issues And Roadmap

This file tracks known product and engineering gaps that are not hidden defects.

## Current Open Issues

- `#2`: migrate AI review to a reusable backend abstraction. Source now has a generic backend interface; remaining work is adding real non-OpenClaw provider adapters.
- `#3`: split `python/kbprep_worker/prepare.py` into smaller stage modules.
- `#4`: split `docs/index.html` inline CSS into separate assets.
- `#5`: simplify `device_override="auto"` semantics.
- `#6`: declare supported languages and keep improving English detail-signal regex coverage.
- `#7`: document uv install path and improve CI cache behavior.
- `#8`: replace hard dependency pins with compatible-release pins and add a scheduled upgrade-test job.

## Closed Workflow Risks

- Default `curated_obsidian_kb` delivery is intentionally Obsidian-first: `latest_outputs.final_md` stays `null`, while `latest_outputs.obsidian_dir`, `latest_outputs.obsidian_index`, and `final_artifact_type="obsidian_dir"` identify the final deliverable.
- `kbprep_cleanup(action="finalize")` must preserve the profile-specific final deliverable: `obsidian/` for curated runs, source-side Markdown/assets for standard runs.

## Adapter Naming

The project package is `kbprep`. The OpenClaw adapter/plugin id remains `openclaw-kbprep`, and the current GitHub repository slug is still `openclaw-kbprep`. Renaming the remote repository requires a GitHub repository settings change plus documentation URL updates.

## Tracked `dist`

`dist/` is intentionally committed because OpenClaw managed installs need readable JavaScript runtime files. CI now rebuilds and checks `dist` for drift so source and compiled runtime cannot silently diverge.
