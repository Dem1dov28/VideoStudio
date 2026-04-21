"""
Test script to verify Mode9 video prompt optimization.

This tests the new structured format with:
- 150-180 words target
- Bullet point structure (•)
- Full-house visibility (elevated camera)
- Structured sections (8 sections)
- No narrative filler
"""

from modes.mode9.video_generator import _build_keyframe_video_prompt, _build_video_prompt


def test_keyframe_video_prompt():
    """Test keyframe video prompt generation."""
    
    # Sample scene data
    scene = {
        "index": 1,
        "stage_key": "assembly_stage_1",
        "name_en": "Chassis Assembly",
        "start_state_en": "Bare chassis on assembly line",
        "end_state_en": "Chassis with engine and suspension mounted",
        "action_en": "Engine installation and suspension mounting",
        "workers_en": "Mechanics installing engine components, technicians mounting suspension",
        "machinery_en": "Hydraulic lifts, pneumatic tools, engine hoists",
        "build_intensity": "medium",
        "time_of_day": "midday",
        "is_peak_moment": False,
    }
    
    # Sample scenario
    scenario = {
        "vehicle_type": "car_modern",
        "location": "factory",
        "num_floors": 1,  # Single vehicle assembly
    }
    
    print("=" * 80)
    print("TESTING MODE9 KEYFRAME VIDEO PROMPT")
    print("=" * 80)
    
    # Generate prompt
    result = _build_keyframe_video_prompt(
        scene=scene,
        scenario=scenario,
        language="en",
    )
    
    print("\nGENERATED PROMPT:")
    print("-" * 80)
    print(result)
    print("-" * 80)
    
    # Validation checks
    print("\nVALIDATION RESULTS:")
    
    # 1. Word count (TARGET: 150-180 words)
    word_count = len(result.split())
    if word_count < 150:
        status = "FAIL - TOO SHORT"
    elif word_count > 180:
        status = "FAIL - TOO LONG"
    else:
        status = "PASS"
    print(f"{status} - Word count: {word_count}/150-180 (target range)")
    
    # 2. Bullet points
    has_bullets = "•" in result
    status = "PASS" if has_bullets else "FAIL"
    print(f"{status} - Contains bullet points")
    
    # 3. Structure sections
    has_transition = "**TRANSITION:**" in result
    status = "PASS" if has_transition else "FAIL"
    print(f"{status} - Has TRANSITION section")
    
    has_camera = "**CAMERA & CONTINUITY:**" in result
    status = "PASS" if has_camera else "FAIL"
    print(f"{status} - Has CAMERA & CONTINUITY section")
    
    has_visual_changes = "**KEY VISUAL CHANGES**" in result
    status = "PASS" if has_visual_changes else "FAIL"
    print(f"{status} - Has KEY VISUAL CHANGES section")
    
    has_motion_type = "**MOTION TYPE:**" in result
    status = "PASS" if has_motion_type else "FAIL"
    print(f"{status} - Has MOTION TYPE section")
    
    has_motion_detail = "**MOTION DETAIL:**" in result
    status = "PASS" if has_motion_detail else "FAIL"
    print(f"{status} - Has MOTION DETAIL section")
    
    has_height_context = "**ASSEMBLY HEIGHT CONTEXT:**" in result
    status = "PASS" if has_height_context else "FAIL"
    print(f"{status} - Has ASSEMBLY HEIGHT CONTEXT section")
    
    has_visual_focus = "**VISUAL FOCUS:**" in result
    status = "PASS" if has_visual_focus else "FAIL"
    print(f"{status} - Has VISUAL FOCUS section")
    
    has_lighting = "**LIGHTING & ATMOSPHERE:**" in result
    status = "PASS" if has_lighting else "FAIL"
    print(f"{status} - Has LIGHTING & ATMOSPHERE section")
    
    # 4. Full-house visibility check
    has_full_house = "FULL HOUSE VISIBILITY" in result or "FULL vehicle/house visible" in result
    status = "PASS" if has_full_house else "FAIL"
    print(f"{status} - Mentions full-house visibility")
    
    # 5. Elevated camera position
    has_elevated = "Y=8.0m" in result or "elevated" in result.lower()
    status = "PASS" if has_elevated else "FAIL"
    print(f"{status} - Has elevated camera position")
    
    # 6. Character count
    char_count = len(result)
    print(f"\nMETRICS:")
    print(f"   Characters: {char_count}")
    print(f"   Words: {word_count}")
    print(f"   Lines: {len(result.splitlines())}")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    
    return result


if __name__ == "__main__":
    result = test_keyframe_video_prompt()
    
    # Save to file for review
    with open("test_mode9_output.txt", "w", encoding="utf-8") as f:
        f.write("MODE9 GENERATED VIDEO PROMPT SAMPLE\n")
        f.write("=" * 80 + "\n\n")
        f.write(result)
        f.write("\n\n" + "=" * 80 + "\n")
        f.write(f"Word count: {len(result.split())}\n")
        f.write(f"Character count: {len(result)}\n")
    
    print("\nOutput saved to: test_mode9_output.txt")
