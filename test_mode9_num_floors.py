"""
Test script to verify num_floors is properly passed through Mode9 pipeline.
"""

from modes.mode9.scenario_writer import generate_scenario


def test_num_floors_in_scenario():
    """Test that num_floors is stored in scenario."""
    print("=" * 80)
    print("TESTING MODE9 NUM_FLOORS INTEGRATION")
    print("=" * 80)
    
    # Test with 1 floor
    print("\n1. Testing with num_floors=1...")
    scenario_1floor = generate_scenario(
        vehicle_type="car_modern",
        location="factory",
        num_stages=5,
        num_floors=1,
        language="en"
    )
    print(f"   Scenario num_floors: {scenario_1floor.num_floors}")
    assert scenario_1floor.num_floors == 1, "num_floors should be 1"
    print("   [PASS]")
    
    # Test with 2 floors
    print("\n2. Testing with num_floors=2...")
    scenario_2floors = generate_scenario(
        vehicle_type="car_modern",
        location="factory",
        num_stages=5,
        num_floors=2,
        language="en"
    )
    print(f"   Scenario num_floors: {scenario_2floors.num_floors}")
    assert scenario_2floors.num_floors == 2, "num_floors should be 2"
    print("   [PASS]")
    
    # Test default value
    print("\n3. Testing default num_floors (should be 1)...")
    scenario_default = generate_scenario(
        vehicle_type="car_modern",
        location="factory",
        num_stages=5,
        language="en"
    )
    print(f"   Scenario num_floors: {scenario_default.num_floors}")
    assert scenario_default.num_floors == 1, "Default num_floors should be 1"
    print("   [PASS]")
    
    # Test video prompt generation
    print("\n4. Testing video prompt includes num_floors...")
    from modes.mode9.video_generator import _build_keyframe_video_prompt
    
    scenario_dict = {
        "vehicle_type": "car_modern",
        "location": "factory",
        "num_floors": 2,
        "scenes": [
            {
                "start_state_en": "empty space",
                "end_state_en": "chassis assembled",
                "action_en": "assembling chassis",
                "name_en": "Chassis Assembly",
                "workers_en": "workers assembling",
                "machinery_en": "lifts operating"
            }
        ]
    }
    
    prompt = _build_keyframe_video_prompt(
        scene=scenario_dict["scenes"][0],
        scenario=scenario_dict,
        language="en"
    )
    
    print(f"\nGENERATED PROMPT (first 500 chars):")
    print("-" * 80)
    print(prompt[:500])
    print("-" * 80)
    
    # Check if num_floors is mentioned
    if "Number of levels: 2 floors" in prompt:
        print("   [PASS] - num_floors found in prompt")
    else:
        print("   [FAIL] - num_floors NOT found in prompt")
        return False
    
    print("\n" + "=" * 80)
    print("ALL TESTS PASSED!")
    print("=" * 80)
    return True


if __name__ == "__main__":
    try:
        success = test_num_floors_in_scenario()
        if success:
            print("\n[PASS] Mode9 num_floors integration working correctly!")
        else:
            print("\n[FAIL] Some tests failed!")
    except Exception as e:
        print(f"\n[FAIL] Test failed with error: {e}")
        import traceback
        traceback.print_exc()
