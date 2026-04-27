from modes.mode5 import pipeline


def test_mode5_stage_transition_forward_ok():
    plan = {}
    pipeline._validate_mode5_stage_transition(plan, pipeline.MODE5_CKPT_STUB)
    pipeline._touch_mode5_checkpoint(plan, pipeline.MODE5_CKPT_STUB)
    pipeline._validate_mode5_stage_transition(plan, pipeline.MODE5_CKPT_AFTER_TTS)


def test_mode5_stage_transition_regression_forbidden():
    plan = {}
    pipeline._touch_mode5_checkpoint(plan, pipeline.MODE5_CKPT_AFTER_IMAGES)
    try:
        pipeline._validate_mode5_stage_transition(plan, pipeline.MODE5_CKPT_STUB)
        assert False, "Expected regression transition to fail"
    except ValueError:
        pass
