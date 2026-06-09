import unittest

from kbprep_worker.classify_blocks import classify_blocks
from kbprep_worker.obsidian_kb import apply_curated_obsidian_policy, complete_body_filename


class KnowledgePollutionRegressionTests(unittest.TestCase):
    def test_cta_phrase_inside_method_instruction_is_kept(self):
        blocks = [{
            "block_id": "b_method",
            "type": "paragraph",
            "text": "步骤1：在文章结尾加入“扫码入群领取体验卡”作为测试文案，并记录转化率和失败原因。",
            "heading_path": ["用户运营", "私域转化方法"],
        }]

        classified = classify_blocks(blocks, profile="curated_obsidian_kb")

        self.assertEqual(classified[0]["status"], "keep")
        self.assertTrue(classified[0].get("protected"))
        self.assertIn(classified[0]["type"], {"case_step", "operation_step"})

    def test_obsidian_templates_do_not_leak_between_calls(self):
        course_blocks = [{
            "block_id": "course_heading",
            "type": "section_heading",
            "status": "keep",
            "text": "# 生财准备如何用AI赋能圈友",
        }]
        generic_blocks = [{
            "block_id": "generic_heading",
            "type": "section_heading",
            "status": "keep",
            "text": "# 生财准备如何用AI赋能圈友",
        }]

        course_result = apply_curated_obsidian_policy(course_blocks, template_name="obsidian_course_kb")
        generic_result = apply_curated_obsidian_policy(generic_blocks, template_name="obsidian_generic")

        self.assertEqual(course_result[0].get("curated_text"), "# 如何用AI赋能")
        self.assertIsNone(generic_result[0].get("curated_text"))
        self.assertEqual(complete_body_filename("认知", template_name="obsidian_course_kb"), "认知-完整正文.md")
        self.assertEqual(complete_body_filename("认知", template_name="obsidian_generic"), "认知.md")


if __name__ == "__main__":
    unittest.main()
