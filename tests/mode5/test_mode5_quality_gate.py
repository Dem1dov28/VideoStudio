from modes.mode5.quality_gate import assess_mode5_narration_quality, remediate_mode5_narrations


def test_quality_gate_flags_repetition():
    narrations = [
        "This block repeats same idea and same wording over and over again in this video.",
        "This block repeats same idea and same wording over and over again in this video.",
        "A different block with more unique words and softer transition to the next section.",
    ]
    quality = assess_mode5_narration_quality(narrations, language="en")
    assert quality.score < 0.9
    assert len(quality.flagged_indices) >= 1


def test_quality_gate_remediation_improves_or_keeps_score():
    narrations = [
        "В этом видео мы повторяем одно и то же несколько раз и в этом видео почти нет развития мысли.",
        "В этом видео мы повторяем одно и то же несколько раз и в этом видео почти нет развития мысли.",
    ]
    _, report = remediate_mode5_narrations(narrations, language="ru")
    before = report["quality_before"]["score"]
    after = report["quality_after"]["score"]
    assert after >= before
