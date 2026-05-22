"""Chunk-level sequential toggle must not reduce parallelism when disabled (default)."""

import asyncio
import unittest

from modes.mode5 import pipeline


class Mode5SequentialChunksHelpersTests(unittest.TestCase):
    def test_lane_parallel_unchanged_when_flag_off(self):
        plan = {"sequential_chunks": False}
        self.assertEqual(pipeline._mode5_chunk_lane_parallel(32, plan), 32)
        self.assertEqual(pipeline._mode5_chunk_lane_parallel(10, None), 10)

    def test_lane_parallel_forced_to_one_when_flag_on(self):
        plan = {"sequential_chunks": True}
        self.assertEqual(pipeline._mode5_chunk_lane_parallel(32, plan), 1)

    def test_sequential_chunks_defaults_false(self):
        self.assertFalse(pipeline._mode5_sequential_chunks({}))
        self.assertFalse(pipeline._mode5_sequential_chunks(None))


class Mode5AwaitChunkCoroutinesTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_mode_runs_concurrently(self):
        plan = {"sequential_chunks": False}
        started: list[int] = []
        lock = asyncio.Lock()

        async def worker(i: int) -> int:
            async with lock:
                started.append(i)
            await asyncio.sleep(0.05)
            return i

        coros = [worker(i) for i in range(4)]
        t0 = asyncio.get_event_loop().time()
        out = await pipeline._mode5_await_chunk_coroutines(coros, plan)
        elapsed = asyncio.get_event_loop().time() - t0
        self.assertEqual(out, [0, 1, 2, 3])
        self.assertEqual(len(started), 4)
        # Four 50ms sleeps in parallel should finish well under 200ms.
        self.assertLess(elapsed, 0.18)

    async def test_sequential_mode_runs_one_after_another(self):
        plan = {"sequential_chunks": True}
        order: list[int] = []

        async def worker(i: int) -> int:
            order.append(i)
            await asyncio.sleep(0.03)
            return i

        coros = [worker(i) for i in range(3)]
        t0 = asyncio.get_event_loop().time()
        out = await pipeline._mode5_await_chunk_coroutines(coros, plan)
        elapsed = asyncio.get_event_loop().time() - t0
        self.assertEqual(out, [0, 1, 2])
        self.assertEqual(order, [0, 1, 2])
        self.assertGreaterEqual(elapsed, 0.08)

    async def test_empty_coroutines_returns_empty(self):
        self.assertEqual(await pipeline._mode5_await_chunk_coroutines([], {}), [])


class Mode5EarlyPausePlanTests(unittest.TestCase):
    def test_early_pause_placeholder_stores_sequential_flag(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            sid = "test-seq-chunks"
            session_root = Path(tmp) / sid
            session_root.mkdir(parents=True)
            with (
                patch.object(pipeline, "_session_dir", lambda _s: session_root),
                patch.object(pipeline, "_mode5_dir", lambda _s: session_root / "clips" / "mode5"),
            ):
                (session_root / "clips" / "mode5").mkdir(parents=True, exist_ok=True)
                plan = pipeline.write_mode5_early_pause_placeholder(
                    sid,
                    {
                        "mode5_script_text": "topic for test",
                        "mode5_sub_mode": "facts50",
                        "mode5_sequential_chunks": True,
                    },
                )
            self.assertTrue(plan.get("sequential_chunks"))


if __name__ == "__main__":
    unittest.main()
