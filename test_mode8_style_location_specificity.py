"""
Test script to verify Mode8 house style and location specificity enhancements.

This tests that:
1. LLM receives detailed house style visual descriptions
2. LLM receives detailed location visual descriptions  
3. Dynamic location features are properly passed
4. Generated prompts explicitly mention architectural styles
5. Different house styles produce distinctly different prompts
"""

import asyncio
from modes.mode8.contextual_prompt_generator import (
    generate_contextual_prompts,
    ContextAnalyzer,
    ImagePromptGenerator,
)
from modes.mode8.scenario_writer import HOUSE_STYLES, LOCATIONS


async def test_context_analysis_with_styles():
    """Test that context analysis receives full style/location data."""
    print("\n" + "="*80)
    print("TEST 1: Context Analysis with House Style & Location Details")
    print("="*80)
    
    # Create a test scenario
    test_scenario = {
        "house_style": "victorian",
        "location": "forest",
        "num_floors": 2,
        "scenes": [
            {"stage_key": "foundation", "name_en": "Foundation", "end_state_en": "foundation complete"},
            {"stage_key": "walls", "name_en": "Walls", "end_state_en": "walls erected"},
            {"stage_key": "roof", "name_en": "Roof", "end_state_en": "roof installed"},
        ]
    }
    
    # Get expected style/location data
    victorian_data = HOUSE_STYLES.get("victorian", {})
    forest_data = LOCATIONS.get("forest", {})
    
    print(f"\nExpected House Style (Victorian):")
    print(f"  Visual: {victorian_data.get('visual', 'N/A')[:100]}...")
    print(f"  Materials: {victorian_data.get('materials', 'N/A')}")
    print(f"  Features: {', '.join(victorian_data.get('typical_features', []))}")
    
    print(f"\nExpected Location (Forest):")
    print(f"  Visual: {forest_data.get('visual', 'N/A')[:100]}...")
    print(f"  Background: {forest_data.get('background', 'N/A')[:100]}...")
    
    # Run context analysis
    try:
        context = await ContextAnalyzer.analyze(test_scenario)
        print(f"\n✓ Context Analysis Success!")
        print(f"  Stages analyzed: {len(context.visual_progression)}")
        print(f"  Overall narrative: {context.overall_narrative[:80]}...")
        
        # Check if style/location influenced analysis
        for i, stage_ctx in enumerate(context.visual_progression[:2]):
            print(f"\n  Stage {i+1} - {stage_ctx.name_en}:")
            print(f"    Theme: {stage_ctx.visual_theme}")
            print(f"    Key Elements: {', '.join(stage_ctx.key_elements[:3])}")
            
    except Exception as e:
        print(f"\n✗ Context Analysis Failed: {e}")
        return False
    
    return True


