"""
Mode 8 Contextual Prompt Generator — Intelligent LLM-based System.

This module implements a stateful, history-aware prompt generation pipeline:
1. Context Analysis (LLM) — Analyze scenario for visual progression
2. Image Prompt Generation (LLM + Context) — Generate all image prompts with history
3. Video Prompt Generation (LLM + Recursive Analysis) — Generate video prompts iteratively

KEY FEATURES:
- Each stage analyzes ALL previous prompts to avoid repetition
- LLM is invoked at every step for intelligent context awareness
- Visual progression tracking ensures each stage is unique
- Cross-stage dependency management for consistent storytelling
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from loguru import logger

from utils.llm import make_llm


# ═══════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class StageContext:
    """Context analysis for a single building stage."""
    index: int
    stage_key: str
    name_en: str
    visual_theme: str  # Main visual theme for this stage
    key_elements: list[str]  # Unique visual elements
    emotional_tone: str  # Emotional atmosphere
    progression_notes: str  # How this stage differs from previous
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "stage_key": self.stage_key,
            "name_en": self.name_en,
            "visual_theme": self.visual_theme,
            "key_elements": self.key_elements,
            "emotional_tone": self.emotional_tone,
            "progression_notes": self.progression_notes,
        }


@dataclass
class ScenarioContext:
    """Complete context analysis for entire scenario."""
    visual_progression: list[StageContext] = field(default_factory=list)
    overall_narrative: str = ""
    style_consistency_notes: str = ""
    location_atmosphere: str = ""
    num_floors: int = 2  # NEW: Number of floors from UI
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "visual_progression": [sc.to_dict() for sc in self.visual_progression],
            "overall_narrative": self.overall_narrative,
            "style_consistency_notes": self.style_consistency_notes,
            "location_atmosphere": self.location_atmosphere,
            "num_floors": self.num_floors,
        }


@dataclass
class GeneratedPrompt:
    """Generated prompt with metadata."""
    stage_index: int
    stage_key: str
    prompt_text: str
    language: str
    prompt_type: str  # "image" or "video"
    analysis_notes: str = ""  # LLM's reasoning for this prompt
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_index": self.stage_index,
            "stage_key": self.stage_key,
            "prompt_text": self.prompt_text,
            "language": self.language,
            "prompt_type": self.prompt_type,
            "analysis_notes": self.analysis_notes,
        }


# ═══════════════════════════════════════════════════════════════════════════
# PROMPT TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════

CONTEXT_ANALYSIS_PROMPT = """You are an expert visual narrative analyst for construction timelapse videos.

TASK: Analyze the building scenario and create a detailed visual progression plan.

SCENARIO DETAILS:
- House Style: {house_style}
- House Style Visual Description: {house_style_visual}
- House Style Materials: {house_style_materials}
- Location: {location}
- Location Visual Description: {location_visual}
- Location Background: {location_background}
- Number of Floors: {num_floors} {floor_word}
- Total Stages: {total_stages}

STAGES TO ANALYZE:
{stages_list}

For EACH stage, provide:

1. VISUAL THEME (2-3 words): Main visual focus
2. KEY ELEMENTS (4-6 items): Unique visual details that appear ONLY in this stage
3. EMOTIONAL TONE (1-2 words): Mood/atmosphere
4. PROGRESSION NOTES: How this stage visually DIFFERS from all previous stages

CRITICAL REQUIREMENTS:
- Each stage must have DISTINCT visual elements (no repetition)
- Create clear visual progression (empty land → foundation → walls → roof → finished)
- ⚠️ CRITICAL: Camera MUST remain COMPLETELY STATIC — NO angle changes allowed
- Ensure architectural consistency while adding variety
- **HOUSE STYLE SPECIFICITY**: Explicitly reference the house style's unique characteristics (roof shape, materials, architectural features) in each stage
- **LOCATION DYNAMICS**: Make the location come alive - if near water, show water prominently; if in forest, emphasize trees surrounding; if mountains, highlight elevation and peaks
- **ARCHITECTURAL DIVERSITY**: Ensure different house styles look DISTINCTLY different (e.g., Mansion should NOT look like Cabin, Victorian should NOT look like Minimalist)

Respond with structured JSON following the ScenarioContext schema."""


IMAGE_PROMPT_GENERATION_PROMPT = """You are a professional AI image prompt engineer for construction timelapse photography.

TASK: Generate a UNIQUE image prompt for stage {stage_index} of {total_stages}.

CONTEXT FROM PREVIOUS STAGES:
{previous_prompts_context}

CURRENT STAGE DETAILS:
- Stage: {stage_name} ({stage_key})
- Visual Theme: {visual_theme}
- Key Elements: {key_elements}
- Emotional Tone: {emotional_tone}
- Progression Notes: {progression_notes}

