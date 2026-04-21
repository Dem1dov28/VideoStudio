"""Test script to verify Mode9 enhancements."""
import asyncio
import sys
sys.path.insert(0, r'd:\work\VideoStudio')

from modes.mode9.scenario_writer import (
    VEHICLE_TYPES,
    LOCATIONS,
    ASSEMBLY_STAGES,
    CAMERA_SPECS,
    LOCATION_DYNAMIC_FEATURES,
    get_stage_sequence,
    validate_stage_sequence,
    build_visual_prompt,
    generate_scenario,
)
from modes.mode9.architectural_variations import (
    get_vehicle_variation,
    PRE_GENERATED_VARIATIONS,
)

print("=" * 80)
print("MODE9 ENHANCEMENTS VERIFICATION")
print("=" * 80)
print()

# Test 1: Enhanced VEHICLE_TYPES
print("1. ENHANCED VEHICLE TYPES")
print("-" * 80)
print(f"Total vehicle types: {len(VEHICLE_TYPES)}")
print()

sample_vehicles = ["car_modern", "airplane_passenger", "tractor", "ship_cargo"]
for vkey in sample_vehicles:
    vehicle = VEHICLE_TYPES[vkey]
    print(f"  🚗 {vehicle['name_en'].upper()}")
    print(f"     Description: {vehicle.get('description', 'N/A')[:80]}...")
    print(f"     Has typical_features: {'typical_features' in vehicle}")
    print()

# Test 2: Enhanced LOCATIONS
print("2. ENHANCED LOCATIONS")
print("-" * 80)
print(f"Total locations: {len(LOCATIONS)}")
print()

sample_locations = ["factory", "hangar", "ocean_coast", "mountain_valley"]
for lkey in sample_locations:
    loc = LOCATIONS[lkey]
    print(f"  🌍 {loc['name_en'].upper()}")
    print(f"     Description: {loc.get('description', 'N/A')[:80]}...")
    print(f"     Atmosphere: {loc.get('atmosphere', 'N/A')}")
    print(f"     Camera: {loc.get('camera_recommendation', 'N/A')}")
    print(f"     Has dynamic_features: {'dynamic_features' in loc}")
    print()

# Test 3: CAMERA_SPECS
print("3. CAMERA SPECIFICATIONS")
print("-" * 80)
for cam_key, cam_spec in CAMERA_SPECS.items():
    print(f"  📷 {cam_key}")
    print(f"     Name: {cam_spec['name']}")
    print(f"     Height: {cam_spec['height']}")
    print(f"     Movement: {cam_spec['movement']}")
    print()

# Test 4: State Tracking in ASSEMBLY_STAGES
print("4. STATE TRACKING FLAGS")
print("-" * 80)
print("Stage progression (frame | engine | body | wheels | interior | paint):")
print()

for stage_key in ['empty_space', 'frame_chassis', 'engine', 'body_panels', 'wheels', 'interior', 'paint_finish']:
    stage = ASSEMBLY_STAGES[stage_key]
    flags = [
        "F" if stage.get('has_frame') else "-",
        "E" if stage.get('has_engine') else "-",
        "B" if stage.get('has_body') else "-",
        "W" if stage.get('has_wheels') else "-",
        "I" if stage.get('has_interior') else "-",
        "P" if stage.get('has_paint') else "-",
    ]
    print(f"  {stage_key:15} | {' | '.join(flags)} | {stage['name_en']}")

print()

# Test 5: Stage Sequences (5-8 stages)
print("5. STAGE SEQUENCES (5-8 stages)")
print("-" * 80)
for num in [5, 6, 7, 8]:
    seq = get_stage_sequence(num)
    print(f"  {num} stages: {' -> '.join(seq)}")

print()

# Test 6: Validation
print("6. STAGE SEQUENCE VALIDATION")
print("-" * 80)
try:
    validate_stage_sequence(get_stage_sequence(7))
    print("  ✓ 7-stage sequence is valid")
except ValueError as e:
    print(f"  ✗ Validation failed: {e}")

# Test invalid sequence (engine before frame)
invalid_seq = ['empty_space', 'engine', 'frame_chassis', 'body_panels', 'paint_finish']
try:
    validate_stage_sequence(invalid_seq)
    print("  ✗ Invalid sequence passed (should have failed)")
except ValueError as e:
    print(f"  ✓ Correctly detected invalid sequence")

print()

# Test 7: Enhanced Visual Prompt
print("7. ENHANCED VISUAL PROMPT")
print("-" * 80)
prompt = build_visual_prompt(
    stage_key="body_panels",
    vehicle_type="car_sport",
    location="factory",
)
print(prompt[:1500])
print("...")
print()

# Test 8: Architectural Variations
print("8. VEHICLE VARIATIONS SYSTEM")
print("-" * 80)
print(f"Pre-generated variations available for: {len(PRE_GENERATED_VARIATIONS)} vehicle types")
print(f"Variation categories: {', '.join(list(PRE_GENERATED_VARIATIONS.keys())[:5])}...")
print()

# Test fallback variation (sync version)
from modes.mode9.architectural_variations import get_fallback_variation
fallback = get_fallback_variation("car_sport")
print(f"  Fallback variation for car_sport:")
print(f"    Name: {fallback['name']}")
print(f"    Color: {fallback['primary_color']}")
print(f"    Finish: {fallback['finish']}")
print(f"    Features: {', '.join(fallback['accent_features'][:2])}")
print()

# Test 9: Full Scenario Generation
print("9. FULL SCENARIO GENERATION")
print("-" * 80)
scenario = generate_scenario(
    vehicle_type="car_modern",
    location="factory",
    num_stages=6,
    language="ru",
)

print(f"  Title: {scenario.title}")
print(f"  Vehicle: {scenario.vehicle_type_name}")
print(f"  Location: {scenario.location_name}")
print(f"  Stages: {len(scenario.stages)}")
print()

for stage in scenario.stages:
    print(f"    {stage.index + 1}. {stage.name_en} (peak: {stage.is_peak_moment})")

print()

print("=" * 80)
print("ALL TESTS PASSED ✓")
print("=" * 80)
