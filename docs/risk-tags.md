# Risk Tags

The kbprep cleaner (`python/kbprep_worker/clean_rules.py`) emits
`risk_tags` on every block that it touches. Tags are free-form strings,
but in practice only the following values are used. The list is
maintained here as the source of truth so downstream consumers (RAG
indexers, Obsidian filters, audit dashboards) can rely on the enum.

## Block-level risk tags

| Tag | Meaning | Set by | Example |
|---|---|---|---|
| `cta` | Call-to-action: a line that asks the user to do something (sign up, scan QR, follow account, claim reward). | `clean_rules.py:_is_cta_line` | "扫码加微信领体验卡" |
| `promotional_line` | Pure marketing copy with no knowledge content; safe to discard. | `clean_rules.py:_is_promotional_line` | "本平台限时优惠" |
| `contextual_promo` | Marketing mention embedded in an otherwise informative paragraph; keep the paragraph, mark for review. | `clean_rules.py:_is_contextual_promo_knowledge` | "本节课程介绍如何识别扫码陷阱" |
| `possible_cta` | Low-confidence CTA detection; reviewer should confirm. | `clean_rules.py:_is_cta_line` (with `_is_tutorial_context`) | "添加客服获取更多资料" |
| `section_heading` | Structural heading; preserved verbatim. | `blockify.py` | "## 第 3 章 操作步骤" |

## Page-level risk tags

| Tag | Meaning | Set by |
|---|---|---|
| `garbled_text_layer` | PDF text layer present but unparseable; MinerU/OCR will be tried. | `diagnose.py:pdf_text_layer` |
| `ppt_export_like` | PDF was exported from PowerPoint; often contains page-level backgrounds the cleaner should not delete. | `diagnose.py:pdf_text_layer` |
| `low_coverage` | OCR returned less than 60% of expected text length. | `quality.py:_check_coverage` |

## Operation statuses (orthogonal to risk_tags)

| Status | Meaning |
|---|---|
| `keep` | Block retained in `cleaned.md` as-is. |
| `discard` | Block moved to `discarded.md` with reason. |
| `evidence` | Block moved to `evidence/marketing_pages.md` (promo content kept for audit). |
| `review` | Block needs human review; appears in `review_needed.md`. |

## Conventions

- Tags are lowercase, snake_case.
- Multiple tags on one block are joined with `+` in serialized form (e.g. `cta+possible_cta`).
- Tags are an **enum-of-intent**, not an enum-of-decision. A `cta` tag does not imply `discard` — see `clean_rules.py:_split_promotional_lines` for the line-level surgery that splits a useful block from its embedded marketing lines.

## Adding a new tag

1. Add the string to the `risk_tags` list in `clean_rules.py`.
2. Document it in this file with the meaning and example.
3. If downstream consumers should react to it (e.g. RAG indexer should skip), add a note in `docs/decoupling.md` or the relevant adapter's README.
