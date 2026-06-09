# Capability Matrix

The code-level source of truth is
`python/kbprep_worker/converter_capabilities.py`. This file is the reader-facing
summary of those declarations and should not claim a route that is absent from
the registry.

Status values:

- `verified`: implemented and covered by named tests or fixtures
- `partial`: implemented with some named tests or fixtures, but known to miss important structure or lacks broad coverage
- `experimental`: route exists, but quality depends heavily on external tools or source quality
- `unsupported`: should be reported clearly instead of pretending success

| Capability ID | Source type | Current route | Status | Must preserve | Current evidence | Current risk |
| --- | --- | --- | --- | --- | --- | --- |
| markdown_text_direct | Markdown/text/table text | direct_text | verified | headings, paragraphs, tables, links, code-like details | declares converter capabilities and exposes the chosen capability through diagnosis; reports source-to-converted integrity loss for text sources | cleanup rules can still remove useful text if rules are too broad |
| html_direct | HTML | direct_text | partial | visible text, headings, lists, links, image references | converts local HTML, JSON, and CSV sources into readable Markdown | navigation, footer, cookie, and ad wrappers need document-type cleanup rules |
| json_direct | JSON | direct_text | verified | keys, values, nesting where representable in Markdown | converts local HTML, JSON, and CSV sources into readable Markdown | large machine JSON may be readable but not knowledge-friendly |
| code_direct | Code/config files | direct_code | verified | exact code, parameters, comments, URLs | converts GitHub-style source and config files as fenced Markdown without summarizing code | code must be protected from prose cleanup |
| notebook_json | Jupyter notebooks | notebook_json | partial | markdown cells, code cells, cell order | converts Jupyter notebooks into readable Markdown cells with code and text outputs | outputs, attachments, and rich display data need more fixtures |
| subtitle_transcript_direct | Subtitle/transcript files | direct_text | verified | utterance order, timestamps when present, speaker-like lines | normalizes local subtitle files into readable transcript markdown | subtitle noise still needs transcript-specific cleanup |
| office_xml | Modern Office XML | office_xml | partial | document text, slide order, sheet/table text, embedded images when extractable | converts modern Office files through the local XML fallback when MinerU is unnecessary | layout fidelity, charts, and complex workbook semantics are not fully proven |
| epub_xhtml | EPUB | epub_xhtml | partial | spine order, chapter headings, links, images when referenced | converts EPUB ebooks through local XHTML extraction instead of MinerU | footnotes, complex tables, and custom XHTML need more fixtures |
| pdf_diagnosis_selected | PDF | pdf_diagnosis_selected | partial | page order, text layer where trusted, OCR text when routed to MinerU, image evidence | converts trusted text-layer PDFs without invoking MinerU; falls back to MinerU when a trusted PDF text-layer conversion produces unreadable Markdown; routes image-only scanned PDFs through MinerU OCR and records the actual route | bad embedded text layers and complex layouts require strict quality checks |
| image_ocr | Image files | external_conversion_required | unsupported | n/a | none | Standalone image OCR has no end-to-end KBPrep fixture yet; use an external OCR tool or wrap the image in a verified PDF route first |
| legacy_office_or_mobi_heavy_conversion | Legacy Office/MOBI | external_conversion_required | unsupported | n/a | none | Legacy Office/MOBI conversion is not verified; convert to DOCX, PPTX, XLSX, EPUB, PDF, Markdown, or text first |
| media_requires_transcript | Audio/video binaries | provide_transcript_first | unsupported | n/a | declares converter capabilities and exposes the chosen capability through diagnosis | KBPrep v1 does not transcribe audio/video binaries |

## Next Required Work

Every `diagnose` result and every `diagnosis_report.json` now records the
selected `capability`, including route, status, dependencies, fallback,
preserved structures, test evidence, risk, and reason.

Every successful conversion also writes `conversion_report.json.route_decision`.
That record compares the declared capability route with the actual converter
used for this run, including the diagnosed strategy, actual route,
`fallback_applied`, `fallback_from`, and `fallback_to`. For example, a PDF can
be declared as `pdf_diagnosis_selected`, diagnosed as `pdf_text_layer`, then
record an actual route of `mineru_ocr` if the text layer was rejected after
conversion.

`python/kbprep_worker/converter_capabilities.py` also exposes
`capability_gap_report()`. That machine-readable report lists every non-verified
route with its current status, current route, required evidence, and promotion
blocker. Package checks validate that every `partial` or `unsupported`
capability appears in this gap report, so new file routes cannot silently imply
full support before fixtures prove them.

1. Add golden fixtures for every `partial` route before promoting it to `verified`.
2. Add image-input OCR fixtures before changing `image_ocr` out of `unsupported`.
3. Add legacy Office/MOBI fixtures and a reliable external converter before changing that route out of `unsupported`.
