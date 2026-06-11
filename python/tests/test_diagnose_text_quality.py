import unittest

from kbprep_worker.diagnose.text_quality import analyze_text_quality, detect_text_profile
from kbprep_worker.quality.conversion_integrity import _source_text_layer_status


class DiagnoseTextQualityBehaviorTests(unittest.TestCase):
    def test_normal_text_has_low_unreadable_ratio_and_detects_tutorial_profile(self):
        text = "\n".join(
            [
                "步骤1：打开 ExampleTool 后台，设置 threshold=0.8。",
                "步骤2：记录 retry_count=3 和 failure_reason=timeout。",
                "步骤3：复盘失败原因并保存配置。",
            ]
        )

        quality = analyze_text_quality(text)
        profile = detect_text_profile(text)

        self.assertLess(quality["unreadable_text_ratio"], 0.1)
        self.assertEqual(profile["text_profile"], "tutorial")

    def test_mojibake_text_has_high_unreadable_ratio(self):
        text = "ExampleTool姗欑毊涔︿粠鍏ラ棬鍒扮簿閫氾紝娑电洊鏋舵瀯鍘熺悊" * 8

        quality = analyze_text_quality(text)

        self.assertGreaterEqual(quality["unreadable_text_ratio"], 0.25)
        self.assertGreater(quality["mojibake_chars"], 0)

    def test_rejected_pdf_text_layer_is_superseded_by_successful_ocr_conversion(self):
        layer = _source_text_layer_status(
            {
                "needs_ocr": True,
                "pdf_subtype": "garbled_text_layer",
                "text_quality": {"unreadable_text_ratio": 0.5},
            },
            {"converter": "mineru", "converted_bytes": 2048},
        )

        self.assertTrue(layer["superseded_by_conversion"])
        self.assertEqual(layer["converter"], "mineru")

    def test_unreadable_pdf_text_layer_without_ocr_remains_final_quality_failure(self):
        layer = _source_text_layer_status(
            {
                "needs_ocr": True,
                "pdf_subtype": "garbled_text_layer",
                "text_quality": {"unreadable_text_ratio": 0.5},
            },
            {"converter": "pdf_text_layer", "converted_bytes": 128},
        )

        self.assertFalse(layer["superseded_by_conversion"])
        self.assertEqual(layer["converter"], "pdf_text_layer")


if __name__ == "__main__":
    unittest.main()