ARCHITECTURAL CONTEXT:
- House Style: {house_style}
- House Style Visual Details: {house_style_visual}
- House Style Materials: {house_style_materials}
- House Style Features: {house_style_features}
- Location: {location}
- Location Visual Details: {location_visual}
- Location Background Elements: {location_background}
- Location Dynamic Features: {location_dynamic}
- Number of Floors: {num_floors} {floor_word}
- Camera Specs: {camera_specs}

PREVIOUS IMAGE PROMPTS (DO NOT REPEAT):
{previous_image_prompts}

YOUR TASK:
Write a detailed, cinematic image prompt that:
1. Captures THIS SPECIFIC stage's unique visual character
2. DOES NOT repeat elements from previous stages (see above)
3. Maintains architectural consistency
4. Uses specific, vivid details (NOT generic descriptions)
5. Includes lighting and composition details (camera angle is FIXED - see calibration data below)
6. **CRITICAL: ENTIRE HOUSE MUST BE FULLY VISIBLE** - compose the shot so the complete house structure fits within the frame with surrounding landscape context
7. **FRAMING REQUIREMENT**: House should occupy 40-50% of frame - far enough to show full building, not cropped or partial view
8. **HOUSE STABILITY**: The house structure itself does NOT change during image capture - camera is completely static
9. **HOUSE STYLE EXPLICITNESS**: Clearly describe the specific architectural style - e.g., if Victorian, mention towers/bay windows/ornate details; if Modern, mention flat roof/geometric shapes/large glass panels
10. **LOCATION IMMERSION**: Make the location dynamic - if lakeside, show expansive water; if forest, show dense trees surrounding; if hillside, show dramatic elevation
11. **STYLE DIVERSITY**: Ensure this house looks UNIQUE to its style - a Cottage should NOT resemble a Mansion, a Cabin should NOT look like Contemporary

CRITICAL RULES:
- NEVER use phrases like "similar to", "same as", "like before"
- ALWAYS describe what's NEW and DIFFERENT in this stage
- Use concrete visual details (materials, textures, colors, shadows)
- Make each prompt feel like a professional photograph
- **COMPOSITION RULE**: Frame the shot to capture the ENTIRE house - imagine you're photographing from 25 meters away at 8 meters height
- **FULL VISIBILITY**: Every part of the house must be in frame - from foundation to roof, left edge to right edge
- **NO CROPPING**: Never crop any part of the house - the whole structure must fit completely in the shot

⚠️ STATIC CAMERA RULE (ABSOLUTELY CRITICAL):
- Camera must be COMPLETELY STATIC - mounted on tripod, locked-off position
- Background (sky, clouds, trees, grass, landscape, neighboring houses) MUST stay EXACTLY identical across ALL stages
- ONLY THE HOUSE CONSTRUCTION changes - the background is FROZEN and cannot change
- Camera angle, height, distance, perspective - everything must remain IDENTICAL
- If camera moves even 1 degree between stages, the entire timelapse video will be ruined
- Think of it as: camera is bolted to concrete - ZERO movement allowed
- This is THE MOST IMPORTANT rule for construction timelapse
- **HOUSE STRUCTURE REMAINS UNCHANGED** - only workers/machinery move around fixed structure

━━━ CAMERA CALIBRATION DATA (MATHEMATICAL PRECISION REQUIRED) ━━━
CAMERA PARAMETERS - MUST BE IDENTICAL FOR EVERY SINGLE IMAGE:
- Position: X=0.0m (center), Y=8.0m (height - elevated), Z=25.0m (distance - far)
- Angle: Horizontal=0°, Vertical=-10° (slight downward angle from height)
- Focal Length: 35mm full-frame equivalent (wide enough for full house)
- Horizon Line: 60% from bottom edge (elevated viewpoint)
- Cloud Motion: ALWAYS moving RIGHT (never static, never left)
- Framing: ENTIRE house must be fully visible with surrounding landscape
- These parameters are LOCKED - ZERO tolerance for variation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STYLE: Photorealistic, shot on smartphone camera, natural lighting, authentic construction site look. NOT 3D render, NOT CGI, NOT animated, NOT cartoon. Must look like REAL smartphone footage.

Write the prompt in English for AI image generation."""


VIDEO_PROMPT_GENERATION_PROMPT = """You are an expert AI video prompt engineer for construction timelapse.

TASK: Generate detailed structured video prompt (150-180 words) for transition: {from_stage_name} -> {to_stage_name}.

⚠️ CRITICAL RULE #0 - HOUSE STRUCTURE STABILITY ABSOLUTE (MOST IMPORTANT):
The ENTIRE HOUSE STRUCTURE MUST REMAIN 100% UNCHANGED throughout this video!

