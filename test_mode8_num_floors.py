"""
Test script to verify num_floors is properly used in Mode8 video prompts.
"""

from modes.mode8.video_generator import _build_video_prompt, _build_keyframe_video_prompt


def test_num_floors_in_prompts():
    """Test that num_floors appears in Mode8 video prompts."""
    print("=" * 80)
    print("TESTING MODE8 NUM_FLOORS IN VIDEO PROMPTS")
    print("=" * 80)
    
    # Sample scenario with 2 floors
    scenario_2floors = {
        "vehicle_type": "house",
        "house_style": "modern",
        "location": "suburbs",
        "num_floors": 2,  # TWO FLOORS
        "scenes": [
            {
                "start_state_en": "empty foundation",
                "end_state_en": "first floor walls",
                "action_en": "constructing first floor walls",
                "name_en": "First Floor Construction",
                "workers_en": "construction workers building walls",
                "machinery_en": "cranes lifting materials",
            }
        ]
    }
    
    # Test _build_video_prompt
    print("\n1. Testing _build_video_prompt with 2 floors...")
    scene = scenario_2floors["scenes"][0]
    
    prompt1 = _build_video_prompt(
        scene=scene,
        index=0,
        total_stages=5,
        scenario=scenario_2floors,
        language="en"
    )
    
    if "NUM FLOORS: 2 floors" in prompt1:
        print("   [PASS] - Found 'NUM FLOORS: 2 floors' in prompt")
    else:
        print("   [FAIL] - NUM FLOORS not found or incorrect")
        print(f"\n   Generated prompt excerpt:")
        print("   " + "-" * 76)
        for line in prompt1.split('\n')[:20]:
            print(f"   {line}")
        print("   " + "-" * 76)
        return False
    
    # Test _build_keyframe_video_prompt
    print("\n2. Testing _build_keyframe_video_prompt with 2 floors...")
    prompt2 = _build_keyframe_video_prompt(
        scene=scene,
        scenario=scenario_2floors,
        language="en"
    )
    
    if "NUM FLOORS: 2 floors" in prompt2:
        print("   [PASS] - Found 'NUM FLOORS: 2 floors' in keyframe prompt")
    else:
        print("   [FAIL] - NUM FLOORS not found or incorrect in keyframe prompt")
        print(f"\n   Generated prompt excerpt:")
        print("   " + "-" * 76)
        for line in prompt2.split('\n')[:20]:
            print(f"   {line}")
        print("   " + "-" * 76)
        return False
    
    # Test with 3 floors
    print("\n3. Testing with 3 floors...")
    scenario_3floors = {
        "vehicle_type": "house",
        "house_style": "modern",
        "location": "suburbs",
        "num_floors": 3,  # THREE FLOORS
        "scenes": [scene]
    }
    
    prompt3 = _build_keyframe_video_prompt(
        scene=scenario_3floors["scenes"][0],
        scenario=scenario_3floors,
        language="en"
    )
    
    if "NUM FLOORS: 3 floors" in prompt3:
        print("   [PASS] - Found 'NUM FLOORS: 3 floors' in prompt")
    else:
        print("   [FAIL] - NUM FLOORS not correct for 3 floors")
        return False
    
    # Test with 1 floor
    print("\n4. Testing with 1 floor...")
    scenario_1floor = {
        "vehicle_type": "house",
        "house_style": "modern",
        "location": "suburbs",
        "num_floors": 1,  # ONE FLOOR
        "scenes": [scene]
    }
    
    prompt4 = _build_keyframe_video_prompt(
        scene=scenario_1floor["scenes"][0],
        scenario=scenario_1floor,
        language="en"
    )
    
    if "NUM FLOORS: 1 floor" in prompt4:  # Singular "floor" not "floors"
        print("   [PASS] - Found 'NUM FLOORS: 1 floor' in prompt (singular)")
    else:
        print("   [FAIL] - NUM FLOORS not correct for 1 floor")
        print(f"\n   Generated prompt excerpt:")
        print("   " + "-" * 76)
        for line in prompt4.split('\n')[:20]:
            print(f"   {line}")
        print("   " + "-" * 76)
        return False
    
    print("\n" + "=" * 80)
    print("ALL TESTS PASSED!")
    print("=" * 80)
    print("\n[PASS] Mode8 num_floors is correctly injected into video prompts!")
    return True


if __name__ == "__main__":
    try:
        success = test_num_floors_in_prompts()
        if not success:
            print("\n[FAIL] Some tests failed!")
            exit(1)
    except Exception as e:
        print(f"\n[FAIL] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
