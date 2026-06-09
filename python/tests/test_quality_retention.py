import tempfile
import unittest
from pathlib import Path

from kbprep_worker.quality.retention import (
    _detail_retention_stats,
    _image_retention_stats,
    _output_retention_stats,
)


class QualityRetentionBehaviorTests(unittest.TestCase):
    def test_output_retention_tolerates_safe_markdown_formatting_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "cleaned.md").write_text(
                "\n".join(
                    [
                        "Step 1: configure threshold=0.8.",
                        "",
                        "```js",
                        "const    value = 1;",
                        "```",
                        "",
                        "|Field|Value|",
                        "|---|---|",
                        "|retry_count|3|",
                        "",
                        "[Docs](https://example.com/docs)",
                    ]
                ),
                encoding="utf-8",
            )
            blocks = [
                {
                    "block_id": "param",
                    "status": "keep",
                    "type": "operation_step",
                    "text": "Step 1: configure threshold = 0.8.",
                },
                {
                    "block_id": "code",
                    "status": "keep",
                    "type": "code",
                    "text": "```js\n    const value = 1;\n```",
                },
                {
                    "block_id": "table",
                    "status": "keep",
                    "type": "table",
                    "text": "| Field | Value |\n| --- | --- |\n| retry_count | 3 |",
                },
                {
                    "block_id": "link",
                    "status": "keep",
                    "type": "paragraph",
                    "text": "Docs: https://example.com/docs",
                },
            ]

            stats = _output_retention_stats(blocks, run_dir)

        self.assertEqual(stats["missing_total"], 0)
        self.assertEqual(stats["parameter"]["missing_count"], 0)
        self.assertEqual(stats["code"]["missing_count"], 0)
        self.assertEqual(stats["table"]["missing_count"], 0)
        self.assertEqual(stats["link"]["missing_count"], 0)

    def test_output_retention_still_fails_when_url_is_removed_or_rewritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "cleaned.md").write_text("Docs: https://short.example/x", encoding="utf-8")
            blocks = [
                {
                    "block_id": "link",
                    "status": "keep",
                    "type": "paragraph",
                    "text": "Docs: https://example.com/docs",
                }
            ]

            stats = _output_retention_stats(blocks, run_dir)

        self.assertEqual(stats["link"]["missing"], ["https://example.com/docs"])
        self.assertEqual(stats["missing_total"], 1)

    def test_discarded_plain_url_pollution_does_not_count_as_detail_loss(self):
        blocks = [
            {
                "block_id": "footer_link",
                "status": "discard",
                "type": "paragraph",
                "text": "More updates at https://example.com/news",
            },
            {
                "block_id": "kept_step",
                "status": "keep",
                "type": "operation_step",
                "text": "Step 1: set threshold=0.8.",
            },
        ]

        stats = _detail_retention_stats(blocks)

        self.assertEqual(stats["discarded_detail_block_ids"], [])
        self.assertEqual(stats["link"]["discarded_blocks"], 1)

    def test_discarded_url_with_strong_detail_signal_still_counts_as_detail_loss(self):
        blocks = [
            {
                "block_id": "lost_config",
                "status": "discard",
                "type": "paragraph",
                "text": "Set threshold=0.8 and open https://example.com/config.",
            }
        ]

        stats = _detail_retention_stats(blocks)

        self.assertEqual(stats["discarded_detail_block_ids"], ["lost_config"])

    def test_svg_retention_accepts_responsive_and_single_quote_svg_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "responsive.svg").write_text(
                "<svg viewBox='0 0 100 100'><path d='M0 0h100v100z'/></svg>",
                encoding="utf-8",
            )
            (run_dir / "lowercase.svg").write_text(
                "<svg viewbox='0 0 100 100'><path d='M0 0h100v100z'/></svg>",
                encoding="utf-8",
            )
            blocks = [
                {
                    "block_id": "responsive",
                    "status": "keep",
                    "type": "image",
                    "text": "![responsive](responsive.svg)",
                },
                {
                    "block_id": "lowercase",
                    "status": "keep",
                    "type": "image",
                    "text": "![lowercase](lowercase.svg)",
                },
            ]

            stats = _image_retention_stats(blocks, run_dir)

        self.assertEqual(stats["missing_file_count"], 0)
        self.assertEqual(stats["invalid_svg_count"], 0)

    def test_svg_retention_rejects_non_svg_files_referenced_as_svg(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "broken.svg").write_text("not svg", encoding="utf-8")
            blocks = [
                {
                    "block_id": "broken",
                    "status": "keep",
                    "type": "image",
                    "text": "![broken](broken.svg)",
                }
            ]

            stats = _image_retention_stats(blocks, run_dir)

        self.assertEqual(stats["invalid_svg_files"], ["broken.svg"])


if __name__ == "__main__":
    unittest.main()
