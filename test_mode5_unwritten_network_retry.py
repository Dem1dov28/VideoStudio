import unittest


class Mode5UnwrittenNetworkRetryTests(unittest.TestCase):
    def test_transient_error_detection_catches_dns_and_connection(self):
        from modes.mode5.unwritten_chapter_generator import _is_transient_llm_error

        self.assertTrue(_is_transient_llm_error(Exception("Connection error.")))
        self.assertTrue(_is_transient_llm_error(Exception("[Errno 11001] getaddrinfo failed")))
        self.assertTrue(_is_transient_llm_error(Exception("HTTP 503 Service Unavailable")))

    def test_transient_error_detection_ignores_schema_failures(self):
        from modes.mode5.unwritten_chapter_generator import _is_transient_llm_error

        self.assertFalse(_is_transient_llm_error(ValueError("Could not parse LLM JSON")))
        self.assertFalse(_is_transient_llm_error(RuntimeError("missing field blocks")))

    def test_outline_validator_allows_empty_visual_anchor_but_requires_human_stakes(self):
        from modes.mode5.unwritten_chapter_generator import _outline_blocks_valid

        base_subchapter = {
            "title": "Official Narrative",
            "coverage": "Coverage",
            "evidence_anchor": "Memo from 1983",
            "visual_anchor": "",
            "human_stakes": "A witness risks losing a career.",
            "micro_conclusion": "First layer is unstable.",
            "frame_description": "",
        }
        chapters = [{"title": f"Block {i}", "subchapters": [dict(base_subchapter)]} for i in range(1, 6)]
        outline = {"working_title": "T", "logline": "L", "chapters": chapters}
        self.assertTrue(_outline_blocks_valid(outline))

        broken = {"working_title": "T", "logline": "L", "chapters": [dict(ch) for ch in chapters]}
        broken["chapters"][0] = dict(broken["chapters"][0])
        broken["chapters"][0]["subchapters"] = [dict(base_subchapter, human_stakes="")]
        self.assertFalse(_outline_blocks_valid(broken))


if __name__ == "__main__":
    unittest.main()