**ARCHITECTURAL ELEMENTS THAT CANNOT CHANGE:**
- ROOF: Shape, slope, material CANNOT change (flat OR pitched OR gabled - whatever exists, stays IDENTICAL)
- WALLS: Height, width, position CANNOT change (walls are FROZEN)
- WINDOWS/DOORS: Size, location, style CANNOT change (if present, they stay FIXED)
- FOUNDATION: Dimensions CANNOT change (foundation is STATIC)
- **NUMBER OF FLOORS: MUST STAY EXACTLY {num_floors} {floor_word} - CANNOT add or remove floors during video**
- The house does NOT grow, modify, or transform during this video
- ONLY workers and machinery move around the FIXED structure
- Think: house is a STATIC PHOTO - workers are DYNAMIC overlay
- Camera captures workers working, NOT house changing
- House structure is LOCKED - only construction ACTIVITY happens around it

IMAGE PROMPTS (visual reference - these define the FIXED structure):
- From Stage: {from_image_prompt}
- To Stage: {to_image_prompt}

PREVIOUS VIDEO PROMPTS (AVOID REPETITION):
{previous_video_prompts}

CONTEXT FOR CONTINUITY:
- Building Type: House with {num_floors} {floor_word}
- Overall Progression: Stage {from_index} of {total_stages} total stages
- What's Already Built: Previous stages completed successfully
- What Comes Next: After this transition, construction continues upward/forward

---
OUTPUT FORMAT (STRICT STRUCTURE WITH LINE BREAKS):

**TRANSITION:** [{from_stage_name}] -> [{to_stage_name}]

**CAMERA & CONTINUITY:** (4 bullets - VERY concise)
• Fixed tripod (X=0.0m, Y=8.0m, Z=25.0m), 35mm focal length
• Horizon at 60% from bottom, elevated viewpoint
• Sky, trees, landscape unchanged across frames
• ONLY workers/machinery move - house structure FROZEN
• ENTIRE house fully visible with surrounding landscape

**KEY VISUAL CHANGES** (3 bullets - main focus, detailed):
• [Specific worker/machinery ACTION with tools + method]
• [Construction activity detail - what workers are DOING]
• [Movement/installation process - HOW work is done]

**MOTION TYPE:** [timelapse]

**MOTION DETAIL:** (3 bullets - concise)
• Continuous forward build, smooth progression
• No reversing - only forward advancement
• Active workers/machinery, tools: [specific tools]

**BUILDING HEIGHT CONTEXT:** (2 bullets - REQUIRED)
• Current floor: [ground/first/second], height: ~[X] meters
• Vertical progress: building grows upward

**VISUAL FOCUS:** [2-3 words - REQUIRED]

**LIGHTING & ATMOSPHERE:** (2 bullets - REQUIRED)
• Time: [morning/midday], lighting: [bright/diffused]
• Weather: clear construction conditions

---
CRITICAL RULES:

1. TARGET 150-180 WORDS TOTAL (allocate words wisely across ALL sections)
2. Include ALL sections above - EVERY section required
3. CAMERA: Keep very concise (20 words max)
4. KEY VISUAL CHANGES: Main detail here (50-60 words) - focus on WORKER ACTIONS not house changes
5. MOTION DETAIL: Concise (25 words max)
6. BUILDING HEIGHT CONTEXT: Required (20 words)
7. VISUAL FOCUS: Required (2-3 words)
8. LIGHTING & ATMOSPHERE: Required (20 words)
9. FORMAT REQUIREMENT: Use line breaks between sections
10. NO narrative filler:
    - "as the scene progresses"
    - "we can see"
    - "the camera captures"
    - "carefully", "diligently", "skillfully"
    - "showcasing", "illustrating"

11. NO magical transformations:
    - NO instant appearance
    - ALL changes by visible agents (workers/machinery)

12. BE SPECIFIC about WORKER ACTIONS:
    ❌ WRONG: "roof changes from flat to pitched"
    ✅ CORRECT: "workers install roof trusses on existing walls"
    
    ❌ WRONG: "walls grow taller"
    ✅ CORRECT: "workers add new wall sections upward"
    
    ❌ WRONG: "windows appear in walls"
    ✅ CORRECT: "workers install window frames into openings"

13. HOUSE STRUCTURE IS FIXED:
    - Roof shape (flat/pitched/gabled) - WHATEVER EXISTS, STAYS SAME
    - Wall dimensions - WHATEVER EXISTS, STAYS SAME
    - Window/door locations - WHATEVER EXISTS, STAYS SAME
    - Foundation size - WHATEVER EXISTS, STAYS SAME
    - **Number of floors ({num_floors} {floor_word}) - WHATEVER EXISTS, STAYS SAME - CANNOT add/remove floors**
    - You CANNOT change architectural elements - ONLY workers move

14. WORD ALLOCATION MATTERS: Don't spend 100 words on first 2 sections - save words for KEY VISUAL CHANGES and LIGHTING!

