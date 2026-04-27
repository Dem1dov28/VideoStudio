from modes.mode5 import pipeline


def test_live_defaults_are_applied():
    plan = {"chunks": [{"index": 0, "segments": [{"s": 0, "text": "x"}]}]}
    pipeline._ensure_mode5_live_defaults(plan)
    assert plan["live_policy"] == "hybrid"
    assert isinstance(plan["live_queue"], list)
    assert isinstance(plan["live_events"], list)
    ch = plan["chunks"][0]
    assert ch["status"] == "pending"
    assert ch["version"] == 1
    assert ch["audio_status"] == "pending"
    seg = ch["segments"][0]
    assert seg["image_version"] == 1
    assert seg["audio_version"] == 1


def test_chunk_scoped_checkpoint_keeps_forward_global_stage():
    plan = {}
    pipeline._touch_mode5_checkpoint(plan, pipeline.MODE5_CKPT_AFTER_SLICES)
    stage = pipeline._checkpoint_stage_for_write(
        plan, pipeline.MODE5_CKPT_AFTER_TTS, chunk_scoped=True
    )
    assert stage == pipeline.MODE5_CKPT_AFTER_SLICES


def test_live_action_queue_idempotent_by_action_id():
    plan = {"chunks": []}
    action_id_1, dup_1 = pipeline._mode5_queue_action(
        plan, "rebuild-final", action_id="act-1", chunk_index=0
    )
    action_id_2, dup_2 = pipeline._mode5_queue_action(
        plan, "rebuild-final", action_id="act-1", chunk_index=0
    )
    assert action_id_1 == "act-1"
    assert action_id_2 == "act-1"
    assert dup_1 is False
    assert dup_2 is True
    assert len(plan["live_queue"]) == 1


def test_duplicate_action_context_mismatch_is_rejected():
    existing = {
        "action_id": "act-42",
        "action": "regenerate-image",
        "payload": {"chunk_index": 1, "segment_index": 2},
    }
    try:
        pipeline._mode5_assert_duplicate_matches(
            existing,
            action="regenerate-image",
            chunk_index=1,
            segment_index=3,
        )
    except ValueError as exc:
        assert "another segment" in str(exc)
    else:
        raise AssertionError("Expected ValueError for action_id segment mismatch")


def test_duplicate_action_type_mismatch_is_rejected():
    existing = {
        "action_id": "act-777",
        "action": "rebuild-final",
        "payload": {},
    }
    try:
        pipeline._mode5_assert_duplicate_matches(existing, action="regenerate-audio", chunk_index=0)
    except ValueError as exc:
        assert "another action" in str(exc)
    else:
        raise AssertionError("Expected ValueError for action_id action mismatch")
