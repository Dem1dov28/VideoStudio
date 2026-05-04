from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Mode5PromptProfile:
    style_id: str
    style_description: str
    mode_rules: str


@dataclass(frozen=True)
class Mode5RenderSlots:
    """Per-sub_mode: concrete scene/camera/quality hints so the T2I prompt is operational, not only policy."""

    subject: str
    environment: str
    action: str
    mood: str
    camera: str
    quality: str
    extra_rules: tuple[str, ...] = ()


@dataclass(frozen=True)
class Mode5PromptPayload:
    final_prompt: str
    debug_prompt: str


_DEFAULT_PROFILE_KEY = "manual"

_MODE5_PROMPT_PROFILES: dict[str, Mode5PromptProfile] = {
    "manual": Mode5PromptProfile(
        style_id="realistic_documentary",
        style_description=(
            "Realistic documentary still frame, natural color balance, physically plausible lighting, "
            "clear environment details, no stylized exaggeration."
        ),
        mode_rules=(
            "Focus on practical real-world depiction of the spoken content. "
            "Prefer literal setting and action over symbolism."
        ),
    ),
    "bible": Mode5PromptProfile(
        style_id="classical_painterly",
        style_description=(
            "Classical painterly realism, restrained brush texture, warm chiaroscuro, "
            "period-appropriate clothing and architecture."
        ),
        mode_rules=(
            "Keep biblical and near-east historical atmosphere without fantasy excess. "
            "Depict respectful human scenes and period-consistent props."
        ),
    ),
    "facts50": Mode5PromptProfile(
        style_id="clean_editorial_realistic",
        style_description=(
            "Clean editorial realism, crisp composition, balanced contrast, "
            "informative documentary look with grounded contemporary/historical fidelity by context."
        ),
        mode_rules=(
            "Prioritize factual clarity and concrete visual evidence from narration. "
            "Avoid decorative or abstract scene choices."
        ),
    ),
    "outline": Mode5PromptProfile(
        style_id="neutral_documentary",
        style_description=(
            "Neutral documentary realism, straightforward framing, controlled color palette, "
            "unobtrusive cinematic lighting."
        ),
        mode_rules=(
            "Choose one clear scene that communicates the current spoken point directly. "
            "Maintain continuity with the surrounding chunk context."
        ),
    ),
    "book_night": Mode5PromptProfile(
        style_id="soft_cinematic_realistic",
        style_description=(
            "Soft cinematic realism, calm low-contrast lighting, gentle depth cues, "
            "cozy but realistic environment rendering with layered production design."
        ),
        mode_rules=(
            "Show lived scenes implied by ideas and habits. "
            "Weave the episode's themes into the set: props, era, weather, crafts, textures, and architecture that echo the narration — "
            "avoid a sparse anonymous room unless the script explicitly calls for it. "
            "Preserve restful, quiet mood; keep energy in detail density, not chaos."
        ),
    ),
    "unwritten_chapter": Mode5PromptProfile(
        style_id="archival_documentary_muted",
        style_description=(
            "Archival documentary realism, muted dark palette (sepia/charcoal/olive), "
            "restrained grain, evidence-oriented composition."
        ),
        mode_rules=(
            "Prefer investigation-oriented scenes: archive interiors, evidence handling, "
            "location trace, witness environment, period-consistent context."
        ),
    ),
}

