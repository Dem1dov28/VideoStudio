"""
Test script to verify Mode8 video prompt optimization.

This tests the new structured format with:
- MAX 150 words
- Bullet point structure (•)
- Specific actions (not abstract)
- No narrative filler
- No magical transformations
"""

import asyncio
from difflib import SequenceMatcher
from modes.mode8.contextual_prompt_generator import VideoPromptGenerator, ScenarioContext


async def test_video_prompt_generation():
    """Test video prompt generation with sample data."""
    
    # Sample scenario data
    from_stage = {
        "index": 1,
        "stage_key": "land_preparation",
        "name_en": "Land Preparation",
    }
    
    to_stage = {
        "index": 2,
        "stage_key": "foundation",
        "name_en": "Foundation",
    }
    
    # Sample image prompts (expanded for better context)
    from_image_prompt = "Construction site with cleared land, excavated soil piles around perimeter, ground leveled and ready for foundation work, realistic daylight, construction materials staged at edges"
    
    to_image_prompt = "Concrete foundation poured into wooden forms, rebar grid visible within forms, workers smoothing concrete surface, construction progress visible, foundation footprint complete"
    
    # Minimal scenario context
    scenario = {
        "scenes": [from_stage, to_stage],
        "house_style": "modern",
        "location": "suburbs",
        "num_floors": 2,
    }
    
    scenario_context = ScenarioContext(
        visual_progression=[],
        overall_narrative="Standard construction progression",
        style_consistency_notes="Modern suburban home",
        location_atmosphere="typical construction site",
    )
    
    previous_prompts = []  # First transition
    
    print("=" * 80)
    print("TESTING MODE8 VIDEO PROMPT GENERATION")
    print("=" * 80)
    
    # Generate prompt
    result = await VideoPromptGenerator.generate_single(
        from_stage=from_stage,
        to_stage=to_stage,
        from_image_prompt=from_image_prompt,
        to_image_prompt=to_image_prompt,
        scenario=scenario,
        scenario_context=scenario_context,
        previous_video_prompts=previous_prompts,
        language="en",
    )
    
    print("\nGENERATED PROMPT:")
    print("-" * 80)
    print(result.prompt_text)
    print("-" * 80)
    
    # Validation checks
    print("\nVALIDATION RESULTS:")
    
    # 1. Word count (TARGET: 150-180 words)
    word_count = len(result.prompt_text.split())
    if word_count < 150:
        status = "FAIL - TOO SHORT"
    elif word_count > 180:
        status = "FAIL - TOO LONG"
    else:
        status = "PASS"
    print(f"{status} - Word count: {word_count}/150-180 (target range)")
    
    # 2. Bullet points
    has_bullets = "•" in result.prompt_text
    status = "PASS" if has_bullets else "FAIL"
    print(f"{status} - Contains bullet points")
    
    # 3. Structure sections
    has_transition = "**TRANSITION:**" in result.prompt_text
    status = "PASS" if has_transition else "FAIL"
    print(f"{status} - Has TRANSITION section")
    
    has_camera_continuity = "**CAMERA & CONTINUITY:**" in result.prompt_text
    status = "PASS" if has_camera_continuity else "FAIL"
    print(f"{status} - Has CAMERA & CONTINUITY section")
    
    has_visual_changes = "**KEY VISUAL CHANGES**" in result.prompt_text
    status = "PASS" if has_visual_changes else "FAIL"
    print(f"{status} - Has KEY VISUAL CHANGES section")
    
    has_motion_type = "**MOTION TYPE:**" in result.prompt_text
    status = "PASS" if has_motion_type else "FAIL"
    print(f"{status} - Has MOTION TYPE section")
    
    has_motion_detail = "**MOTION DETAIL:**" in result.prompt_text
    status = "PASS" if has_motion_detail else "FAIL"
    print(f"{status} - Has MOTION DETAIL section")
    
    has_visual_focus = "**VISUAL FOCUS:**" in result.prompt_text
    status = "PASS" if has_visual_focus else "FAIL"
    print(f"{status} - Has VISUAL FOCUS section")
    
    has_building_height = "**BUILDING HEIGHT CONTEXT:**" in result.prompt_text
    status = "PASS" if has_building_height else "FAIL"
    print(f"{status} - Has BUILDING HEIGHT CONTEXT section")
    
    has_lighting = "**LIGHTING & ATMOSPHERE:**" in result.prompt_text
    status = "PASS" if has_lighting else "FAIL"
    print(f"{status} - Has LIGHTING & ATMOSPHERE section")
    
    # 4. No narrative filler
    filler_phrases = [
        "as the scene progresses",
        "we can see",
        "the camera captures",
        "carefully",
        "diligently",
        "showcasing",
    ]
    found_fillers = [phrase for phrase in filler_phrases if phrase in result.prompt_text.lower()]
    status = "PASS" if not found_fillers else "FAIL"
    print(f"{status} - No narrative filler phrases")
    if found_fillers:
        print(f"   Found: {found_fillers}")
    
    # 5. No magic transformations
    magic_phrases = [
        "instantly appears",
        "magically forms",
        "suddenly materializes",
    ]
    found_magic = [phrase for phrase in magic_phrases if phrase in result.prompt_text.lower()]
    status = "PASS" if not found_magic else "FAIL"
    print(f"{status} - No magical transformations")
    if found_magic:
        print(f"   Found: {found_magic}")
    
    # 6. Check floors/height context mentioned
    has_floor_context = any(word in result.prompt_text.lower() for word in ["floor", "level", "height", "story"])
    status = "PASS" if has_floor_context else "FAIL"
    print(f"{status} - Contains floor/building height context")
    char_count = len(result.prompt_text)
    print(f"\nMETRICS:")
    print(f"   Characters: {char_count}")
    print(f"   Words: {word_count}")
    print(f"   Lines: {len(result.prompt_text.splitlines())}")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    
    return result


if __name__ == "__main__":
    result = asyncio.run(test_video_prompt_generation())
    
    # Save to file for review
    with open("test_output_sample.txt", "w", encoding="utf-8") as f:
        f.write("GENERATED VIDEO PROMPT SAMPLE\n")
        f.write("=" * 80 + "\n\n")
        f.write(result.prompt_text)
        f.write("\n\n" + "=" * 80 + "\n")
        f.write(f"Word count: {len(result.prompt_text.split())}\n")
        f.write(f"Character count: {len(result.prompt_text)}\n")
    
    print("\nOutput saved to: test_output_sample.txt")
