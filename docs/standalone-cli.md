# KBPrep Standalone CLI

The standalone CLI is KBPrep's maintained host-neutral entry point. It is for local files only.

## AI Review Backend

Standalone KBPrep remains host-neutral. It does not ship OpenClaw, Claude,
Codex, OpenAI, or other provider-specific review code.

For automated review, callers may inject an `AIReviewBackend` in-process or
configure an external command backend. The external command receives JSON on
stdin with `sessionKey`, `message`, `systemPrompt`, optional provider/model
fields, timeout, and idempotency key. It must write JSON on stdout with a
`messages` array and optional `warning`.

If no external command or injected backend is configured, `ai_review` reports a
clear warning and does not claim that AI patches were applied.

External command failures are explicit: invalid JSON, non-zero exit, and timeout
surface as review errors/warnings with stderr evidence instead of being treated
as a successful AI review.

## Runtime Setup

On first use, KBPrep creates a package-local Python runtime under `.kbprep/venv`.
Setup is reported as structured steps: create venv, upgrade packaging tools,
install worker dependencies, then run the setup-env probe.

Default setup timeouts are bounded by step rather than hidden as one long wait:
5 minutes for venv creation, 10 minutes for packaging upgrade, 60 minutes for
worker dependency installation, and 30 minutes for the environment probe. Advanced
operators may override them with `KBPREP_CREATE_VENV_TIMEOUT_MS`,
`KBPREP_UPGRADE_PACKAGING_TIMEOUT_MS`, `KBPREP_INSTALL_WORKER_TIMEOUT_MS`, and
`KBPREP_PROBE_ENVIRONMENT_TIMEOUT_MS`; values are clamped to a safe range.

Use `KBPREP_BOOTSTRAP_PYTHON`, `KBPREP_PYTHON`, or `--config-file` with
`python_path` when a specific Python executable is required. Runtime setup and
worker subprocess timeout errors include stderr tails so failures can be traced
from the CLI JSON envelope or the run log directory.

## Commands

```bash
kbprep-preflight --workdir ./.kbprep/check
kbprep-analyze --input ./source.pdf --output ./.kbprep/source
kbprep-prepare --input ./source.pdf --output ./.kbprep/source --mode rules_only --force
kbprep-prepare --input ./source.md --output ./.kbprep/source --source-url "https://example.com/course/lesson-1" --source-domain "example.com" --site-name "Example Course"
kbprep-apply-review --run-dir ./.kbprep/source/runs/<run-id> --patch-file ./review.patch.json
kbprep-feedback --run-dir ./.kbprep/source/runs/<run-id> --feedback-text "下次删除「关注公众号」这种污染"
kbprep-feedback --accept-proposal latest
kbprep-feedback --suggest-dictionary-updates --rules-dir ./.kbprep/rules/user
kbprep-feedback --promote-dictionary-suggestion --document-type course --confirm-dictionary-update --rerun-after-promotion --rules-dir ./.kbprep/rules/user --target-rules-dir ./rules
kbprep-feedback --summarize-promotion-history --target-rules-dir ./rules
kbprep-feedback --resolve-promotion-failures --document-type course --confirm-failure-resolved --representative-run-dir ./.kbprep/source/runs/<run-id> --target-rules-dir ./rules
kbprep-cleanup --output ./.kbprep/source --action finalize
kbprep-batch --input ./sources --output ./.kbprep/batch --mode rules_only
```

## Help

Every command supports `--help`:

```bash
kbprep-preflight --help
kbprep-analyze --help
kbprep-prepare --help
kbprep-apply-review --help
kbprep-feedback --help
kbprep-cleanup --help
kbprep-batch --help
```

## Modes

- `rules_only`: local deterministic cleanup only.
- `rules_plus_review_pack`: local cleanup plus `review_pack.json` for human or external AI review.
- `ai_review`: only available when the caller injects a generic review backend through the runtime API. The standalone CLI does not read model API keys, does not call a built-in LLM provider, and does not treat an unavailable backend as a successful AI review. The CLI-safe path is `rules_plus_review_pack`, then `kbprep-apply-review` with a validated patch.

`--max-quality-iterations <n>` controls how many quality/review passes may be
recorded before KBPrep stops the loop with `E_QUALITY_ITERATION_LIMIT`. The
default is 3.

## Output

`kbprep-prepare` writes process artifacts under the output directory and publishes a profile-specific final deliverable:

- Default `--profile standard`: use `latest_outputs.final_md`, the source-side Markdown file beside the source.
- Explicit `--profile obsidian_kb`: generic Obsidian vault output. Use `latest_outputs.obsidian_dir`, `latest_outputs.obsidian_index`, and `latest_outputs.obsidian_complete`.
- Explicit `--profile curated_obsidian_kb`: legacy course/self-media Obsidian template. It uses optional template rules such as `obsidian_course_kb` and should only be selected for that document family.

Use `kbprep-cleanup --action finalize` only after checking `quality_report.json`, `discarded.md`, and `review_needed.md`. Finalize preserves the final deliverable: `obsidian/` for Obsidian profiles, or source-side Markdown/assets for standard runs.

`kbprep-feedback` is for learning from review results. By default it writes proposed rules under the current project's `.kbprep/rules/user/proposed_rules.jsonl`. Only an explicit `--accept-proposal <id|latest>` copies a proposal into `.kbprep/rules/user/accepted_rules.jsonl`, where the deterministic cleaner can use it in future runs without extra environment variables. Add `--rerun-after-accept` to rerun the affected source when the original run can be located through `latest.json`.

Use `--suggest-dictionary-updates` after several accepted or rejected feedback records exist. It writes review-only `dictionary_suggestions.jsonl`. Use `--promote-dictionary-suggestion --confirm-dictionary-update` only after review; add `--rerun-after-promotion` so KBPrep reruns representative sources and reports whether promoted discard/protect rules behaved correctly. Every promotion appends `promotion_history.jsonl` under the target rules directory. Run `--summarize-promotion-history` before more promotions to see pass/fail/unverified trends by document type. If a document type has failed promotion history, promotion is blocked by default; `--allow-failed-promotion-history` is a risk override for explicit user-approved continuation. Use `--resolve-promotion-failures` after fixing failed samples; it appends a resolution record only when representative reruns pass. Use `--reject-proposal <id|latest>` for bad proposals; those are written to `.kbprep/rules/user/rejected_rules.jsonl` as memory and are not loaded by cleanup.

For source-specific cleanup, pass provenance into `kbprep-prepare` with `--source-url`, `--source-domain`, and `--site-name` when known. KBPrep records this as `source_identity` in `run_metadata.json`, and accepted `source_pattern` rules can match keyed fragments such as `source_domain:example.com` without affecting unrelated sources. Prefer keyed patterns; plain patterns match path or file-name prefix boundaries rather than arbitrary substrings.

## Path Safety

`--input` and batch `--input` are explicit user-authorized local reads, so absolute
paths are allowed. Write/delete boundaries are stricter: `--output` and cleanup
output roots cannot point at a filesystem root, and patch/config/feedback file
arguments must be real files within their size limits before the Python worker
is called.