# Per-mode render hints: what was missing from a pure policy prompt (slots, camera, quality, mode-specific hard rules).
_MODE5_RENDER_SLOTS: dict[str, Mode5RenderSlots] = {
    "manual": Mode5RenderSlots(
        subject="1-2 primary people or clear focal subjects implied by the scene source (generic roles if names unknown)",
        environment="one believable contemporary or historical real-world place matching the spoken line (no stock fantasy)",
        action="one clear in-progress action from the scene source (gesture, movement, task)",
        mood="sober documentary, grounded, non-symbolic",
        camera="medium or medium-wide shot, eye-level or slight low angle, single stable frame",
        quality=(
            "natural skin and fabric texture, realistic daylight or practical indoor light, "
            "sharp enough for environment read, no HDR glow, no plastic CGI"
        ),
        extra_rules=(
            "Continuity: surrounding context may fix recurring place or era only if it does not contradict the scene source.",
            "Add environmental storytelling: secondary props, architecture, weather, or workplace detail that reinforces the narration — "
            "avoid a blank minimalist void.",
        ),
    ),
    "bible": Mode5RenderSlots(
        subject="1-3 figures in modest period dress implied by the scene source; respectful poses, no caricature",
        environment=(
            "ancient Near East plausible architecture/landscape from the spoken moment (no modern objects); "
            "populate the world with period props, paths, vessels, animals, or city life that support the beat"
        ),
        action="one narrative action from the scene source (travel, teaching moment, labor, prayer posture as described)",
        mood="reverent classical tableau, warm chiaroscuro, restrained emotion",
        camera="medium shot or two-shot, stable composition, painterly depth",
        quality=(
            "oil-painting-like controlled brush softness, coherent period materials (stone, linen, clay), "
            "no neon, no anachronistic tech"
        ),
        extra_rules=(
            "No open scripture pages or scroll text as the hero subject; show people and place as primary read.",
            "If the scene source implies a specific era, match costumes and props to that era only.",
        ),
    ),
    "facts50": Mode5RenderSlots(
        subject="the concrete fact carrier: people in roles, object, place, or process named by the scene source",
        environment="single setting that makes the fact obvious at a glance (lab, street, landscape, workshop)",
        action="one illustrative action proving the fact (observing, building, measuring, traveling)",
        mood="clear educational editorial, calm, readable",
        camera="medium shot or clean wide establishing if the place is the fact; horizon straight",
        quality=(
            "high clarity edges for key objects, balanced exposure, no chart/infographic overlays, "
            "no decorative bokeh that hides the subject"
        ),
        extra_rules=(
            "The image must visualize the current fact line, not a generic stock scene.",
            "Infer modern versus historical setting from the scene source; do not default to the wrong century.",
        ),
    ),
    "outline": Mode5RenderSlots(
        subject="entities implied by the current outline beat (people, institution, object)",
        environment="one location that matches the chapter beat; align with surrounding context for series continuity",
        action="one beat-appropriate action from the scene source",
        mood="neutral explanatory documentary, not melodramatic",
        camera="medium shot, straightforward framing, readable spatial layout",
        quality=(
            "even lighting, controlled palette, documentary sharpness without stylized grading"
        ),
        extra_rules=(
            "Use surrounding context to keep recurring motifs consistent when the segment is thin.",
            "If the scene source is abstract, still render one concrete literal scene that instantiates it.",
            "Include midground/background interest (tools, signage shapes without text, vehicles, landscape) so the frame feels specific to the beat.",
        ),
    ),
    "book_night": Mode5RenderSlots(
        subject="1-2 people in everyday roles implied by the scene source (no celebrity likeness)",
        environment=(
            "a specific, lived-in interior or exterior with storytelling depth: foreground prop, midground figures, "
            "background context (street, garden, workshop corner, kitchen detail, transit platform) aligned to the spoken habit or reflection"
        ),
        action="gentle routine action (walking, sitting, hands busy with a non-text prop, conversation posture)",
        mood="soft low-contrast calm, sleep-friendly, intimate but realistic",
        camera="medium-close or medium, gentle depth, no harsh dutch angle; frame should feel art-directed, not stock-photo empty",
        quality=(
            "soft shadows, low noise, cozy but photoreal materials, no harsh speculars, no surreal glow; "
            "rich small-object and texture detail that supports the theme"
        ),
        extra_rules=(
            "Echo the book or episode topic through environment and props (stacked closed books as shapes, lamp light, textiles, tools, "
            "maps as texture without labels) — not as readable pages, covers, titles, or UI.",
            "No readable text on walls, screens, or props; keep typography out of frame.",
        ),
    ),
    "unwritten_chapter": Mode5RenderSlots(
        subject="investigators, archivists, or witnesses as roles implied by the scene source (1-2 primary)",
        environment="archive room, briefing table, map wall, field trace, or period interior tied to the claim",
        action="evidence handling: comparing folders, marking maps, examining records, sealing boxes (no legible text)",
        mood="muted investigative tension, documentary restraint, no thriller neon",
        camera="medium or over-shoulder on desk evidence, practical lamp motivation allowed",
        quality=(
            "muted palette, fine grain, tactile paper and metal, believable shadows, no glossy blockbuster grade"
        ),
        extra_rules=(
            "Include investigation props such as folders, maps, stamps, tapes, or tools as supporting objects without readable text.",
        ),
    ),
}

_CONFLICT_RULE = (
    "Priority rule: the scene source is authoritative. "
    "If continuity context conflicts with the scene source, ignore conflicting continuity details."
)

_ANTI_ABSTRACT_RULE = (
    "Anti-abstract rule: no symbolic/metaphoric/conceptual scene substitutions; "
    "render literal filmable content from the scene source."
)
_SINGLE_SCENE_RULE = (
    "Critical single-scene rule: generate exactly ONE photo with ONE scene only. "
    "Do not merge multiple moments, multiple locations, or multiple timeline beats into one image."
)


def normalize_mode5_sub_mode(sub_mode: str | None) -> str:
    sm = str(sub_mode or "").strip().lower()
    if sm in _MODE5_PROMPT_PROFILES:
        return sm
    return _DEFAULT_PROFILE_KEY


def mode5_style_lock_for_sub_mode(sub_mode: str | None) -> str:
    profile = _MODE5_PROMPT_PROFILES[normalize_mode5_sub_mode(sub_mode)]
    return profile.style_description


def mode5_style_id_for_sub_mode(sub_mode: str | None) -> str:
    profile = _MODE5_PROMPT_PROFILES[normalize_mode5_sub_mode(sub_mode)]
    return profile.style_id


def _clean_text(text: str, *, limit: int) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())[:limit]


