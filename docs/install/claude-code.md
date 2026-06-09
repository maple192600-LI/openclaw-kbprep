# Claude Code Install

KBPrep does not ship Claude-specific adapter code.

Use the host-neutral CLI and skill:

1. Install or clone this repository.
2. Run `npm install` and `npm run build`.
3. Copy `skills/kbprep/SKILL.md` into the Claude Code skill location used by your setup.
4. In that skill wrapper, call the CLI commands:
   - `kbprep-preflight`
   - `kbprep-analyze`
   - `kbprep-prepare`
   - `kbprep-apply-review`
   - `kbprep-feedback`
   - `kbprep-cleanup`
   - `kbprep-batch`

Claude Code or its skill creator may package the repository differently. KBPrep's contract is the CLI plus `skills/kbprep/SKILL.md`.
