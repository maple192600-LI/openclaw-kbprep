# Hermes Agent Install

KBPrep does not ship Hermes-specific adapter code.

Use Hermes Agent's own packaging mechanism:

1. Install or clone this repository.
2. Run `npm install` and `npm run build`.
3. Package `skills/kbprep/SKILL.md` as the Hermes-facing instruction.
4. Let the Hermes wrapper call the KBPrep CLI commands:
   - `kbprep-preflight`
   - `kbprep-analyze`
   - `kbprep-prepare`
   - `kbprep-apply-review`
   - `kbprep-feedback`
   - `kbprep-cleanup`
   - `kbprep-batch`

The repository boundary stays the same: CLI, Python worker, rules, docs, and skill instructions.
