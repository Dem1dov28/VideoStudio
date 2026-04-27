import asyncio
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


class Mode5UnwrittenChapterTests(unittest.TestCase):
    def test_mode5_output_format_defaults_to_horizontal(self):
        from modes.mode5 import pipeline as mode5_pipeline

        with patch.object(mode5_pipeline.settings, "mode5_video_format", None):
            self.assertEqual(mode5_pipeline._mode5_output_format(), "horizontal")

    def test_regenerate_mode5_image_uses_clean_segment_text_only(self):
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

        def fake_build_mode5_image_prompt(**kwargs):
            captured["segment_text"] = str(kwargs.get("segment_text") or "")
            captured["style_suffix"] = str(kwargs.get("style_lock") or "")
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
                patch.object(mode5_pipeline, "build_mode5_image_prompt", side_effect=fake_build_mode5_image_prompt),
                patch.object(mode5_pipeline, "_generate_one_image", side_effect=fake_generate_one_image),
                patch.object(mode5_pipeline, "_ensure_mode5_looped_intro_video", side_effect=fake_ensure_intro),
                patch.object(mode5_pipeline, "_build_chunk_preview_sync", side_effect=lambda session_id, chunk_index, plan_obj: None),
                patch.object(mode5_pipeline, "_save_mode5_plan", side_effect=lambda session_id, plan_obj, checkpoint=None, **extra: None),
            ):
                asyncio.run(mode5_pipeline.regenerate_mode5_image("sid", 0, 0))

        self.assertIn("muted dark palette", captured["style_suffix"].lower())
        self.assertEqual(captured["segment_text"], "A clerk notices one missing page in the file.")

    def test_regenerate_mode5_image_sends_no_prompt_metadata_to_image_api(self):
        from modes.mode5 import pipeline as mode5_pipeline

        plan = {
            "sub_mode": "unwritten_chapter",
            "chunks": [
                {
                    "index": 0,
                    "segments": [
                        {
                            "s": 0,
                            "text": "Investigators compare folders in a dim archive room.",
                            "image": "clips/mode5/img_c0_s0.jpg",
                            "audio": "clips/mode5/seg_c0_s0.wav",
                        }
                    ],
                    "preview_relpath": "mode5_preview_000.mp4",
                }
            ],
        }
        captured: dict[str, str] = {}

        async def fake_generate_one_image(prompt, img_path, aspect_ratio=None):
            captured["prompt"] = prompt
            img_path.parent.mkdir(parents=True, exist_ok=True)
            img_path.write_bytes(b"ok")

        async def fake_ensure_intro(*args, **kwargs):
            return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            session_dir = Path(tmp_dir)
            with (
                patch.object(mode5_pipeline, "load_mode5_plan", side_effect=lambda session_id: deepcopy(plan)),
                patch.object(mode5_pipeline, "_session_dir", side_effect=lambda session_id: session_dir),
                patch.object(mode5_pipeline, "_generate_one_image", side_effect=fake_generate_one_image),
                patch.object(mode5_pipeline, "_ensure_mode5_looped_intro_video", side_effect=fake_ensure_intro),
                patch.object(mode5_pipeline, "_build_chunk_preview_sync", side_effect=lambda session_id, chunk_index, plan_obj: None),
                patch.object(mode5_pipeline, "_save_mode5_plan", side_effect=lambda session_id, plan_obj, checkpoint=None, **extra: None),
            ):
                asyncio.run(mode5_pipeline.regenerate_mode5_image("sid", 0, 0))

        prompt = captured["prompt"]
        for marker in ("CURRENT_SEGMENT", "CHUNK_CONTEXT", "Mode profile", "Locked style id", "Technical rules"):
            self.assertNotIn(marker, prompt)
        low = prompt.lower()
        self.assertIn("absolutely no visible text anywhere in the image", low)
        self.assertIn("no tiled layout, no side-by-side layout, no segmented layout, no panel layout, no small inset pictures", low)

    def test_unwritten_intro_video_forces_horizontal_aspect(self):
        from modes.mode5 import pipeline as mode5_pipeline

        plan = {
            "sub_mode": "unwritten_chapter",
            "style_suffix": "archival documentary style",
            "chunks": [
                {
                    "index": 0,
                    "segments": [
                        {
                            "s": 0,
                            "text": "Intro segment",
                            "image_prompt": "muted archive room",
                            "image": "clips/mode5/img_c0_s0.jpg",
                            "audio": "clips/mode5/seg_c0_s0.wav",
                        }
                    ],
                }
            ],
        }
        captured: dict[str, str] = {}

        async def fake_generate_video_from_keyframes(*args, **kwargs):
            captured["video_aspect_ratio"] = str(kwargs.get("video_aspect_ratio"))
            output_dir = kwargs["output_dir"]
            out = output_dir / "clip_000.mp4"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"mp4")
            return out

        with tempfile.TemporaryDirectory() as tmp_dir:
            session_dir = Path(tmp_dir)
            img = session_dir / "clips/mode5/img_c0_s0.jpg"
            wav = session_dir / "clips/mode5/seg_c0_s0.wav"
            img.parent.mkdir(parents=True, exist_ok=True)
            img.write_bytes(b"jpg")
            wav.write_bytes(b"wav")

            with (
                patch.object(mode5_pipeline, "_session_dir", side_effect=lambda _sid: session_dir),
                patch.object(mode5_pipeline.settings, "fastgen_http_base_url", "https://fast-gen.ai"),
                patch.object(mode5_pipeline.settings, "mode5_video_format", "horizontal"),
                patch(
                    "agents.content_generator.fastgen_http.generate_video_from_keyframes",
                    side_effect=fake_generate_video_from_keyframes,
                ),
            ):
                asyncio.run(mode5_pipeline._ensure_mode5_looped_intro_video("sid", plan, force=True))

        seg0 = plan["chunks"][0]["segments"][0]
        self.assertEqual(captured.get("video_aspect_ratio"), "16:9")
        self.assertEqual(seg0.get("asset_type"), "video")
        self.assertTrue(str(seg0.get("video") or "").endswith("intro_loop_c0_s0.mp4"))


if __name__ == "__main__":
    unittest.main()
