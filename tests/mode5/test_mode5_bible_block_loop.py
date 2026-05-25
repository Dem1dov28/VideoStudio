from modes.mode5.pipeline import (
    _apply_mode5_block_loop_timing_to_plan,
    _mode5_block_loop_needed_blocks,
    _mode5_block_loop_pool_size_for_plan,
    _mode5_block_loop_seconds_for_plan,
    _mode5_estimated_plan_speech_sec,
    _mode5_skip_segment_images_for_block_loop,
)


def test_bible_block_loop_uses_thirty_minute_slots():
    plan = {"sub_mode": "bible", "language": "ru", "chunks": [{"text": "word " * 500}]}
    _apply_mode5_block_loop_timing_to_plan(plan)
    assert plan["block_loop_seconds"] == 1800.0
    assert _mode5_block_loop_seconds_for_plan(plan) == 1800.0


def test_bible_block_loop_pool_is_one_confirmed_clip():
    words = "слово " * 2700
    plan = {
        "sub_mode": "bible",
        "language": "ru",
        "script_text": words,
        "chunks": [{"text": words[: len(words) // 2]}, {"text": words[len(words) // 2 :]}],
    }
    est = _mode5_estimated_plan_speech_sec(plan)
    assert est >= 1100.0
    pool = _mode5_block_loop_pool_size_for_plan(plan)
    assert pool == 1


def test_manual_keeps_default_thirty_minute_block_loop():
    plan = {"sub_mode": "manual", "language": "ru", "chunks": [{"text": "hello world"}]}
    assert _mode5_block_loop_seconds_for_plan(plan) == 1800.0
    assert _mode5_block_loop_pool_size_for_plan(plan) == 5


def test_bible_skips_per_segment_jpegs_when_block_loop_still_then_animate():
    plan = {"sub_mode": "bible", "image_backend": "playwright"}
    assert _mode5_skip_segment_images_for_block_loop(plan) is True


def test_user_block_loop_pool_size_override():
    words = "слово " * 5400
    plan = {
        "sub_mode": "bible",
        "language": "ru",
        "script_text": words,
        "block_loop_pool_size_user": 4,
        "block_loop_pool_size": 4,
        "chunks": [{"text": words}],
    }
    _apply_mode5_block_loop_timing_to_plan(plan)
    assert plan["block_loop_pool_size"] == 4
    assert _mode5_block_loop_pool_size_for_plan(plan) == 4


def test_user_pool_capped_when_audio_shorter():
    import modes.mode5.pipeline as pipeline_mod

    plan = {
        "sub_mode": "bible",
        "language": "ru",
        "block_loop_pool_size_user": 3,
        "chunks": [{"segments": [{"audio": "clips/mode5/chunk_000/seg_000.wav"}]}],
    }
    orig = pipeline_mod._mode5_actual_plan_audio_sec
    pipeline_mod._mode5_actual_plan_audio_sec = lambda _sid, _plan: 3600.0
    try:
        assert _mode5_block_loop_needed_blocks(plan, session_id="sess") == 2
        assert _mode5_block_loop_pool_size_for_plan(plan, session_id="sess") == 2
    finally:
        pipeline_mod._mode5_actual_plan_audio_sec = orig


def test_user_pool_full_count_before_audio():
    import modes.mode5.pipeline as pipeline_mod

    plan = {
        "sub_mode": "bible",
        "language": "ru",
        "block_loop_pool_size_user": 3,
        "chunks": [{"text": "hello"}],
    }
    orig = pipeline_mod._mode5_actual_plan_audio_sec
    pipeline_mod._mode5_actual_plan_audio_sec = lambda _sid, _plan: 0.0
    try:
        assert _mode5_block_loop_pool_size_for_plan(plan, session_id="sess") == 3
    finally:
        pipeline_mod._mode5_actual_plan_audio_sec = orig
