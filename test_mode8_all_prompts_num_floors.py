"""Test num_floors in ALL Mode8 prompts (images + videos)."""

from modes.mode8.video_generator import (
    _build_image_prompt,
    _build_video_prompt,
    _build_keyframe_video_prompt,
    _build_drone_showcase_image_prompt,
    _build_final_drone_video_prompt,
)


def test_all_prompts_have_num_floors():
    """Test that ALL image and video prompts include num_floors."""
    
    scenario = {
        "house_style": "modern",
        "location": "suburbs",
        "num_floors": 2,  # Test with 2 floors
    }
    
    scene = {
        "name_en": "Foundation Pour",
        "stage_key": "foundation_poured",
        "start_state_en": "empty land",
        "end_state_en": "concrete foundation",
        "visual_prompt": "Wet concrete poured from mixer",
    }
    
    print("=" * 60)
    print("ТЕСТ: Количество этажей во ВСЕХ промптах")
    print("=" * 60)
    
    # Test image prompts
    print("\n1. Image Prompt (_build_image_prompt):")
    image_prompt = _build_image_prompt(scene, 1, scenario, "en")
    has_floors = "Number of floors:" in image_prompt or "NUM FLOORS:" in image_prompt or "2 floor" in image_prompt
    print(f"   {'✅ PASS' if has_floors else '❌ FAIL'} - Found floors info")
    if has_floors:
        for line in image_prompt.split('\n'):
            if 'floor' in line.lower():
                print(f"   → {line.strip()}")
    
    # Test video prompt
    print("\n2. Video Prompt (_build_video_prompt):")
    video_prompt = _build_video_prompt(scene, 1, 5, scenario, "en")
    has_floors = "NUM FLOORS:" in video_prompt or "Number of levels:" in video_prompt or "2 floor" in video_prompt
    print(f"   {'✅ PASS' if has_floors else '❌ FAIL'} - Found floors info")
    if has_floors:
        for line in video_prompt.split('\n'):
            if 'floor' in line.lower() or 'levels' in line.lower():
                print(f"   → {line.strip()}")
    
    # Test keyframe video prompt
    print("\n3. Keyframe Video Prompt (_build_keyframe_video_prompt):")
    keyframe_prompt = _build_keyframe_video_prompt(scene, scenario, "en")
    has_floors = "NUM FLOORS:" in keyframe_prompt or "Number of levels:" in keyframe_prompt or "2 floor" in keyframe_prompt
    print(f"   {'✅ PASS' if has_floors else '❌ FAIL'} - Found floors info")
    if has_floors:
        for line in keyframe_prompt.split('\n'):
            if 'floor' in line.lower() or 'levels' in line.lower():
                print(f"   → {line.strip()}")
    
    # Test drone showcase image prompt
    print("\n4. Drone Showcase Image Prompt (_build_drone_showcase_image_prompt):")
    drone_image_prompt = _build_drone_showcase_image_prompt(scenario, "en")
    has_floors = "Number of floors:" in drone_image_prompt or "NUM FLOORS:" in drone_image_prompt or "2 floor" in drone_image_prompt
    print(f"   {'✅ PASS' if has_floors else '❌ FAIL'} - Found floors info")
    if has_floors:
        for line in drone_image_prompt.split('\n'):
            if 'floor' in line.lower():
                print(f"   → {line.strip()}")
    
    # Test final drone video prompt
    print("\n5. Final Drone Video Prompt (_build_final_drone_video_prompt):")
    drone_video_prompt = _build_final_drone_video_prompt(scenario, "en")
    has_floors = "Number of floors:" in drone_video_prompt or "NUM FLOORS:" in drone_video_prompt or "2 floor" in drone_video_prompt
    print(f"   {'✅ PASS' if has_floors else '❌ FAIL'} - Found floors info")
    if has_floors:
        for line in drone_video_prompt.split('\n'):
            if 'floor' in line.lower():
                print(f"   → {line.strip()}")
    
    # Summary
    print("\n" + "=" * 60)
    all_pass = all([
        "Number of floors:" in image_prompt or "2 floor" in image_prompt,
        "NUM FLOORS:" in video_prompt or "2 floor" in video_prompt,
        "NUM FLOORS:" in keyframe_prompt or "2 floor" in keyframe_prompt,
        "Number of floors:" in drone_image_prompt or "2 floor" in drone_image_prompt,
        "Number of floors:" in drone_video_prompt or "2 floor" in drone_video_prompt,
    ])
    
    if all_pass:
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        print("Количество этажей указано во ВСЕХ промптах.")
    else:
        print("❌ НЕ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        print("Некоторые промпты не содержат информацию об этажах.")
    
    print("=" * 60)
    return all_pass


if __name__ == "__main__":
    try:
        test_all_prompts_have_num_floors()
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
