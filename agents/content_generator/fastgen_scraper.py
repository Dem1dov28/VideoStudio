"""
Точка входа FastGen: при FASTGEN_HTTP_BASE_URL — media_gen_api v2 через httpx (см. fastgen_http);
иначе — Playwright (fast-gen.ai в браузере, fastgen_playwright).

FastGenScraper и вспомогательные символы для UI-тестов реэкспортируются из fastgen_playwright.
"""

from __future__ import annotations

import threading
from pathlib import Path

from config import settings

from agents.content_generator.fastgen_exceptions import FastGenCancelled, VideoGenerationError
from agents.content_generator.fastgen_playwright import (
    FastGenScraper,
    _GENERATE_SELECTORS,
    _PROMPT_SELECTORS,
    _find_first,
    _react_fill,
    _toggle_keyframes_mode,
    _upload_keyframe_end,
    _upload_keyframe_start,
)
from agents.content_generator.fastgen_prompts import prepare_fastgen_prompt_for_ui


def _use_http() -> bool:
    return bool((getattr(settings, "fastgen_http_base_url", None) or "").strip())


async def generate_images_fastgen(
    prompts: list[str],
        output_dir: Path,
    parallel: bool = True,
        cancel_event: threading.Event | None = None,
    ) -> list[Path]:
    if _use_http():
        from agents.content_generator import fastgen_http

        return await fastgen_http.generate_images_fastgen(
            prompts, output_dir, parallel=parallel, cancel_event=cancel_event
        )
    from agents.content_generator import fastgen_playwright as _pw

    return await _pw.generate_images_fastgen(
        prompts, output_dir, parallel=parallel, cancel_event=cancel_event
    )


async def generate_images_with_references_fastgen(
    prompts_with_refs: list[tuple[str, list[Path]]],
        output_dir: Path,
    parallel: bool = True,
    max_workers: int | None = None,
    ) -> list[Path]:
    if _use_http():
        from agents.content_generator import fastgen_http

        return await fastgen_http.generate_images_with_references_fastgen(
            prompts_with_refs, output_dir, parallel=parallel, max_workers=max_workers
        )
    from agents.content_generator import fastgen_playwright as _pw

    return await _pw.generate_images_with_references_fastgen(
        prompts_with_refs, output_dir, parallel=parallel, max_workers=max_workers
    )


