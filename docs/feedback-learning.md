# Feedback Learning

KBPrep must learn from user feedback without trusting the model blindly.

The user may say:

- "delete this kind of thing next time"
- "you missed this pollution"
- "this should not have been deleted"
- "keep these examples"
- "this heading pattern is useless"

KBPrep should turn feedback into rule proposals, not direct unreviewed mutation.

## Rule Proposal Shape

Each proposal should contain:

- `action`: `discard`, `review`, or `protect`
- `scope`: `global`, `user`, `project`, `document_type`, or `source_pattern`
- `document_type`: optional classifier target
- `source_pattern`: required when `scope` is `source_pattern`; it matches source identity metadata, not the body text
- `pattern`: literal text, regex, or structured matcher
- `examples`: source snippets that triggered the proposal
- `counterexamples`: text that must not match, when known
- `reason`: plain-language explanation
- `created_from_run`: run id or run directory
- `artifact_context`: bounded context from the affected run, including source type, profile, document type, failed quality gates, strict error count, and which audit files were read
- `confidence`: numeric score or enum
- `requires_confirmation`: always true before promotion

## Storage Direction

Planned directories:

```text
.kbprep/
  rules/
    user/
      proposed_rules.jsonl
      accepted_rules.jsonl
      rejected_rules.jsonl
      protected_terms.jsonl

rules/
  base/
  document_types/
  templates/
  user/                 # packaged/default rules
    proposed_rules.jsonl
    accepted_rules.jsonl
    rejected_rules.jsonl
    protected_terms.jsonl
```

Project feedback rules live under the current working directory's `.kbprep/rules/user/` by default. Generic packaged base rules must stay small and obvious. Domain-specific packaged rules belong in `document_types/` or `templates/`.

Portable accepted feedback rules may also be distributed in:

```text
rules/user/
  proposed_rules.jsonl
  accepted_rules.jsonl
  rejected_rules.jsonl
```

`rules/user/accepted_rules.jsonl` is loaded before cleanup, while proposed and
rejected files are memory only. The public package keeps these files empty by
default; customized skill packages may copy reviewed accepted rules there on
purpose. `npm run pack:check` verifies that the JSONL rule slots are included in
the package so learned rules do not disappear during skill packaging.

## Feedback Flow

```text
user feedback
-> analyze affected run artifacts
-> propose reusable rules
-> validate schema
-> require confirmation
-> validate examples and counterexamples before acceptance
-> if validation fails, append a narrower follow-up proposal when evidence supports it
-> accept or reject the proposal
-> write accepted rules only after approval
-> optionally rerun the affected source when run metadata can locate it
-> rerun verification proves the rule helped and did not over-delete
-> cluster repeated accepted feedback by document type
-> promote a reviewed dictionary suggestion only with explicit confirmation
-> rerun representative sources after dictionary promotion when run metadata is available
```

## Implemented First Slice

`kbprep-feedback` records user feedback as `.kbprep/rules/user/proposed_rules.jsonl` by default.
The implementation lives under `python/kbprep_worker/feedback/`: command
dispatch, JSONL storage, artifact reading, proposal validation, source-scope
inference, dictionary promotion, promotion history, and rerun verification are
separate modules, while the public `feedback.run(...)` entrypoint remains
compatible.
It intentionally creates proposals first:

- the proposal must have `requires_confirmation: true`
- feedback may suggest `discard`, `review`, or `protect`
- quoted text in the feedback becomes the first proposed literal pattern
- `quality_report.json`, `discarded.md`, `cleaned.md`, and `review_needed.md` are read from the run directory when present
- proposal examples are pulled from relevant run artifacts before falling back to the literal pattern
- discard proposals can include body-text counterexamples from `cleaned.md` so broad cleanup rules are easier to reject or narrow
- acceptance fails when the proposed pattern misses its examples or matches any counterexample
- when a broad literal discard proposal matches counterexamples, KBPrep can append a narrower proposal derived from a concrete run-artifact example
- if that run artifact records a concrete `document_type`, the narrower follow-up proposal is scoped to that document type instead of staying broadly `user` scoped
- if the run artifact does not identify a concrete document type but does identify
  the source file, the narrower follow-up proposal is scoped to
  `source_pattern`
- if multiple run-artifact examples only vary by digits and the derived regex
  matches all examples without matching counterexamples, the narrower follow-up
  proposal uses `match: "regex"` instead of a broader literal
- if the same feedback pattern appears across related source files in prior
  proposed or accepted feedback, a new default proposal is automatically scoped
  to `source_pattern` and records `repeat_feedback` evidence instead of staying
  as a broad `user` rule
- repeated feedback uses structured `source_identity` before filename prefixes;
  if runs share a local export folder, batch name, or source path prefix, KBPrep
  prefers that narrow scope over broad file-name guesses
