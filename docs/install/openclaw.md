# OpenClaw Install

KBPrep no longer maintains OpenClaw adapter business logic in this repository.

Use OpenClaw's own skill or plugin creator to wrap the host-neutral package:

1. Install or clone this repository.
2. Run `npm install` and `npm run build`.
3. Give OpenClaw `skills/kbprep/SKILL.md` as the operating instruction.
4. Expose the CLI commands through whatever wrapper OpenClaw generates:
   - `kbprep-preflight`
   - `kbprep-analyze`
   - `kbprep-prepare`
   - `kbprep-apply-review`
   - `kbprep-feedback`
   - `kbprep-cleanup`
   - `kbprep-batch`

Do not copy old OpenClaw adapter logic back into KBPrep. If OpenClaw needs a plugin shape, let OpenClaw generate it from the CLI and skill instructions.