Write in English. Generate EVERY section. Balance word count across all sections. Focus on WORKER ACTIVITY around FIXED structure."""""


# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT ANALYZER (LLM-Powered)
# ═══════════════════════════════════════════════════════════════════════════

class ContextAnalyzer:
    """Analyzes scenario to extract visual progression context."""
    
    @staticmethod
    async def analyze(scenario: dict[str, Any]) -> ScenarioContext:
        """
        Analyze entire scenario and create visual progression plan.
        
        Args:
            scenario: Complete scenario dict from scenario_writer
            
        Returns:
            ScenarioContext with analysis for all stages
        """
        logger.info("[Mode8 Context] Starting scenario context analysis...")
        
        try:
            llm = make_llm(temperature=0.7)
            
            # Prepare stages list for analysis
            stages = scenario.get("scenes", [])
            stages_list = "\n".join([
                f"{i+1}. {s['name_en']} — {s.get('end_state_en', 'construction progress')}"
                for i, s in enumerate(stages)
            ])
            
            # Get house style and location with FULL visual descriptions
            house_style = scenario.get("house_style", "modern")
            location = scenario.get("location", "suburbs")
            num_floors = scenario.get("num_floors", 2)  # NEW: Get floors from scenario
            floor_word = "floors" if num_floors > 1 else "floor"
            
            # Import style and location data
            from modes.mode8.video_generator import HOUSE_STYLE_VISUALS, LOCATION_VISUALS
            from modes.mode8.scenario_writer import HOUSE_STYLES, LOCATIONS, LOCATION_DYNAMIC_FEATURES
            
            # Get detailed visual descriptions
            house_style_data = HOUSE_STYLES.get(house_style, HOUSE_STYLES["modern"])
            location_data = LOCATIONS.get(location, LOCATIONS["suburbs"])
            
            house_style_visual = house_style_data.get("visual", house_style_data.get("description", ""))
            house_style_materials = house_style_data.get("materials", "")
            house_style_features = ", ".join(house_style_data.get("typical_features", []))
            
            location_visual = location_data.get("visual", location_data.get("description", ""))
            location_background = location_data.get("background", "")
            
            # Get dynamic location features
            dynamic_features = LOCATION_DYNAMIC_FEATURES.get(location, {})
            location_dynamic = dynamic_features.get("dynamic_description", "")
            if not location_dynamic:
                location_dynamic = location_data.get("dynamic_features", "")
            if isinstance(location_dynamic, dict):
                location_dynamic = location_dynamic.get("dynamic_description", "")
            
            logger.info(f"[Mode8 Context] House Style: {house_style} | Features: {house_style_features[:80]}...")
            logger.info(f"[Mode8 Context] Location: {location} | Dynamic: {location_dynamic[:80] if location_dynamic else 'N/A'}...")
            
            # Build prompt
            prompt = CONTEXT_ANALYSIS_PROMPT.format(
                house_style=house_style,
                house_style_visual=house_style_visual,
                house_style_materials=house_style_materials,
                house_style_features=house_style_features,
                location=location,
                location_visual=location_visual,
                location_background=location_background,
                location_dynamic=location_dynamic or "typical setting",
                num_floors=num_floors,  # NEW: Pass floors to context analysis
                floor_word=floor_word,
                total_stages=len(stages),
                stages_list=stages_list,
            )
            
            # Invoke LLM with timeout (increased to 90s for complex analysis)
            try:
                logger.info(f"[Mode8 Context] Analyzing {len(stages)} stages with LLM (timeout=90s)...")
                response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=90.0)
            except asyncio.TimeoutError:
                logger.warning(f"[Mode8 Context] Context analysis timeout (90s), using fallback")
                raise Exception("Timeout")
            except Exception as e:
                logger.error(f"[Mode8 Context] LLM invocation failed: {e}")
                raise
            
            # Parse response (extract JSON)
            context_data = _parse_context_response(response.content)
            
            # Build StageContext objects
            visual_progression = []
            for stage_data in context_data.get("stages", []):
                stage_ctx = StageContext(
                    index=stage_data.get("index", 0),
                    stage_key=stage_data.get("stage_key", ""),
                    name_en=stage_data.get("name_en", ""),
                    visual_theme=stage_data.get("visual_theme", "construction progress"),
                    key_elements=stage_data.get("key_elements", []),
                    emotional_tone=stage_data.get("emotional_tone", "productive"),
                    progression_notes=stage_data.get("progression_notes", ""),
                )
                visual_progression.append(stage_ctx)
            
            context = ScenarioContext(
                visual_progression=visual_progression,
                overall_narrative=context_data.get("overall_narrative", ""),
                style_consistency_notes=context_data.get("style_consistency_notes", ""),
                location_atmosphere=context_data.get("location_atmosphere", ""),
                num_floors=num_floors,  # NEW: Pass floors from scenario
            )
            
            logger.success(f"[Mode8 Context] Analyzed {len(visual_progression)} stages")
            return context
            
        except Exception as e:
            logger.error(f"[Mode8 Context] Context analysis failed: {e}")
            # Return minimal context
            return _create_fallback_context(scenario)


def _parse_context_response(content: str) -> dict[str, Any]:
    """Parse LLM response for context analysis."""
    # Simple extraction (in production, use proper JSON parsing)
    import json
    
    # Try to find JSON block
    start_idx = content.find("{")
    end_idx = content.rfind("}") + 1
    
    if start_idx >= 0 and end_idx > start_idx:
        json_str = content[start_idx:end_idx]
        try:
            return json.loads(json_str)
        except:
            pass
    
    # Fallback: basic structure
    return {
        "stages": [],
        "overall_narrative": content[:500],
    }


def _create_fallback_context(scenario: dict[str, Any]) -> ScenarioContext:
    """Create minimal context if LLM fails."""
    stages = scenario.get("scenes", [])
    num_floors = scenario.get("num_floors", 2)  # NEW: Get floors from scenario
    visual_progression = []
    
    for i, stage in enumerate(stages):
        visual_progression.append(StageContext(
            index=i,
            stage_key=stage.get("stage_key", ""),
            name_en=stage.get("name_en", ""),
            visual_theme="construction progress",
            key_elements=["foundation", "walls", "roof"][:i+1],
            emotional_tone="productive",
            progression_notes=f"Stage {i+1} of construction",
        ))
    
    return ScenarioContext(
        visual_progression=visual_progression,
        overall_narrative="Standard construction progression",
        style_consistency_notes="Maintain consistent architectural style",
        location_atmosphere="typical construction site",
        num_floors=num_floors,  # NEW: Pass floors to fallback context
    )


# ═══════════════════════════════════════════════════════════════════════════
# IMAGE PROMPT GENERATOR (LLM-Powered with History)
# ═══════════════════════════════════════════════════════════════════════════

class ImagePromptGenerator:
    """Generates image prompts with full context awareness."""
    
    @staticmethod
    async def generate_all_prompts(
        scenario: dict[str, Any],
        context: ScenarioContext,
        language: str = "en",
    ) -> list[GeneratedPrompt]:
        """
        Generate ALL image prompts sequentially with history awareness.
        
        Each prompt analyzes ALL previous prompts to avoid repetition.
        """
        logger.info("[Mode8 Images] Generating image prompts with context...")
        
        all_prompts = []
        previous_prompts = []
        
        stages = scenario.get("scenes", [])
        
        for i, stage in enumerate(stages):
            # Get context for this stage
            stage_context = context.visual_progression[i] if i < len(context.visual_progression) else None
            
            # Generate prompt with full history
            prompt = await ImagePromptGenerator.generate_single(
                stage=stage,
                stage_context=stage_context,
                scenario_context=context,
                previous_prompts=previous_prompts,
                language=language,
            )
            
            all_prompts.append(prompt)
            previous_prompts.append(prompt)
            
            logger.debug(f"[Mode8 Images] Generated prompt for stage {i+1}: {stage.get('name_en')}")
        
        logger.success(f"[Mode8 Images] Generated {len(all_prompts)} image prompts")
        return all_prompts
    
    @staticmethod
    async def generate_single(
        stage: dict[str, Any],
        stage_context: StageContext | None,
        scenario_context: ScenarioContext,
        previous_prompts: list[GeneratedPrompt],
        language: str = "en",
    ) -> GeneratedPrompt:
        """Generate single image prompt with full context."""
        try:
            llm = make_llm(temperature=0.8)
            
            # Build previous prompts context
            if previous_prompts:
                prev_context = "\n\n".join([
                    f"Stage {p.stage_index + 1} ({p.stage_key}):\n{p.prompt_text[:300]}"
                    for p in previous_prompts[-3:]  # Last 3 prompts
                ])
            else:
                prev_context = "No previous stages (this is the first stage)"
            
            # Build previous prompts text
            prev_prompts_text = "\n\n".join([
                f"--- Stage {p.stage_index + 1} ---\n{p.prompt_text}"
                for p in previous_prompts
            ]) or "None (first stage)"
            
            # Get stage details
            stage_key = stage.get("stage_key", "")
            stage_name = stage.get("name_en", "")
            
            # Get context info
            visual_theme = stage_context.visual_theme if stage_context else "construction progress"
            key_elements = ", ".join(stage_context.key_elements) if stage_context else "construction elements"
            emotional_tone = stage_context.emotional_tone if stage_context else "productive"
            progression_notes = stage_context.progression_notes if stage_context else f"Stage {stage.get('index', 0) + 1} progression"
            
            # Get camera specs
            camera_specs = _get_camera_specs_for_scenario(scenario_context)
            
            # Calculate floor word
            num_floors = scenario_context.num_floors
            floor_word = "floors" if num_floors > 1 else "floor"
            
            # === CRITICAL: Get detailed house style and location data ===
            from modes.mode8.video_generator import HOUSE_STYLE_VISUALS, LOCATION_VISUALS
            from modes.mode8.scenario_writer import HOUSE_STYLES, LOCATIONS, LOCATION_DYNAMIC_FEATURES
            
            # Get scenario-level style and location
            house_style_key = stage.get("house_style", scenario_context.style_consistency_notes or "modern")
            location_key = stage.get("location", scenario_context.location_atmosphere or "suburbs")
            
            # Fallback to scenario dict if available
            scenario_dict = stage.get("_scenario_ref", {})
            if scenario_dict:
                house_style_key = scenario_dict.get("house_style", house_style_key)
                location_key = scenario_dict.get("location", location_key)
            
            house_style_data = HOUSE_STYLES.get(house_style_key, HOUSE_STYLES["modern"])
            location_data = LOCATIONS.get(location_key, LOCATIONS["suburbs"])
            
            house_style_visual = house_style_data.get("visual", house_style_data.get("description", ""))
            house_style_materials = house_style_data.get("materials", "")
            house_style_features = ", ".join(house_style_data.get("typical_features", []))
            
            location_visual = location_data.get("visual", location_data.get("description", ""))
            location_background = location_data.get("background", "")
            
            # Get dynamic location features
            dynamic_features = LOCATION_DYNAMIC_FEATURES.get(location_key, {})
            location_dynamic = dynamic_features.get("dynamic_description", "")
            if not location_dynamic:
                location_dynamic = location_data.get("dynamic_features", "")
            if isinstance(location_dynamic, dict):
                location_dynamic = location_dynamic.get("dynamic_description", "")
            
            logger.debug(f"[Mode8 Images] Style: {house_style_key} | Location: {location_key}")
            
            # CRITICAL: Add static camera warning to camera specs
            camera_specs_with_warning = f"""{camera_specs}