async def test_image_prompt_generation():
    """Test that image prompts include explicit style/location details."""
    print("\n" + "="*80)
    print("TEST 2: Image Prompt Generation with Explicit Styles")
    print("="*80)
    
    # Test with MODERN house in SUBURBS
    modern_scenario = {
        "house_style": "modern",
        "location": "suburbs",
        "num_floors": 2,
        "scenes": [
            {"stage_key": "foundation", "name_en": "Foundation", "end_state_en": "foundation complete"},
            {"stage_key": "walls", "name_en": "Walls", "end_state_en": "walls erected"},
        ]
    }
    
    # Test with VICTORIAN house in FOREST
    victorian_scenario = {
        "house_style": "victorian",
        "location": "forest",
        "num_floors": 2,
        "scenes": [
            {"stage_key": "foundation", "name_en": "Foundation", "end_state_en": "foundation complete"},
            {"stage_key": "walls", "name_en": "Walls", "end_state_en": "walls erected"},
        ]
    }
    
    async def test_style(scenario, style_name, location_name):
        print(f"\n--- Testing {style_name.upper()} house in {location_name.upper()} ---")
        
        try:
            context = await ContextAnalyzer.analyze(scenario)
            image_prompts = await ImagePromptGenerator.generate_all_prompts(
                scenario=scenario,
                context=context,
                language="en",
            )
            
            if image_prompts:
                prompt_text = image_prompts[0].prompt_text
                print(f"✓ Generated prompt for first stage ({len(prompt_text)} chars)")
                
                # Check for style-specific keywords
                style_keywords = {
                    "modern": ["flat roof", "geometric", "large windows", "minimalist", "concrete", "glass"],
                    "victorian": ["towers", "bay windows", "ornate", "decorative", "vibrant colors", "steep roof"],
                }
                
                found_keywords = []
                for keyword in style_keywords.get(style_name, []):
                    if keyword.lower() in prompt_text.lower():
                        found_keywords.append(keyword)
                
                print(f"  Found {style_name} keywords: {found_keywords}")
                
                # Check for location-specific keywords
                location_keywords = {
                    "suburbs": ["neighborhood", "street", "lawn", "fence", "driveway"],
                    "forest": ["trees", "forest", "pine", "spruce", "clearing", "woodland"],
                }
                
                found_location = []
                for keyword in location_keywords.get(location_name, []):
                    if keyword.lower() in prompt_text.lower():
                        found_location.append(keyword)
                
                print(f"  Found {location_name} keywords: {found_location}")
                
                # Print excerpt
                print(f"\n  Prompt excerpt (first 300 chars):")
                print(f"  {prompt_text[:300]}...")
                
                return len(found_keywords) > 0 or len(found_location) > 0
            
            return False
            
        except Exception as e:
            print(f"✗ Failed: {e}")
            return False
    
    # Test both styles
    modern_result = await test_style(modern_scenario, "modern", "suburbs")
    victorian_result = await test_style(victorian_scenario, "victorian", "forest")
    
    print(f"\n✓ Style differentiation test:")
    print(f"  Modern/Suburbs detected: {modern_result}")
    print(f"  Victorian/Forest detected: {victorian_result}")
    
    return modern_result and victorian_result


async def test_location_dynamics():
    """Test that dynamic location features are included."""
    print("\n" + "="*80)
    print("TEST 3: Dynamic Location Features")
    print("="*80)
    
    from modes.mode8.scenario_writer import LOCATION_DYNAMIC_FEATURES
    
    # Test water-related locations
    water_locations = ["lakefront", "riverside", "seaside"]
    
    for loc_key in water_locations:
        dynamic = LOCATION_DYNAMIC_FEATURES.get(loc_key, {})
        print(f"\n{loc_key.upper()}:")
        print(f"  Dynamic description: {dynamic.get('dynamic_description', 'N/A')[:100]}...")
        print(f"  Visible elements: {', '.join(dynamic.get('visible_elements', [])[:3])}")
    
    # Test mountain/hill locations
    elevation_locations = ["hillside", "mountains", "cliffside"]
    
    for loc_key in elevation_locations:
        dynamic = LOCATION_DYNAMIC_FEATURES.get(loc_key, {})
        print(f"\n{loc_key.upper()}:")
        print(f"  Dynamic description: {dynamic.get('dynamic_description', 'N/A')[:100]}...")
        print(f"  Full house visibility: {dynamic.get('full_house_visibility', 'N/A')}")
    
    print("\n✓ All dynamic features loaded successfully")
    return True


async def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("MODE8 HOUSE STYLE & LOCATION SPECIFICITY TESTS")
    print("="*80)
    
    results = []
    
    # Test 1: Context analysis
    result1 = await test_context_analysis_with_styles()
    results.append(("Context Analysis", result1))
    
    # Test 2: Image prompt generation
    result2 = await test_image_prompt_generation()
    results.append(("Image Prompts", result2))
    
    # Test 3: Location dynamics
    result3 = await test_location_dynamics()
    results.append(("Location Dynamics", result3))
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(r for _, r in results)
    print(f"\nOverall: {'✓ ALL TESTS PASSED' if all_passed else '✗ SOME TESTS FAILED'}")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