def _output_format_rule(output_format: str | None) -> str:
    fmt = str(output_format or "").strip().lower()
    if fmt == "vertical":
        return "Vertical portrait composition (9:16)."
    return "Horizontal landscape composition (16:9)."


def _chunk_context_text(chunk_context: str | None) -> str:
    ctx = _clean_text(chunk_context or "", limit=900)
    return ctx if ctx else "No extra chunk context."


def _build_mode5_prompt_payload(
    *,
    sub_mode: str | None,
    segment_text: str,
    chunk_context: str | None,
    style_lock: str,
    output_format: str | None,
) -> str:
    mode_key = normalize_mode5_sub_mode(sub_mode)
    profile = _MODE5_PROMPT_PROFILES[mode_key]
    slots = _MODE5_RENDER_SLOTS[mode_key]
    segment = _clean_text(segment_text, limit=1200)
    context = _chunk_context_text(chunk_context)
    style = _clean_text(style_lock, limit=600) or profile.style_description
    geometry = _output_format_rule(output_format)
    no_text_rule = (
        "There must be absolutely no visible text anywhere in the image; no captions, no labels, no headings, "
        "no letters, no numbers, no readable papers, no UI, no logos, no watermarks."
    )
    single_image_rule = (
        "One full-frame image only, one continuous scene, one location, one moment; "
        "no tiled layout, no side-by-side layout, no segmented layout, no panel layout, no small inset pictures."
    )

    scene_slots_line = (
        f"Build the scene around {slots.subject}, inside {slots.environment}, showing {slots.action}. "
        f"The mood is {slots.mood}, with {slots.camera}."
    )
    quality_line = f"Use {slots.quality}."
    if mode_key == "book_night":
        literal_scene_rule = (
            "Anchor the frame in literal, filmable reality (people, place, action). "
            "Enrich the world with concrete set dressing and textures that echo the narration's themes — "
            "still one real moment, not a surreal metaphor collage unrelated to the spoken line."
        )
    else:
        literal_scene_rule = (
            "Do not create symbolic, metaphorical, or conceptual substitutions; render literal filmable content from the narration moment."
        )

    final_parts: list[str] = [
        "Create one cinematic still image.",
        f"Use a visual style of {style}",
        f"Base the image on this narration moment, {segment}",
        f"For continuity of place, era, people, or mood, consider this nearby narration only when it does not conflict, {context}",
        f"Follow this visual direction, {profile.mode_rules}",
        "The narration moment is authoritative; if nearby narration conflicts with it, ignore the conflicting nearby details.",
        "Choose the subject, action, and environment from the narration moment first.",
        literal_scene_rule,
        "Generate exactly one photo with exactly one scene only.",
        "Do not merge multiple moments, multiple locations, or multiple timeline beats into one image.",
        single_image_rule,
        scene_slots_line,
        quality_line,
        *[r for r in slots.extra_rules if r],
        f"Use {geometry}",
        no_text_rule,
        "Final result must look like one finished photograph or documentary frame, not a presentation-style layout.",
    ]

    debug_parts: list[str] = [
        "Single still image prompt for narrated video segment.",
        f"Mode profile: {mode_key}.",
        f"Locked style id: {profile.style_id}.",
        f"Style lock: {style}",
        f"Mode constraints: {profile.mode_rules}",
        _CONFLICT_RULE,
        "Scene selection rule: derive subject/action/environment from CURRENT_SEGMENT first.",
        "Chunk context may be used only for continuity of characters/location/time, not to replace current segment meaning.",
        _ANTI_ABSTRACT_RULE,
        _SINGLE_SCENE_RULE,
        f"CURRENT_SEGMENT: {segment}",
        f"CHUNK_CONTEXT: {context}",
        scene_slots_line,
        quality_line,
        *[r for r in slots.extra_rules if r],
        f"Technical rules: {geometry} One dominant uninterrupted scene, no collage, no split layout, no readable text, no logos, no UI, no watermarks.",
        "Output intent: produce a literal, filmable scene that matches the current spoken segment.",
    ]
    return Mode5PromptPayload(final_prompt=" ".join(final_parts), debug_prompt=" ".join(debug_parts))


def build_mode5_image_prompt(
    *,
    sub_mode: str | None,
    segment_text: str,
    chunk_context: str | None,
    style_lock: str,
    output_format: str | None,
) -> str:
    return _build_mode5_prompt_payload(
        sub_mode=sub_mode,
        segment_text=segment_text,
        chunk_context=chunk_context,
        style_lock=style_lock,
        output_format=output_format,
    ).final_prompt


def build_mode5_image_prompt_debug(
    *,
    sub_mode: str | None,
    segment_text: str,
    chunk_context: str | None,
    style_lock: str,
    output_format: str | None,
) -> str:
    return _build_mode5_prompt_payload(
        sub_mode=sub_mode,
        segment_text=segment_text,
        chunk_context=chunk_context,
        style_lock=style_lock,
        output_format=output_format,
    ).debug_prompt