⚠️ CRITICAL CAMERA RULE (MOST IMPORTANT):
- Camera must be COMPLETELY STATIC (tripod-mounted, locked-off)
- Camera position CANNOT change between stages
- Background (sky, trees, landscape) MUST remain EXACTLY the same
- ONLY THE HOUSE changes - background is FROZEN
- This is essential for smooth timelapse video
- If camera moves even slightly, the entire video will be ruined"""
            
            # Build prompt
            prompt_text = IMAGE_PROMPT_GENERATION_PROMPT.format(
                stage_index=stage.get("index", 0) + 1,
                total_stages=len(scenario_context.visual_progression),
                previous_prompts_context=prev_context,
                stage_name=stage_name,
                stage_key=stage_key,
                visual_theme=visual_theme,
                key_elements=key_elements,
                emotional_tone=emotional_tone,
                progression_notes=progression_notes,
                house_style=house_style_key,
                house_style_visual=house_style_visual,
                house_style_materials=house_style_materials,
                house_style_features=house_style_features,
                location=location_key,
                location_visual=location_visual,
                location_background=location_background,
                location_dynamic=location_dynamic or "typical setting",
                num_floors=num_floors,
                floor_word=floor_word,
                camera_specs=camera_specs_with_warning,  # Use enhanced version
                previous_image_prompts=prev_prompts_text,
            )
            
            # Invoke LLM with timeout (increased to 60s for detailed prompts)
            try:
                logger.debug(f"[Mode8 Images] Generating prompt for stage {stage_key} (timeout=60s)...")
                response = await asyncio.wait_for(llm.ainvoke(prompt_text), timeout=60.0)
            except asyncio.TimeoutError:
                logger.warning(f"[Mode8 Images] Image prompt generation timeout (60s), using fallback")
                raise Exception("Timeout")
            except Exception as e:
                logger.error(f"[Mode8 Images] LLM invocation failed: {e}")
                raise
            
            generated_prompt = response.content.strip()
            
            return GeneratedPrompt(
                stage_index=stage.get("index", 0),
                stage_key=stage_key,
                prompt_text=generated_prompt,
                language=language,
                prompt_type="image",
                analysis_notes=f"Generated with context from {len(previous_prompts)} previous stages",
            )
            
        except Exception as e:
            logger.error(f"[Mode8 Images] Failed to generate prompt for stage {stage.get('stage_key')}: {e}")
            # Fallback to original prompt
            fallback_prompt = stage.get("visual_prompt", f"Construction stage: {stage.get('name_en')}")
            return GeneratedPrompt(
                stage_index=stage.get("index", 0),
                stage_key=stage.get("stage_key", ""),
                prompt_text=fallback_prompt,
                language=language,
                prompt_type="image",
                analysis_notes="Fallback prompt (LLM failed)",
            )


def _get_camera_specs_for_scenario(context: ScenarioContext) -> str:
    """Extract camera specs from context with FIXED calibration parameters matching video_generator.py."""
    # CONSISTENT parameters across ALL mode8 files for full house visibility
    return """⚠️ FIXED CAMERA PARAMETERS (LOCKED - for ENTIRE HOUSE visibility):
