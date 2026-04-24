import asyncio
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


class Mode5UnwrittenChapterTests(unittest.TestCase):
    def test_regenerate_mode5_image_preserves_unwritten_block_anchors(self):
        from modes.mode5 import pipeline as mode5_pipeline

        plan = {
            "sub_mode": "unwritten_chapter",
            "style_suffix": "archival documentary style",
            "chunks": [
                {
                    "index": 0,
                    "chapter_title": "Archive Leak",
                    "subchapter_title": "First Contradiction",
                    "evidence_anchor": "Declassified memo, 1983",
                    "visual_anchor": "dusty archive room with folders",
                    "human_stakes": "the witness could lose his career",
                    "segments": [
                        {
                            "s": 0,
                            "text": "A clerk notices one missing page in the file.",
                            "image": "clips/mode5/img_c0_s0.jpg",
                            "audio": "clips/mode5/seg_c0_s0.wav",
                        }
                    ],
                    "preview_relpath": "mode5_preview_000.mp4",
                }
            ],
        }

        captured: dict[str, str] = {}

        async def fake_build_image_prompt_async(segment_text, style_suffix, **kwargs):
            captured["segment_text"] = segment_text
            captured["style_suffix"] = style_suffix
            return "prompt"

        async def fake_generate_one_image(prompt, img_path, aspect_ratio=None):
            img_path.parent.mkdir(parents=True, exist_ok=True)
            img_path.write_bytes(b"ok")

        async def fake_ensure_intro(*args, **kwargs):
            return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            session_dir = Path(tmp_dir)
            with (
                patch.object(mode5_pipeline, "load_mode5_plan", side_effect=lambda session_id: deepcopy(plan)),
                patch.object(mode5_pipeline, "_session_dir", side_effect=lambda session_id: session_dir),
                patch.object(mode5_pipeline, "_build_image_prompt_async", side_effect=fake_build_image_prompt_async),
                patch.object(mode5_pipeline, "_generate_one_image", side_effect=fake_generate_one_image),
                patch.object(mode5_pipeline, "_ensure_mode5_looped_intro_video", side_effect=fake_ensure_intro),
                patch.object(mode5_pipeline, "_build_chunk_preview_sync", side_effect=lambda session_id, chunk_index, plan_obj: None),
                patch.object(mode5_pipeline, "_save_mode5_plan", side_effect=lambda session_id, plan_obj, checkpoint=None, **extra: None),
            ):
                asyncio.run(mode5_pipeline.regenerate_mode5_image("sid", 0, 0))

        self.assertEqual(captured["style_suffix"], "archival documentary style")
        self.assertIn("Block title: Archive Leak — First Contradiction", captured["segment_text"])
        self.assertIn("Evidence anchor: Declassified memo, 1983", captured["segment_text"])
        self.assertIn("Visual anchor: dusty archive room with folders", captured["segment_text"])
        self.assertIn("Human stakes: the witness could lose his career", captured["segment_text"])
        self.assertIn(
            "Segment meaning:\nA clerk notices one missing page in the file.",
            captured["segment_text"],
        )


if __name__ == "__main__":
    unittest.main()
