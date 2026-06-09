# KBPrep Operator Workflows

KBPrep has three layers:

- Python worker core: deterministic conversion, cleanup, quality gates, and artifact publication.
- Host-neutral CLI: standalone commands that any AI coding tool can call or wrap.
- Operator workflows: repeatable review discipline for AI Coding tools and humans.

The operator workflows below do not replace the Python worker and do not run in the default user conversion path.

## Default Operator Flow

1. Run `kbprep-preflight` for the workspace or output root.
2. Run `kbprep-analyze` on the source file.
3. Run `kbprep-prepare` on one representative file.
4. Inspect `quality_report.json`; strict errors block acceptance.
5. Inspect `discarded.md` and `review_needed.md`; do not accept silent loss of concrete steps, tools, parameters, links, prompts, code, tables, or numbers.
6. Confirm the final deliverable:
   - `curated_obsidian_kb`: `latest_outputs.final_artifact_type="obsidian_dir"`, `obsidian_dir`, `obsidian_index`, and `obsidian_complete`.
   - `standard`: `latest_outputs.final_artifact_type="markdown"` and `final_md`.
7. Run `kbprep-feedback` if review finds repeated pollution or mistaken deletion.
8. Run `kbprep-cleanup --action finalize` only after the result is accepted.
9. Run `kbprep-batch` only after the representative sample passes.

## Specialist Review Workflows

### Quality Gate Review

Use after conversion changes, cleanup changes, or suspicious output.

- Check `quality_report.json` for strict errors.
- Check `detail_retention` for discarded concrete details.
- Check `output_retention` for missing rendered links, parameters, code blocks, and tables.
- Verify the final deliverable exists after cleanup.

### Marketing Noise Review

Use when the source contains author bios, course wrappers, platform ads, community CTAs, QR prompts, or promotional covers.

- Confirm direct promotion is removed or routed to audit files.
- Confirm method/case content that merely mentions marketing terms is preserved.
- Read `discarded.md`, `review_needed.md`, and curated `_audit/` files before accepting.
- Reject any result that looks tidy but hides useful method content in discarded output.

### Release Runtime Review

Use before publishing, installing, or claiming the package is ready.

- Run `npm test`.
- Run `npm run build`.
- Run `npm run pack:check`.
- Run `kbprep-preflight --help` and representative CLI smoke checks after install.

## Product Packaging Boundary

Claude/Codex/OpenClaw/Hermes packaging methods are useful for organization: manifest metadata, skills, local validation, and marketplace trust rules. They are not a reason to move KBPrep's business logic into prompts.

Current packaging priority is local product completeness: clear positioning, usable CLI entry points, repeatable operator workflow, runtime validation, `skills/kbprep/SKILL.md`, and install docs. Marketplace publication is out of scope for this stage.