- Position: X=0.0m (center), Y=8.0m (height - elevated), Z=25.0m (distance - far)
- Angle: Horizontal=0°, Vertical=-10° (slight downward angle from height)
- Focal Length: 35mm full-frame equivalent (wide enough for full house)
- Horizon Line: 60% from bottom edge (elevated viewpoint)
- Cloud Motion: ALWAYS moving RIGHT (never static, never left)
- Camera: tripod-mounted, locked-off, COMPLETELY STATIC
- Framing: ENTIRE house must be fully visible with surrounding landscape
- STYLE: Photorealistic smartphone photo, NOT 3D render, NOT CGI"""


# ═══════════════════════════════════════════════════════════════════════════
# VIDEO PROMPT GENERATOR (LLM-Powered with Recursive Analysis)
# ═══════════════════════════════════════════════════════════════════════════

class VideoPromptGenerator:
    """Generates video prompts with full iterative analysis."""
    
    @staticmethod
    async def generate_all_prompts(
        scenario: dict[str, Any],
        context: ScenarioContext,
        image_prompts: list[GeneratedPrompt],
        language: str = "en",
    ) -> list[GeneratedPrompt]:
        """
        Generate ALL video prompts iteratively.
        
        Each video prompt analyzes:
        - The transition (stage_i → stage_i+1)
        - Both image prompts for these stages
        - ALL previous video prompts to avoid repetition
        """
        logger.info("[Mode8 Videos] Generating video prompts with recursive analysis...")
        
        all_prompts = []
        previous_prompts = []
        
        stages = scenario.get("scenes", [])
        
        # Generate N-1 video prompts (transitions between stages)
        for i in range(len(stages) - 1):
            from_stage = stages[i]
            to_stage = stages[i + 1]
            
            from_image_prompt = image_prompts[i].prompt_text if i < len(image_prompts) else ""
            to_image_prompt = image_prompts[i + 1].prompt_text if i + 1 < len(image_prompts) else ""
            
            # Generate prompt with full analysis
            prompt = await VideoPromptGenerator.generate_single(
                from_stage=from_stage,
                to_stage=to_stage,
                from_image_prompt=from_image_prompt,
                to_image_prompt=to_image_prompt,
                scenario=scenario,  # NEW: Pass scenario dict
                scenario_context=context,
                previous_video_prompts=previous_prompts,
                language=language,
            )
            
            all_prompts.append(prompt)
            previous_prompts.append(prompt)
            
            logger.debug(f"[Mode8 Videos] Generated prompt for transition {i+1}: {from_stage.get('name_en')} → {to_stage.get('name_en')}")
        
        logger.success(f"[Mode8 Videos] Generated {len(all_prompts)} video prompts")
        return all_prompts
    
    @staticmethod
    async def generate_single(
        from_stage: dict[str, Any],
        to_stage: dict[str, Any],
        from_image_prompt: str,
        to_image_prompt: str,
        scenario: dict[str, Any],
        scenario_context: ScenarioContext,
        previous_video_prompts: list[GeneratedPrompt],
        language: str = "en",
    ) -> GeneratedPrompt:
        """Generate single video prompt with full recursive analysis."""
        try:
            llm = make_llm(temperature=0.8)
            
            from_index = from_stage.get("index", 0)
            
            # Build previous video prompts context (concise)
            if previous_video_prompts:
                prev_videos_text = "\n\n".join([
                    f"--- Transition {p.stage_index + 1} ---\n{p.prompt_text[:300]}"
                    for p in previous_video_prompts[-3:]  # Last 3 prompts only
                ])
            else:
                prev_videos_text = "None (first video transition)"
            
            # Simplified scenario summary with essential context
            total_stages = len(scenario.get('scenes', []))
            num_floors = scenario.get("num_floors", 2)
            
            # === CRITICAL: Get detailed house style and location data ===
            from modes.mode8.video_generator import HOUSE_STYLE_VISUALS, LOCATION_VISUALS
            from modes.mode8.scenario_writer import HOUSE_STYLES, LOCATIONS, LOCATION_DYNAMIC_FEATURES
            
            house_style_key = scenario.get("house_style", "modern")
            location_key = scenario.get("location", "suburbs")
            
            house_style_data = HOUSE_STYLES.get(house_style_key, HOUSE_STYLES["modern"])
            location_data = LOCATIONS.get(location_key, LOCATIONS["suburbs"])
            
            house_style_visual = house_style_data.get("visual", house_style_data.get("description", ""))
            house_style_materials = house_style_data.get("materials", "")
            house_style_features = ", ".join(house_style_data.get("typical_features", []))
            
            location_visual = location_data.get("visual", location_data.get("description", ""))
            location_background = location_data.get("background", "")
            
            # Get dynamic location features
            dynamic_features = LOCATION_DYNAMIC_FEATURES.get(location_key, {})
            location_dynamic = dynamic_features.get("dynamic_description", "")
            if not location_dynamic:
                location_dynamic = location_data.get("dynamic_features", "")
            if isinstance(location_dynamic, dict):
                location_dynamic = location_dynamic.get("dynamic_description", "")
            
            scenario_summary = f"""
