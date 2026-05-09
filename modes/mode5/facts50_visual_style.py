"""
Единый визуальный стиль для mode5 «77 фактов»: эпоха и эстетика берутся из темы,
а не из дефолта «премодерн» (как в общем mode13).
"""

from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from config import settings
from utils.llm import make_llm


_FALLBACK_HORIZONTAL = (
    "Unified stylized cinematic illustration style with a gentle semi-cartoon look: clean linework, soft painterly shading, calm mood suitable for sleep listening. "
    "Not photorealistic and not anime exaggeration: believable proportions, readable environments, warm friendly visual language. "
    "For broad modern geography or country topics, default to contemporary scenes (accurate modern cities, landscapes, daily life) "
    "— avoid generic medieval castles unless the topic is explicitly historical. "
    "Consistent horizontal 16:9 full-frame composition."
)


async def derive_facts50_unified_style_suffix(
    topic_line: str,
    sample_fact_lines: list[str],
    narration_excerpt: str,
    *,
    output_format: str = "horizontal",
    control: dict | None = None,
) -> str:
    """Один «визуальный библ» для всех кадров facts50: современность vs история — из контекста темы."""
    from pipeline_control import checkpoint

    await checkpoint(control)
    topic = (topic_line or "").strip()[:500]
    samples = "\n".join(f"- {s}" for s in (sample_fact_lines or [])[:18] if (s or "").strip())
    excerpt = (narration_excerpt or "").strip()[:4000]
    horiz = (output_format or "").strip().lower() == "horizontal" or getattr(settings, "mode5_video_format", "horizontal") == "horizontal"
    framing = "Horizontal 16:9 landscape composition" if horiz else "Vertical 9:16 portrait composition"

    try:
        llm = make_llm(temperature=0.38)
        sys = SystemMessage(
            content=(
                "You write ONE unified visual art direction for ALL illustration frames in a calm educational "
                "\"77 facts\" documentary meant for sleep-time listening (voiceover), not a thriller.\n\n"
                "STYLE PRIORITY:\n"
                "- Use a stylized cinematic illustration look with a gentle semi-cartoon feel.\n"
                "- Explicitly avoid strict photorealism.\n"
                "- Keep characters and architecture believable (no caricature, no chibi, no comic-book exaggeration).\n"
                "- Keep colors soft, clean, and slightly dreamy; readable details over noisy textures.\n\n"
                "CRITICAL — infer PRIMARY ERA from the HEADLINE and fact samples:\n"
                "- Broad modern country / travel / culture headlines (e.g. \"77 facts about France\", \"Italy\", \"oceans\"): "
                "default to CONTEMPORARY stylized illustration imagery — modern cities, present-day landscapes, current architecture, "
                "editorial travel-documentary composition in semi-cartoon rendering. Do NOT drift into medieval castles, knights, or "
                "generic fantasy Europe unless samples clearly focus on medieval history.\n"
                "- Explicit ancient / medieval / early-modern history topics: period-accurate environments, costumes, and props; "
                "still stylized cinematic illustration, not fantasy kitsch.\n"
                "- Pure science / space / medicine / tech: clean lab, observatory, modern infographic-free documentary look.\n"
                "- Wildlife / nature: naturalistic but stylized documentary look.\n\n"
                "Output 5–8 short English sentences: framing, lighting, palette, level of stylization (semi-cartoon), mood (soft, calm), "
                "what to AVOID for THIS topic (e.g. if modern France — say explicitly: no medieval default, no photoreal look). "
                "Same cohesive look for every slide. No proper names of celebrities.\n"
                f"End the last sentence with exactly this framing clause: {framing}. "
                "Do not append a long list of no-text/no-logo rules — the image pipeline adds global hard rules once."
            )
        )
        hum = HumanMessage(
            content=(
                f"Video headline / topic:\n{topic}\n\n"
                f"Sample fact one-liners (may be mixed):\n{samples or '(none)'}\n\n"
                f"Narration excerpt (for tone):\n{excerpt[:3500]}"
            )
        )
        resp = await asyncio.wait_for(llm.ainvoke([sys, hum]), timeout=120.0)
        text = (getattr(resp, "content", None) or "").strip()
        if len(text) < 60:
            logger.warning("[facts50] Short style suffix from LLM, using fallback")
            return _FALLBACK_HORIZONTAL
        return text
    except Exception as e:
        logger.warning(f"[facts50] derive_facts50_unified_style_suffix failed: {e}")
        return _FALLBACK_HORIZONTAL
