"""
Test script to verify building stability rule is present in Mode8 video prompts.
"""

from modes.mode8.video_generator import _build_video_prompt, _build_keyframe_video_prompt


def test_building_stability_in_prompts():
    """Test that building stability rule appears FIRST in Mode8 video prompts."""
    print("=" * 80)
    print("TESTING MODE8 BUILDING STABILITY RULE IN VIDEO PROMPTS")
    print("=" * 80)
    
    # Sample scenario with 2 floors
    scenario = {
        "vehicle_type": "house",
        "house_style": "modern",
        "location": "suburbs",
        "num_floors": 2,
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
    
    scene = scenario["scenes"][0]
    
    # Test _build_video_prompt
    print("\n1. Testing _build_video_prompt...")
    prompt1 = _build_video_prompt(
        scene=scene,
        index=0,
        total_stages=5,
        scenario=scenario,
        language="en"
    )
    
    # Check for critical phrases at the beginning
    lines = prompt1.split('\n')
    first_5_lines = '\n'.join(lines[:5])
    
    checks = {
        "CRITICAL": "CRITICAL" in first_5_lines,
        "UNCHANGED": "UNCHANGED" in first_5_lines or "NOT grow" in first_5_lines,
        "FIXED structure": "FIXED" in first_5_lines or "FIXED structure" in prompt1,
        "STATIC PHOTO": "STATIC PHOTO" in prompt1 or "workers are DYNAMIC" in prompt1,
        "BUILDING STABILITY RULE": "BUILDING STABILITY RULE" in prompt1,
    }
    
    all_pass = True
    for check_name, result in checks.items():
        if result:
            print(f"   [PASS] - Found '{check_name}' in prompt")
        else:
            print(f"   [FAIL] - Missing '{check_name}' in prompt")
            all_pass = False
    
    if not all_pass:
        print(f"\n   Generated prompt (first 10 lines):")
        print("   " + "-" * 76)
        for line in lines[:10]:
            print(f"   {line}")
        print("   " + "-" * 76)
        return False
    
    # Test _build_keyframe_video_prompt
    print("\n2. Testing _build_keyframe_video_prompt...")
    prompt2 = _build_keyframe_video_prompt(
        scene=scene,
        scenario=scenario,
        language="en"
    )
    
    lines2 = prompt2.split('\n')
    first_5_lines_2 = '\n'.join(lines2[:5])
    
    checks2 = {
        "CRITICAL": "CRITICAL" in first_5_lines_2,
        "UNCHANGED": "UNCHANGED" in first_5_lines_2 or "NOT grow" in first_5_lines_2,
        "FIXED structure": "FIXED" in first_5_lines_2 or "FIXED structure" in prompt2,
        "BUILDING STABILITY RULE": "BUILDING STABILITY RULE" in prompt2,
    }
    
    for check_name, result in checks2.items():
        if result:
            print(f"   [PASS] - Found '{check_name}' in keyframe prompt")
        else:
            print(f"   [FAIL] - Missing '{check_name}' in keyframe prompt")
            all_pass = False
    
    if not all_pass:
        print(f"\n   Generated prompt (first 10 lines):")
        print("   " + "-" * 76)
        for line in lines2[:10]:
            print(f"   {line}")
        print("   " + "-" * 76)
        return False
    
    print("\n" + "=" * 80)
    print("ALL TESTS PASSED!")
    print("=" * 80)
    print("\n[PASS] Building stability rule is correctly placed at the beginning of prompts!")
    return True


if __name__ == "__main__":
    try:
        success = test_building_stability_in_prompts()
        if not success:
            print("\n[FAIL] Some tests failed!")
            exit(1)
        print("\n[PASS] Mode8 building stability integration working correctly!")
    except Exception as e:
        print(f"\n[FAIL] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
