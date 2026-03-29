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
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "visual_progression": [sc.to_dict() for sc in self.visual_progression],
            "overall_narrative": self.overall_narrative,
            "style_consistency_notes": self.style_consistency_notes,
            "location_atmosphere": self.location_atmosphere,
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
- Location: {location}
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
- Consider camera angles and lighting changes
- Ensure architectural consistency while adding variety

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
- Location: {location}
- Camera Specs: {camera_specs}

PREVIOUS IMAGE PROMPTS (DO NOT REPEAT):
{previous_image_prompts}

YOUR TASK:
Write a detailed, cinematic image prompt that:
1. Captures THIS SPECIFIC stage's unique visual character
2. DOES NOT repeat elements from previous stages (see above)
3. Maintains architectural consistency
4. Uses specific, vivid details (NOT generic descriptions)
5. Includes camera angle, lighting, and composition details

CRITICAL RULES:
- NEVER use phrases like "similar to", "same as", "like before"
- ALWAYS describe what's NEW and DIFFERENT in this stage
- Use concrete visual details (materials, textures, colors, shadows)
- Make each prompt feel like a professional photograph

Write the prompt in English for AI image generation."""


VIDEO_PROMPT_GENERATION_PROMPT = """You are an expert AI video prompt engineer for construction timelapse transitions.

TASK: Generate a DYNAMIC video prompt for transition from Stage {from_index} to Stage {from_index_plus1}.

TRANSITION ANALYSIS:
FROM: {from_stage_name} → TO: {to_stage_name}

IMAGE PROMPTS FOR THESE STAGES:
- From Stage Image: {from_image_prompt}
- To Stage Image: {to_image_prompt}

PREVIOUS VIDEO PROMPTS (AVOID REPETITION):
{previous_video_prompts}

CONTEXT FROM SCENARIO ANALYSIS:
{scenario_context}

YOUR TASK:
Create a captivating video transition prompt that:
1. Shows the TRANSFORMATION PROCESS (not just before/after)
2. Focuses on WHAT CHANGES between these two specific stages
3. Uses dynamic action verbs (building, installing, rising, assembling)
4. Includes worker activities and machinery in motion
5. AVOIDS repeating transition patterns from previous videos

CRITICAL RULES:
- This is a TIMELAPSE transition, not instant transformation
- Show REAL CONSTRUCTION WORK (workers, tools, materials moving)
- NEVER use "magical appearance" or "instant change" language
- Describe SPECIFIC construction actions for THIS transition
- Keep camera FIXED (tripod-mounted look)
- Forward motion ONLY (no reversing)

Write the prompt in English for AI video generation."""


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
            
            house_style = scenario.get("house_style", "modern")
            location = scenario.get("location", "suburbs")
            
            # Build prompt
            prompt = CONTEXT_ANALYSIS_PROMPT.format(
                house_style=house_style,
                location=location,
                total_stages=len(stages),
                stages_list=stages_list,
            )
            
            # Invoke LLM
            response = await llm.ainvoke(prompt)
            
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
                house_style=scenario_context.style_consistency_notes,
                location=scenario_context.location_atmosphere,
                camera_specs=camera_specs,
                previous_image_prompts=prev_prompts_text,
            )
            
            # Invoke LLM
            response = await llm.ainvoke(prompt_text)
            
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
    """Extract camera specs from context."""
    # For now, return generic specs
    return "Wide shot, natural daylight, tripod-mounted camera, consistent angle across all stages"


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
        scenario_context: ScenarioContext,
        previous_video_prompts: list[GeneratedPrompt],
        language: str = "en",
    ) -> GeneratedPrompt:
        """Generate single video prompt with full recursive analysis."""
        try:
            llm = make_llm(temperature=0.8)
            
            from_index = from_stage.get("index", 0)
            
            # Build previous video prompts context
            if previous_video_prompts:
                prev_videos_text = "\n\n".join([
                    f"--- Transition {p.stage_index + 1} ---\n{p.prompt_text}"
                    for p in previous_video_prompts[-3:]  # Last 3 prompts
                ])
            else:
                prev_videos_text = "None (first video transition)"
            
            # Build scenario context summary
            scenario_summary = f"""
Overall Narrative: {scenario_context.overall_narrative}
Style Consistency: {scenario_context.style_consistency_notes}
Location Atmosphere: {scenario_context.location_atmosphere}
Total Transitions: {len(previous_video_prompts) + 1}
            """.strip()
            
            # Build prompt
            prompt_text = VIDEO_PROMPT_GENERATION_PROMPT.format(
                from_index=from_index + 1,
                from_index_plus1=from_index + 2,
                from_stage_name=from_stage.get("name_en", ""),
                to_stage_name=to_stage.get("name_en", ""),
                from_image_prompt=from_image_prompt[:500],
                to_image_prompt=to_image_prompt[:500],
                previous_video_prompts=prev_videos_text,
                scenario_context=scenario_summary,
            )
            
            # Invoke LLM
            response = await llm.ainvoke(prompt_text)
            
            generated_prompt = response.content.strip()
            
            return GeneratedPrompt(
                stage_index=from_index,
                stage_key=f"{from_stage.get('stage_key')}_to_{to_stage.get('stage_key')}",
                prompt_text=generated_prompt,
                language=language,
                prompt_type="video",
                analysis_notes=f"Transition analysis: {from_stage.get('name_en')} → {to_stage.get('name_en')}",
            )
            
        except Exception as e:
            logger.error(f"[Mode8 Videos] Failed to generate prompt for transition {from_stage.get('stage_key')} → {to_stage.get('stage_key')}: {e}")
            # Fallback
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
