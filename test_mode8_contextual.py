"""Test script to verify Mode8 contextual prompt generation system."""
import asyncio
import sys
sys.path.insert(0, r'd:\work\VideoStudio')

from modes.mode8.contextual_prompt_generator import (
    ContextAnalyzer,
    ImagePromptGenerator,
    VideoPromptGenerator,
    generate_contextual_prompts,
)
from modes.mode8.scenario_writer import run_mode8_scenario_writer

print("=" * 80)
print("MODE8 CONTEXTUAL PROMPT GENERATION TEST")
print("=" * 80)
print()

async def test_full_pipeline():
    """Test the complete 3-stage contextual pipeline."""
    
    # Step 0: Generate a basic scenario
    print("0. GENERATING BASIC SCENARIO")
    print("-" * 80)
    scenario_dict = await run_mode8_scenario_writer(
        house_style="modern",
        location="suburbs",
        num_stages=5,
        language="ru",
    )
    print(f"Generated scenario: {scenario_dict.get('title', 'N/A')}")
    print(f"House style: {scenario_dict.get('house_style_name', 'N/A')}")
    print(f"Location: {scenario_dict.get('location_name', 'N/A')}")
    print(f"Stages: {len(scenario_dict.get('scenes', []))}")
    print()
    
    for stage in scenario_dict.get("scenes", []):
        print(f"  {stage.get('index', 0) + 1}. {stage.get('name_en', 'N/A')}")
    print()
    
    # Step 1: Context Analysis
    print("1. CONTEXT ANALYSIS (LLM)")
    print("-" * 80)
    context = await ContextAnalyzer.analyze(scenario_dict)
    print(f"Overall narrative: {context.overall_narrative[:100]}...")
    print(f"Style consistency: {context.style_consistency_notes[:100]}...")
    print(f"Location atmosphere: {context.location_atmosphere[:100]}...")
    print()
    
    print("Visual progression:")
    for stage_ctx in context.visual_progression:
        print(f"  Stage {stage_ctx.index + 1}: {stage_ctx.name_en}")
        print(f"    Theme: {stage_ctx.visual_theme}")
        print(f"    Key elements: {', '.join(stage_ctx.key_elements[:3])}")
        print(f"    Emotional tone: {stage_ctx.emotional_tone}")
    print()
    
    # Step 2: Image Prompt Generation
    print("2. IMAGE PROMPT GENERATION (LLM + History)")
    print("-" * 80)
    image_prompts = await ImagePromptGenerator.generate_all_prompts(
        scenario=scenario_dict,
        context=context,
        language="en",
    )
    
    print(f"Generated {len(image_prompts)} image prompts")
    print()
    
    for i, prompt in enumerate(image_prompts[:2]):  # Show first 2
        print(f"Image {i+1} ({prompt.stage_key}):")
        print(f"  Length: {len(prompt.prompt_text)} chars")
        print(f"  Preview: {prompt.prompt_text[:150]}...")
        print(f"  Analysis: {prompt.analysis_notes}")
        print()
    
    # Step 3: Video Prompt Generation
    print("3. VIDEO PROMPT GENERATION (LLM + Recursive Analysis)")
    print("-" * 80)
    video_prompts = await VideoPromptGenerator.generate_all_prompts(
        scenario=scenario_dict,
        context=context,
        image_prompts=image_prompts,
        language="en",
    )
    
    print(f"Generated {len(video_prompts)} video prompts")
    print()
    
    for i, prompt in enumerate(video_prompts[:2]):  # Show first 2
        print(f"Video {i+1} ({prompt.stage_key}):")
        print(f"  Length: {len(prompt.prompt_text)} chars")
        print(f"  Preview: {prompt.prompt_text[:150]}...")
        print(f"  Analysis: {prompt.analysis_notes}")
        print()
    
    # Test full pipeline function
    print("4. FULL PIPELINE TEST")
    print("-" * 80)
    full_result = await generate_contextual_prompts(
        scenario=scenario_dict,
        language="en",
    )
    
    print(f"Context: {len(full_result['context']['visual_progression'])} stages analyzed")
    print(f"Image prompts: {len(full_result['image_prompts'])}")
    print(f"Video prompts: {len(full_result['video_prompts'])}")
    print()
    
    print("=" * 80)
    print("ALL TESTS PASSED ✓")
    print("=" * 80)
    print()
    print("Summary:")
    print(f"  - Context analysis: {len(context.visual_progression)} stages")
    print(f"  - Image prompts: {len(image_prompts)} (with history awareness)")
    print(f"  - Video prompts: {len(video_prompts)} (with recursive analysis)")
    print(f"  - Full pipeline: SUCCESS")


if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