async def generate_images_chain_fastgen(
    steps: list[tuple[str, int | None]],
    output_dir: Path,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
    if _use_http():
        from agents.content_generator import fastgen_http

        return await fastgen_http.generate_images_chain_fastgen(steps, output_dir, cancel_event=cancel_event)
    from agents.content_generator import fastgen_playwright as _pw

    return await _pw.generate_images_chain_fastgen(steps, output_dir, cancel_event=cancel_event)


async def generate_images_chain_from_seed_fastgen(
    seed_image: Path | str,
    steps: list[tuple[str, int]],
    output_dir: Path,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
    if _use_http():
        from agents.content_generator import fastgen_http

        return await fastgen_http.generate_images_chain_from_seed_fastgen(
            seed_image, steps, output_dir, cancel_event=cancel_event
        )
    from agents.content_generator import fastgen_playwright as _pw

    return await _pw.generate_images_chain_from_seed_fastgen(
        seed_image, steps, output_dir, cancel_event=cancel_event
    )


async def generate_videos_fastgen(
    prompts: list[str],
    output_dir: Path,
    reference_image_path: str | Path | None = None,
    cancel_event: threading.Event | None = None,
    *,
    mode4_veo_flow_flower: bool = False,
) -> list[Path | None]:
    if _use_http():
        from agents.content_generator import fastgen_http

        return await fastgen_http.generate_videos_fastgen(
            prompts,
                output_dir,
                        reference_image_path=reference_image_path,
                        cancel_event=cancel_event,
            mode4_veo_flow_flower=mode4_veo_flow_flower,
        )
    from agents.content_generator import fastgen_playwright as _pw

    return await _pw.generate_videos_fastgen(
            prompts,
            output_dir,
        reference_image_path=reference_image_path,
        cancel_event=cancel_event,
        mode4_veo_flow_flower=mode4_veo_flow_flower,
        )


async def generate_single_video_fastgen(
    prompt: str,
    output_dir: Path,
    index: int,
    reference_image_path: str | Path | None = None,
    *,
    reference_image_paths: list[str | Path] | None = None,
    cancel_event: threading.Event | None = None,
    mode4_veo_flow_flower: bool = False,
) -> Path | None:
    if _use_http():
        from agents.content_generator import fastgen_http

        return await fastgen_http.generate_single_video_fastgen(
            prompt,
            output_dir,
            index,
            reference_image_path=reference_image_path,
            reference_image_paths=reference_image_paths,
            cancel_event=cancel_event,
            mode4_veo_flow_flower=mode4_veo_flow_flower,
        )
    from agents.content_generator import fastgen_playwright as _pw

    return await _pw.generate_single_video_fastgen(
        prompt,
        output_dir,
        index,
        reference_image_path=reference_image_path,
                        reference_image_paths=reference_image_paths,
        cancel_event=cancel_event,
        mode4_veo_flow_flower=mode4_veo_flow_flower,
    )


async def generate_videos_fastgen_multi_ref(
    prompts: list[str],
    output_dir: Path,
    reference_image_paths: list[Path],
) -> list[Path | None]:
    if _use_http():
        from agents.content_generator import fastgen_http

        return await fastgen_http.generate_videos_fastgen_multi_ref(prompts, output_dir, reference_image_paths)
    from agents.content_generator import fastgen_playwright as _pw

    return await _pw.generate_videos_fastgen_multi_ref(prompts, output_dir, reference_image_paths)


async def generate_single_video_multi_ref(
    index: int,
    prompt: str,
    output_dir: Path,
    reference_image_paths: list[Path],
) -> Path | None:
    if _use_http():
        from agents.content_generator import fastgen_http

        return await fastgen_http.generate_single_video_multi_ref(
            index, prompt, output_dir, reference_image_paths
        )
    from agents.content_generator import fastgen_playwright as _pw

    return await _pw.generate_single_video_multi_ref(index, prompt, output_dir, reference_image_paths)


async def generate_video_from_keyframes(
    prompt: str,
    output_dir: Path,
    start_frame_path: Path,
    end_frame_path: Path,
    index: int = 0,
    *,
    video_aspect_ratio: str | None = None,
) -> Path | None:
    if _use_http():
        from agents.content_generator import fastgen_http

        return await fastgen_http.generate_video_from_keyframes(
            prompt,
            output_dir,
            start_frame_path,
            end_frame_path,
            index=index,
            video_aspect_ratio=video_aspect_ratio,
        )
    from agents.content_generator import fastgen_playwright as _pw

    return await _pw.generate_video_from_keyframes(
        prompt,
        output_dir,
        start_frame_path,
        end_frame_path,
        index=index,
        video_aspect_ratio=video_aspect_ratio,
    )


__all__ = [
    "FastGenCancelled",
    "FastGenScraper",
    "VideoGenerationError",
    "_GENERATE_SELECTORS",
    "_PROMPT_SELECTORS",
    "_find_first",
    "_react_fill",
    "_toggle_keyframes_mode",
    "_upload_keyframe_end",
    "_upload_keyframe_start",
    "generate_images_chain_fastgen",
    "generate_images_chain_from_seed_fastgen",
    "generate_images_fastgen",
    "generate_images_with_references_fastgen",
    "generate_single_video_fastgen",
    "generate_single_video_multi_ref",
    "generate_video_from_keyframes",
    "generate_videos_fastgen",
    "generate_videos_fastgen_multi_ref",
    "prepare_fastgen_prompt_for_ui",
]