- accepted proposals are copied to `.kbprep/rules/user/accepted_rules.jsonl`
- accepted rules are loaded by the deterministic cleanup dictionary
- `source_pattern` accepted rules are loaded only when the current source identity matches the accepted `source_pattern` by field scope or path/name prefix boundary
- source identity always includes the input path, source path, and file name; local callers may also record a source title, origin label, export batch, or other local metadata
- `source_pattern` can be a plain prefix-boundary pattern such as `exports/course-a` or `course-a`; it matches local source paths or file names at safe boundaries
- accepted rule files fail during dictionary loading when a JSONL line is
  invalid or a `regex` pattern cannot compile; errors include the rule file and
  line number so the user can fix the learned dictionary before rerunning
- `kbprep-feedback --accept-proposal <id|latest> --rerun-after-accept` reruns the affected source when `created_from_run` points to a run with a discoverable `latest.json` or `run_metadata.json`
- rerun verification checks the new `cleaned.md`: discard rules must remove the pattern, protect rules must keep it
- when rerun metadata is unavailable, KBPrep reports that rerun verification is unavailable instead of pretending quality was proven
- rejected proposals are copied to `.kbprep/rules/user/rejected_rules.jsonl`
- rejected rules are remembered but never loaded by deterministic cleanup
- a rejected proposal cannot be accepted later by accident
- `kbprep-feedback --suggest-dictionary-updates` clusters accepted and rejected feedback history by document type, then writes review-only suggestions to `dictionary_suggestions.jsonl`
- dictionary suggestions require explicit human confirmation and do not mutate packaged `rules/document_types/*.json` directly
- rejected feedback patterns are excluded from dictionary suggestions so KBPrep does not re-promote text the user already rejected
- `kbprep-feedback --promote-dictionary-suggestion --document-type <type> --confirm-dictionary-update` promotes one reviewed suggestion into a document-type dictionary
- dictionary promotion creates a missing `rules/document_types/<type>.json` file with the standard cleaning-rule schema, or updates an existing valid dictionary
- promotion validates every proposed pattern before writing, skips duplicate rules, and writes a `.bak` backup before updating an existing dictionary
- generated dictionary suggestions preserve `created_from_run` and bounded artifact context so promotion can find representative sources later
- `--rerun-after-promotion` reruns representative source runs after a dictionary promotion and reports per-sample `quality_report.json`, `cleaned.md`, strict errors, and rule effects
- `--representative-run-dir <dir>` can be used when the suggestion file does not contain enough run provenance
- every dictionary promotion appends a durable `promotion_history.jsonl` record under the target rules directory, including promoted rule ids and regression verification results
- `kbprep-feedback --summarize-promotion-history` reads `promotion_history.jsonl` and summarizes pass/fail/unverified trends by document type before the next dictionary change
- dictionary promotion is blocked by default when the same document type has failed promotion history
- `--allow-failed-promotion-history` is an explicit risk override; use it only after reviewing failed regression samples and user approval
- `kbprep-feedback --resolve-promotion-failures` reruns representative samples and appends a `kbprep.dictionary_promotion_resolution.v1` record only when the reruns pass
- promotion history summaries treat resolved failed promotions as no longer blocking future promotion

Example:

```bash
kbprep-feedback --run-dir ./.kbprep/source/run-123 --feedback-text "下次删除「关注公众号」这种污染"
kbprep-feedback --run-dir ./.kbprep/source/run-123 --scope source_pattern --source-pattern "export-a" --feedback-text "这个本地导出来源以后删除「批次专属广告」"
kbprep-feedback --run-dir ./.kbprep/source/run-123 --scope source_pattern --source-pattern "exports/course-a" --feedback-text "这个本地导出批次以后删除「来源专属广告」"
kbprep-feedback --accept-proposal latest --rerun-after-accept
kbprep-feedback --reject-proposal latest --reject-reason "这是正文案例，不是污染"
kbprep-feedback --suggest-dictionary-updates --rules-dir ./.kbprep/rules/user --min-feedback-count 2
kbprep-feedback --promote-dictionary-suggestion --document-type course --confirm-dictionary-update --rerun-after-promotion --rules-dir ./.kbprep/rules/user --target-rules-dir ./rules
kbprep-feedback --summarize-promotion-history --target-rules-dir ./rules
kbprep-feedback --resolve-promotion-failures --document-type course --confirm-failure-resolved --representative-run-dir ./.kbprep/source/runs/<run-id> --target-rules-dir ./rules
```

## Implemented Source Identity Matching

`source_pattern` no longer depends only on file names. KBPrep records local source identity in `run_metadata.json`. Deterministic cleanup uses the same identity when deciding whether a source-scoped accepted rule should load.

This keeps learned source-specific cleanup narrow: a rule for `exports/course-a` can remove that export batch's boilerplate without affecting unrelated files that happen to share the same body text.

Plain `source_pattern` values do not use arbitrary substring matching. They match source paths or file names at a path/name prefix boundary, so `course-a` can match `course-a-page.md` while `test` does not match `contest_report.pdf`.