Building Info:
- Floors: {num_floors} floors total
- Total Construction Stages: {total_stages}
- Current Transition: {from_index + 1} of {total_stages - 1} video transitions
- House Style: {house_style_key} — {house_style_visual[:100]}...
- Location: {location_key} — {location_visual[:100]}...
- Location Dynamics: {location_dynamic[:80] if location_dynamic else 'N/A'}...
            """.strip()
            
            # Get num_floors from scenario
            num_floors = scenario.get("num_floors", 2)
            
            # Build prompt with strict format and full context
            prompt_text = VIDEO_PROMPT_GENERATION_PROMPT.format(
                from_stage_name=from_stage.get("name_en", ""),
                to_stage_name=to_stage.get("name_en", ""),
                from_image_prompt=from_image_prompt[:400],  # More context
                to_image_prompt=to_image_prompt[:400],
                previous_video_prompts=prev_videos_text,
                from_index=from_index + 1,
                total_stages=len(scenario.get('scenes', [])),
                num_floors=scenario.get("num_floors", 2),
            )
            
            # Invoke LLM with timeout (60s for detailed video prompts)
            try:
                logger.debug(f"[Mode8 Videos] Generating prompt for transition {from_index + 1} (timeout=60s)...")
                response = await asyncio.wait_for(llm.ainvoke(prompt_text), timeout=60.0)
                generated_prompt = response.content.strip()
            except asyncio.TimeoutError:
                logger.warning(f"[Mode8 Videos] Video prompt generation timeout (60s)")
                raise Exception("Timeout")
            except Exception as e:
                logger.error(f"[Mode8 Videos] LLM invocation failed: {e}")
                raise
            
            # Final cleanup
            generated_prompt = generated_prompt.strip()
            
            # Log basic metrics
            logger.info(f"[Mode8 Videos] Generated: {len(generated_prompt)} chars, {len(generated_prompt.split())} words")
            
            return GeneratedPrompt(
                stage_index=from_index,
                stage_key=f"{from_stage.get('stage_key')}_to_{to_stage.get('stage_key')}",
                prompt_text=generated_prompt,
                language=language,
                prompt_type="video",
                analysis_notes=f"Transition: {from_stage.get('name_en')} → {to_stage.get('name_en')}",
            )
            
        except Exception as e:
            logger.error(f"[Mode8 Videos] Failed to generate prompt for transition {from_stage.get('stage_key')} → {to_stage.get('stage_key')}: {e}")
            # Fallback to original template-based prompt
            fallback_prompt = f"Timelapse transition from {from_stage.get('name_en')} to {to_stage.get('name_en')}"
            return GeneratedPrompt(
                stage_index=from_stage.get("index", 0),
                stage_key=f"{from_stage.get('stage_key')}_to_{to_stage.get('stage_key')}",
                prompt_text=fallback_prompt,
                language=language,
                prompt_type="video",
                analysis_notes="Fallback prompt (LLM failed)",
            )


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

async def generate_contextual_prompts(
    scenario: dict[str, Any],
    language: str = "en",
) -> dict[str, Any]:
    """
    Main entry point for contextual prompt generation.
    
    Executes the full 3-stage pipeline:
    1. Context Analysis (LLM)
    2. Image Prompt Generation (LLM + History)
    3. Video Prompt Generation (LLM + Recursive Analysis)
    
    Args:
        scenario: Complete scenario from scenario_writer
        language: Output language
        
    Returns:
        dict with image_prompts, video_prompts, and context
    """
    logger.info("[Mode8 Contextual] Starting 3-stage prompt generation pipeline...")
    
    # Stage 1: Context Analysis
    context = await ContextAnalyzer.analyze(scenario)
    
    # Stage 2: Image Prompts
    image_prompts = await ImagePromptGenerator.generate_all_prompts(
        scenario=scenario,
        context=context,
        language=language,
    )
    
    # Stage 3: Video Prompts
    video_prompts = await VideoPromptGenerator.generate_all_prompts(
        scenario=scenario,
        context=context,
        image_prompts=image_prompts,
        language=language,
    )
    
    logger.success(f"[Mode8 Contextual] Pipeline complete: {len(image_prompts)} images, {len(video_prompts)} videos")
    
    return {
        "context": context.to_dict(),
        "image_prompts": [p.to_dict() for p in image_prompts],
        "video_prompts": [p.to_dict() for p in video_prompts],
        "scenario": scenario,
    }
