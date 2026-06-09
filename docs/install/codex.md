# Codex Install

KBPrep does not ship Codex-specific adapter code.

Use the host-neutral CLI and skill:

1. Install or clone this repository.
2. Run `npm install` and `npm run build`.
3. Copy `skills/kbprep/SKILL.md` into your Codex skill directory, or ask Codex's skill tooling to package this repository.
4. Keep the skill pointed at the CLI commands:
   - `kbprep-preflight`
   - `kbprep-analyze`
   - `kbprep-prepare`
   - `kbprep-apply-review`
   - `kbprep-feedback`
   - `kbprep-cleanup`
   - `kbprep-batch`

Codex should treat KBPrep as a local file-processing CLI, not as a SaaS or host plugin.
