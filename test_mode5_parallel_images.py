"""Жёсткий лимит параллельной генерации изображений MODE5 (см. MODE5_PARALLEL_IMAGES_HARD_MAX)."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modes.mode5.pipeline import (
    MODE5_PARALLEL_IMAGES_HARD_MAX,
    _clamp_mode5_parallel_images,
    _mode5_parallel_images_cap,
)


class Mode5ParallelImagesCapTests(unittest.TestCase):
    def test_cap_never_exceeds_hard_max_even_if_settings_huge(self):
        from modes.mode5 import pipeline as mode5_pipeline

        with patch.object(mode5_pipeline.settings, "mode5_max_parallel_images", 999):
            self.assertEqual(_mode5_parallel_images_cap(), MODE5_PARALLEL_IMAGES_HARD_MAX)

    def test_cap_respects_lower_setting(self):
        from modes.mode5 import pipeline as mode5_pipeline

        with patch.object(mode5_pipeline.settings, "mode5_max_parallel_images", 3):
            self.assertEqual(_mode5_parallel_images_cap(), 3)

    def test_clamp_large_request_respects_config_cap(self):
        from modes.mode5 import pipeline as mode5_pipeline

        with patch.object(mode5_pipeline.settings, "mode5_max_parallel_images", 10):
            self.assertEqual(_clamp_mode5_parallel_images(999), 10)

    def test_clamp_none_uses_cap(self):
        from modes.mode5 import pipeline as mode5_pipeline

        with patch.object(mode5_pipeline.settings, "mode5_max_parallel_images", 7):
            self.assertEqual(_clamp_mode5_parallel_images(None), 7)

    def test_clamp_invalid_value_falls_back_to_cap(self):
        from modes.mode5 import pipeline as mode5_pipeline

        with patch.object(mode5_pipeline.settings, "mode5_max_parallel_images", 5):
            self.assertEqual(_clamp_mode5_parallel_images("not-an-int"), 5)


class Mode5ChunkImagesConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_chunk_images_peak_in_flight_at_most_hard_max(self):
        from modes.mode5 import pipeline as mode5_pipeline

        in_flight = 0
        peak = 0
        lock = asyncio.Lock()

        async def fake_generate_one_image(prompt, img_path, aspect_ratio=None, **kwargs):
            nonlocal in_flight, peak
            async with lock:
                in_flight += 1
                peak = max(peak, in_flight)
            await asyncio.sleep(0.08)
            async with lock:
                in_flight -= 1
            img_path.parent.mkdir(parents=True, exist_ok=True)
            img_path.write_bytes(b"x")

        n = 24
        chunk = {
            "index": 0,
            "segments": [
                {"s": i, "text": f"segment {i}", "image": f"clips/mode5/img_c0_s{i}.jpg"}
                for i in range(n)
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            with (
                patch.object(mode5_pipeline, "_session_dir", lambda _sid: session_dir),
                patch.object(mode5_pipeline, "_generate_one_image", side_effect=fake_generate_one_image),
            ):
                await mode5_pipeline._generate_chunk_images(
                    "sid",
                    chunk,
                    "test style lock",
                    sub_mode="facts50",
                    max_parallel_images=999,
                )

        self.assertLessEqual(
            peak,
            MODE5_PARALLEL_IMAGES_HARD_MAX,
            msg=f"ожидали пик одновременных вызовов <= {MODE5_PARALLEL_IMAGES_HARD_MAX}, получили {peak}",
        )
        self.assertGreater(peak, 1, msg="тест должен реально запускать несколько задач параллельно")
