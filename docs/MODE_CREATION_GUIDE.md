# Руководство по созданию нового режима генерации видео

Полное руководство по добавлению нового режима в VideoStudio на основе архитектуры Mode 8 (House Building Timelapse).

Mode 8 демонстрирует:
- **Последовательную генерацию** изображений с цепочкой референсов
- **Keyframe-подход** для плавных переходов между кадрами
- **Продвинутую обработку ошибок** с retry-логикой
- **Детальную структуру промптов** с интенсивностью, временем суток, пиковыми моментами
- **Publishing metadata** для YouTube Shorts

---

## Структура режима

### Файловая структура

```
modes/
├── modeN/
│   ├── __init__.py              # Экспорт главной функции пайплайна
│   ├── pipeline.py              # Главный пайплайн режима
│   ├── scenario_writer.py       # Генерация сценария с Pydantic моделями
│   ├── video_generator.py       # Последовательная генерация + keyframe видео
│   ├── video_assembler.py       # Сборка финального видео
│   └── publishing_metadata.py   # Метаданные для публикации (опционально)
```

---

## Шаг 1: Создание модуля режима

### `modes/modeN/__init__.py`

```python
"""Mode N: Название режима — краткое описание."""
from modes.modeN.pipeline import run_modeN_pipeline

__all__ = ["run_modeN_pipeline"]
```

---

## Шаг 2: Scenario Writer с Pydantic моделями

### `modes/modeN/scenario_writer.py`

```python
"""
Mode N Scenario Writer — Генерация структурированного сценария.

Использует Pydantic для валидации и типизации данных сценария.
Каждая сцена содержит детальные параметры для генерации.
"""

from __future__ import annotations

import random
from typing import Any

from loguru import logger
from pydantic import BaseModel


# ═══════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ СТИЛЕЙ И ЛОКАЦИЙ
# ═══════════════════════════════════════════════════════════════════════════

STYLE_CONFIGS: dict[str, dict[str, Any]] = {
    "style1": {
        "name": "название на русском",
        "name_en": "english name",
        "visual": "визуальное описание для промптов",
        "features": "ключевые особенности",
    },
    # ... другие стили
}

LOCATION_CONFIGS: dict[str, dict[str, Any]] = {
    "location1": {
        "name": "название",
        "name_en": "english name",
        "visual": "визуальное описание",
        "background": "описание фона",
    },
    # ... другие локации
}


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC МОДЕЛИ
# ═══════════════════════════════════════════════════════════════════════════

class SceneStage(BaseModel):
    """Одна сцена/этап в сценарии."""
    index: int
    stage_key: str                    # Уникальный ключ этапа
    name: str                         # Название на русском
    name_en: str                      # Название на английском
    start_state: str                  # Начальное состояние
    end_state: str                    # Конечное состояние
    visual_prompt: str                # Визуальный промпт для генерации
    action: str                       # Действие/активность
    duration: int = 6                 # Длительность в секундах
    
    # Дополнительные параметры для детализации
    workers: str | None = None        # Описание работников
    workers_en: str | None = None
    machinery: str | None = None      # Описание техники
    machinery_en: str | None = None
    micro_actions: list[str] = []     # Микро-действия для реализма
    micro_actions_en: list[str] = []
    
    # Параметры для промптов
    build_intensity: str = "medium"   # low | medium | high
    time_of_day: str = "midday"       # morning | midday | afternoon | golden_hour
    is_peak_moment: bool = False      # Пиковый визуальный момент


class Scenario(BaseModel):
    """Полный сценарий."""
    title: str
    title_en: str
    style: str
    style_name: str
    location: str
    location_name: str
    scenes: list[SceneStage]
    total_duration: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ СЦЕНАРИЯ
# ═══════════════════════════════════════════════════════════════════════════

def generate_scenario(
    preferred_style: str | None = None,
    preferred_location: str | None = None,
    num_stages: int = 5,
    language: str = "ru",
) -> Scenario:
    """
    Генерация структурированного сценария.
    
    Args:
        preferred_style: Предпочтительный стиль (или None для случайного)
        preferred_location: Предпочтительная локация
        num_stages: Количество этапов (5-8)
        language: Язык вывода
    
    Returns:
        Scenario с полной структурой
    """
    # Выбор стиля и локации
    style_key = _select_style(preferred_style)
    loc_key = _select_location(preferred_location)
    
    style = STYLE_CONFIGS[style_key]
    loc = LOCATION_CONFIGS[loc_key]
    
    # Получение последовательности этапов
    stage_keys = _get_stage_sequence(num_stages)
    
    # Построение этапов
    stages = []
    for i, stage_key in enumerate(stage_keys):
        stage_data = _get_stage_data(stage_key)
        
        visual_prompt = _build_visual_prompt(
            stage_key, style_key, loc_key, language
        )
        
        stage = SceneStage(
            index=i,
            stage_key=stage_key,
            name=stage_data["name"],
            name_en=stage_data["name_en"],
            start_state=stage_data["start_state"],
            end_state=stage_data["end_state"],
            visual_prompt=visual_prompt,
            action=stage_data["action"],
            duration=6,
            workers=stage_data.get("workers"),
            workers_en=stage_data.get("workers_en"),
            machinery=stage_data.get("machinery"),
            machinery_en=stage_data.get("machinery_en"),
            micro_actions=stage_data.get("micro_actions", []),
            micro_actions_en=stage_data.get("micro_actions_en", []),
            build_intensity=stage_data.get("build_intensity", "medium"),
            time_of_day=stage_data.get("time_of_day", "midday"),
            is_peak_moment=stage_data.get("is_peak_moment", False),
        )
        stages.append(stage)
    
    # Формирование заголовка
    if language == "en":
        title = f"Timelapse: {style['name_en']}"
        title_en = title
    else:
        title = f"Таймлапс: {style['name']}"
        title_en = f"Timelapse: {style['name_en']}"
    
    return Scenario(
        title=title,
        title_en=title_en,
        style=style_key,
        style_name=style["name"],
        location=loc_key,
        location_name=loc["name"],
        scenes=stages,
        total_duration=sum(s.duration for s in stages),
    )


async def run_modeN_scenario_writer(
    preferred_style: str | None = None,
    preferred_location: str | None = None,
    num_stages: int = 5,
    language: str = "ru",
    control: dict | None = None,
) -> dict[str, Any]:
    """Точка входа для пайплайна."""
    from pipeline_control import checkpoint
    
    await checkpoint(control)
    
    scenario = generate_scenario(
        preferred_style=preferred_style,
        preferred_location=preferred_location,
        num_stages=num_stages,
        language=language,
    )
    
    # Конвертация в dict для совместимости с пайплайном
    return {
        "title": scenario.title,
        "title_en": scenario.title_en,
        "style": scenario.style,
        "style_name": scenario.style_name,
        "location": scenario.location,
        "location_name": scenario.location_name,
        "scenes": [s.model_dump() for s in scenario.scenes],
        "total_duration": scenario.total_duration,
    }
```

---

## Шаг 3: Video Generator с последовательной генерацией

### `modes/modeN/video_generator.py`

```python
"""
Mode N Video Generator — Последовательная генерация с keyframe-переходами.

WORKFLOW:
1. ПОСЛЕДОВАТЕЛЬНАЯ генерация изображений с цепочкой референсов:
   - Этап 0: генерация БЕЗ референса
   - Этап 1: генерация с изображением этапа 0 как референс
   - И так далее...

2. KEYFRAME генерация видео (переходы между этапами):
   - Видео 0: переход от этапа_0 к этапу_1
   - Видео 1: переход от этапа_1 к этапу_2
   - ...

ОСОБЕННОСТИ:
- Retry-логика для изображений (2 попытки)
- Проверка существования файлов перед генерацией видео
- Параллельная генерация видео после подготовки всех кадров
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from agents.content_generator.fastgen_scraper import (
    generate_single_video_multi_ref,
    generate_video_from_keyframes,
)
from config import settings


# ═══════════════════════════════════════════════════════════════════════════
# ПОСТРОИТЕЛИ ПРОМПТОВ
# ═══════════════════════════════════════════════════════════════════════════

def _build_image_prompt(
    scene: dict[str, Any],
    index: int,
    scenario: dict[str, Any],
    language: str = "ru",
) -> str:
    """
    Построить промпт для генерации референсного изображения.
    
    CRITICAL: Фон должен оставаться НЕИЗМЕННЫМ между этапами!
    """
    style = scenario.get("style", "default")
    location = scenario.get("location", "default")
    stage_name = scene.get("name", "stage")
    visual_prompt = scene.get("visual_prompt", "")
    
    prompt = f"""Create a photorealistic still image.

━━━ CRITICAL: BACKGROUND STAYS THE SAME! ━━━
The BACKGROUND MUST REMAIN EXACTLY THE SAME across all stages!
- Same sky, same environment
- ONLY THE SUBJECT CHANGES — background is FROZEN!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━ CONTENT SAFETY (MANDATORY) ━━━
Generate ONLY original, generic content.
- NO brand names, logos, copyrighted characters
- All items must be GENERIC
- NO visible text or logos
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STYLE: Photorealistic, natural lighting, authentic look.
NOT 3D render, NOT CGI, NOT cartoon. Must look REAL.

STAGE: {stage_name}

SCENE DESCRIPTION:
{visual_prompt}

COMPOSITION:
- Vertical 9:16 aspect ratio
- Camera positioned at consistent angle
- Natural daylight
- Realistic shadows and lighting

CRITICAL:
- This MUST look like a REAL PHOTO
- If previous image is provided as reference, match the EXACT camera angle"""

    return prompt


def _build_keyframe_video_prompt(
    scene: dict[str, Any],
    scenario: dict[str, Any],
    language: str = "ru",
) -> str:
    """
    Построить КОРОТКИЙ промпт для FastGen keyframe видео.
    
    VIDEO PROMPT FORMULA:
    [Shot Type] + [Subject Action] + [Camera Motion] + [Environment] + [Temporal] + [Technical]
    
    Оптимизирован для FastGen (~700 символов).
    """
    style = scenario.get("style", "default")
    location = scenario.get("location", "default")
    
    start_state = scene.get("start_state", "previous")
    end_state = scene.get("end_state", "next")
    action = scene.get("action", "transformation")
    stage_name = scene.get("name_en", "stage")
    
    # Дополнительные параметры
    intensity = scene.get("build_intensity", "medium")
    time_of_day = scene.get("time_of_day", "midday")
    is_peak = scene.get("is_peak_moment", False)
    
    # Короткие версии workers/machinery
    workers = scene.get("workers_en", "workers active")
    machinery = scene.get("machinery_en", "equipment operating")
    workers_short = (workers[:80] + "...") if len(workers) > 80 else workers
    machinery_short = (machinery[:80] + "...") if len(machinery) > 80 else machinery
    
    peak_section = ""
    if is_peak:
        peak_section = "PEAK VISUAL MOMENT — MAXIMUM IMPACT! "
    
    prompt = f"""Wide shot (WS), timelapse: {stage_name}. {peak_section}

SUBJECT: {action}. Workers: {workers_short}. Equipment: {machinery_short}.

CAMERA: Locked-off tripod, static frame. CRITICAL: camera must not move.
TEMPORAL: Time-lapse, forward motion ONLY, step-by-step progress.

TRANSITION: "{start_state}" → "{end_state}".
MUST strictly follow start frame to end frame. No sudden jumps.

BACKGROUND: Environment stays SAME. Only subject evolves.

SAFETY: Generic content ONLY. NO brands, logos, copyrighted material.

TECHNICAL: Vertical 9:16, 1080x1920, cinematic, photorealistic 4K."""

    return prompt


# ═══════════════════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЙ С RETRY
# ═══════════════════════════════════════════════════════════════════════════

async def _generate_single_image_with_ref(
    prompt: str,
    output_dir: Path,
    index: int,
    reference_image_paths: list[Path],
) -> Path | None:
    """
    Генерация одного изображения с референсом.
    Используется для последовательной цепочки.
    """
    try:
        from agents.content_generator.fastgen_scraper import (
            generate_images_with_references_fastgen,
        )

        prompts_with_refs = [(prompt, reference_image_paths)]

        image_paths = await generate_images_with_references_fastgen(
            prompts_with_refs,
            output_dir,
            parallel=False,  # Последовательная генерация
        )

        if image_paths and len(image_paths) > 0:
            img_path = image_paths[0]
            if img_path and Path(img_path).exists():
                new_path = output_dir / f"stage_{index:03d}_ref.png"
                Path(img_path).rename(new_path)
                return new_path

        return None

    except Exception as e:
        logger.error(f"[ModeN] Image generation failed for stage {index}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ ВИДЕО
# ═══════════════════════════════════════════════════════════════════════════

async def _generate_keyframe_video(
    index: int,
    prompt: str,
    start_frame: Path,
    end_frame: Path,
    output_dir: Path,
) -> Path | None:
    """
    Генерация видео перехода от start_frame к end_frame.
    PREFERRED метод для плавных переходов.
    """
    try:
        result = await generate_video_from_keyframes(
            prompt=prompt,
            output_dir=output_dir,
            start_frame_path=start_frame,
            end_frame_path=end_frame,
            index=index,
        )

        if result and Path(result).exists():
            logger.success(f"[ModeN] Keyframe video {index + 1} saved: {Path(result).name}")
            return result
        else:
            logger.error(f"[ModeN] Keyframe video {index + 1}: No result")
            return None

    except Exception as e:
        logger.error(f"[ModeN] Keyframe video {index + 1} failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ ГЕНЕРАЦИИ
# ═══════════════════════════════════════════════════════════════════════════

async def generate_videos(
    scenario: dict[str, Any],
    output_dir: Path,
    session_id: str,
    language: str = "ru",
) -> tuple[list[Path | None], dict[str, Any]]:
    """
    Генерация видео с последовательной подготовкой изображений.
    
    WORKFLOW:
    1. ПОСЛЕДОВАТЕЛЬНАЯ генерация изображений с цепочкой референсов
    2. ПАРАЛЛЕЛЬНАЯ генерация keyframe видео
    
    Returns:
        Tuple of (list of video paths, enriched scenario)
    """
    scenes = scenario.get("scenes", [])
    
    if not scenes:
        raise ValueError("[ModeN] No scenes to generate")
    
    fastgen_key = getattr(settings, "fastgen_api_key", "") or ""
    if not fastgen_key:
        raise RuntimeError("FASTGEN_API_KEY not set")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "reference_images"
    images_dir.mkdir(parents=True, exist_ok=True)
    
    # ═══════════════════════════════════════════════════════════════════════
    # ЭТАП 1: ПОСЛЕДОВАТЕЛЬНАЯ генерация изображений с цепочкой референсов
    # ═══════════════════════════════════════════════════════════════════════
    
    logger.info(f"[ModeN] STEP 1: Generating {len(scenes)} images SEQUENTIALLY...")
    
    ref_image_paths: list[Path | None] = []
    previous_image: Path | None = None
    image_retries = 2  # Количество повторных попыток
    
    for i, scene in enumerate(scenes):
        image_prompt = _build_image_prompt(scene, i, scenario, language)
        
        # Референс = предыдущее изображение (для континуитета)
        refs = [previous_image] if previous_image else []
        
        logger.info(
            f"[ModeN] Generating image {i + 1}/{len(scenes)}: {scene.get('stage_key', 'stage')} "
            f"(with {len(refs)} reference(s))"
        )
        
        # Генерация С RETRY
        image_path = None
        for retry in range(image_retries + 1):
            image_path = await _generate_single_image_with_ref(
                prompt=image_prompt,
                output_dir=images_dir,
                index=i,
                reference_image_paths=refs,
            )
            if image_path and Path(image_path).exists():
                break
            if retry < image_retries:
                logger.warning(f"[ModeN] Image {i + 1} failed, retry {retry + 2}/{image_retries + 1}...")
        
        if image_path:
            ref_image_paths.append(image_path)
            previous_image = image_path  # Цепочка на следующий этап
            logger.success(f"[ModeN] Stage {i + 1} image: {image_path.name}")
        else:
            ref_image_paths.append(None)
            logger.error(f"[ModeN] Stage {i + 1}: Failed after {image_retries + 1} attempts")
            # НЕ прерываем — продолжаем с None, но предупреждаем
            if i < len(scenes) - 1:
                logger.warning(f"[ModeN] Stage {i + 2} will have no reference!")
    
    # ═══════════════════════════════════════════════════════════════════════
    # ЭТАП 2: KEYFRAME генерация видео (переходы между этапами)
    # ═══════════════════════════════════════════════════════════════════════
    
    num_videos = len(scenes) - 1  # Переходы между N этапами = N-1 видео
    
    if num_videos < 1:
        raise ValueError("[ModeN] Need at least 2 stages for keyframe videos")
    
    logger.info(f"[ModeN] STEP 2: Generating {num_videos} KEYFRAME videos...")
    
    video_tasks = []
    for i in range(num_videos):
        start_frame = ref_image_paths[i] if i < len(ref_image_paths) else None
        end_frame = ref_image_paths[i + 1] if i + 1 < len(ref_image_paths) else None
        
        # Проверка существования файлов
        if not start_frame or not end_frame:
            logger.warning(f"[ModeN] Skipping video {i}: missing frames")
            video_tasks.append(asyncio.create_task(asyncio.sleep(0)))
            continue
        
        if not Path(start_frame).exists() or not Path(end_frame).exists():
            logger.warning(f"[ModeN] Skipping video {i}: frame files not found")
            video_tasks.append(asyncio.create_task(asyncio.sleep(0)))
            continue
        
        video_prompt = _build_keyframe_video_prompt(scenes[i], scenario, language)
        
        task = _generate_keyframe_video(
            index=i,
            prompt=video_prompt,
            start_frame=Path(start_frame),
            end_frame=Path(end_frame),
            output_dir=output_dir,
        )
        video_tasks.append(task)
    
    # ПАРАЛЛЕЛЬНАЯ генерация всех видео
    video_paths = await asyncio.gather(*video_tasks, return_exceptions=True)
    
    # Обработка результатов
    valid_paths: list[Path | None] = []
    for i, result in enumerate(video_paths):
        if isinstance(result, Exception):
            logger.error(f"[ModeN] Video {i + 1} failed: {result}")
            valid_paths.append(None)
        elif result is None:
            valid_paths.append(None)
        else:
            valid_paths.append(result)
    
    # Обогащение сценария путями
    enriched_scenes = []
    for i, scene in enumerate(scenes):
        enriched_scene = dict(scene)
        if i < len(ref_image_paths) and ref_image_paths[i]:
            enriched_scene["reference_image_path"] = str(ref_image_paths[i])
        if i > 0 and i - 1 < len(valid_paths) and valid_paths[i - 1]:
            enriched_scene["video_path"] = str(valid_paths[i - 1])
        enriched_scenes.append(enriched_scene)
    
    enriched_scenario = dict(scenario)
    enriched_scenario["scenes"] = enriched_scenes
    
    valid_count = sum(1 for p in valid_paths if p and Path(p).exists())
    ref_count = sum(1 for p in ref_image_paths if p and Path(p).exists())
    logger.success(
        f"[ModeN] Generated {ref_count}/{len(scenes)} images "
        f"and {valid_count}/{num_videos} videos"
    )
    
    return valid_paths, enriched_scenario
```

---

## Шаг 4: Video Assembler с продвинутой обработкой

### `modes/modeN/video_assembler.py`

```python
"""
Mode N Video Assembler — Сборка финального видео.

Features:
- Crossfade transitions между клипами
- Speed ramping для кинематографичности
- Final hold frame для удержания внимания
- Смешивание аудио: оригинал + фоновая музыка
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from loguru import logger
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    VideoClip,
    VideoFileClip,
    afx,
    concatenate_audioclips,
    concatenate_videoclips,
)
from PIL import Image

from config import settings


def _resize_fill(img: Image.Image, w: int, h: int, bottom_crop: float = 0.0) -> Image.Image:
    """Масштабирование с заполнением; опционально обрезка снизу (для водяных знаков)."""
    if bottom_crop > 0 and bottom_crop < 1:
        keep_h = int(img.height * (1.0 - bottom_crop))
        if keep_h > 0:
            img = img.crop((0, 0, img.width, keep_h))
    ratio = max(w / img.width, h / img.height)
    nw, nh = int(img.width * ratio), int(img.height * ratio)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _clip_with_bottom_crop(
    vc: VideoFileClip, target_w: int, target_h: int, fps: int, bottom_crop: float
) -> VideoClip:
    """Обёртка VideoFileClip с обрезкой снизу + ресайз."""
    vid_dur = float(vc.duration)

    def make_frame(t: float) -> np.ndarray:
        t_vid = min(t, vid_dur - 0.001) if vid_dur > 0 else 0
        frame = vc.get_frame(t_vid)
        if frame is None or frame.size == 0:
            return np.zeros((target_h, target_w, 3), dtype=np.uint8)
        img = Image.fromarray(frame)
        img = _resize_fill(img, target_w, target_h, bottom_crop=bottom_crop)
        return np.array(img)

    return VideoClip(make_frame, duration=vid_dur).with_fps(fps)


def _make_crossfade(clip_a, clip_b, duration: float, fps: int):
    """Плавный переход между клипами с smoothstep."""
    dur_a = float(clip_a.duration)
    dur_b = float(clip_b.duration)
    half = duration / 2.0

    def smoothstep(x):
        x = max(0.0, min(1.0, x))
        return x * x * (3.0 - 2.0 * x)

    def make_frame(t):
        raw = t / duration if duration > 0 else 1.0
        alpha = smoothstep(raw)
        half_a = min(half, dur_a)
        half_b = min(half, dur_b)
        ta = max(0.0, dur_a - half_a) + raw * half_a
        tb = raw * half_b
        fa = clip_a.get_frame(ta).astype("float32")
        fb = clip_b.get_frame(tb).astype("float32")
        return ((1.0 - alpha) * fa + alpha * fb).astype("uint8")

    return VideoClip(make_frame, duration=duration).with_fps(fps)


def _assemble_with_crossfades(clips: list, T: float, fps: int):
    """Сборка клипов с crossfade переходами."""
    if len(clips) == 1 or T <= 0:
        return concatenate_videoclips(clips, method="compose")
    half = T / 2.0
    parts = []
    for i, clip in enumerate(clips):
        is_first, is_last = i == 0, i == len(clips) - 1
        t_start = 0.0 if is_first else half
        t_end = clip.duration if is_last else max(clip.duration - half, half + 0.1)
        t_end = min(t_end, clip.duration - 0.01)
        trimmed = clip.subclipped(t_start, t_end)
        parts.append(trimmed)
        if not is_last:
            parts.append(_make_crossfade(trimmed, clips[i + 1], T, fps))
    return concatenate_videoclips(parts, method="compose")


def assemble_modeN_video(
    video_paths: list[Path | str],
    output_path: Path,
    title: str | None = None,
    crossfade_duration: float = 0.2,
    speed_multiplier: float = 1.5,
    use_speed_ramping: bool = True,
    final_hold_duration: float = 1.5,
) -> Path:
    """
    Сборка финального видео.
    
    Args:
        video_paths: Список путей к видео
        output_path: Путь для сохранения
        title: Заголовок (для логов)
        crossfade_duration: Длительность перехода (0.2s для viral стиля)
        speed_multiplier: Множитель скорости (1.5x для динамики)
        use_speed_ramping: Кинематографичное изменение скорости
        final_hold_duration: Удержание последнего кадра
    """
    target_w, target_h = settings.video_resolution
    fps = settings.video_fps
    T = max(0.0, min(crossfade_duration, 0.5))
    bottom_crop = max(0, min(0.2, getattr(settings, "video_bottom_crop", 0.05)))

    # Сохраняем оригинальные VideoFileClips для доступа к аудио
    original_vcs: list[VideoFileClip] = []
    clips: list = []
    original_audios: list = []

    for p in video_paths:
        path = Path(p)
        if not path.exists():
            logger.warning(f"[ModeN Assembler] Skip missing: {path}")
            continue
        vc = VideoFileClip(str(path))
        original_vcs.append(vc)

        # Сохраняем оригинальное аудио
        if vc.audio is not None:
            dur = max(0.0, vc.duration - 0.05)
            original_audios.append(vc.audio.subclipped(0, min(vc.audio.duration, dur)))
        else:
            original_audios.append(None)

        # Визуальный клип (с обрезкой/ресайзом)
        clip = _clip_with_bottom_crop(vc, target_w, target_h, fps, bottom_crop)
        clips.append(clip)

    if not clips:
        raise ValueError("[ModeN Assembler] No valid clips")

    logger.info(f"[ModeN Assembler] Assembling {len(clips)} clips (T={T}s)")

    # Сборка видео (только визуал)
    final = _assemble_with_crossfades(clips, T, fps)

    # Применение множителя скорости
    if speed_multiplier != 1.0:
        from moviepy import vfx
        final = final.with_effects([vfx.MultiplySpeed(speed_multiplier)])

    # ===== SPEED RAMPING =====
    if use_speed_ramping:
        try:
            from moviepy import vfx
            total_dur = final.duration
            phase1_end = total_dur * 0.1  # Медленный старт
            phase2_end = total_dur * 0.8  # Быстрая середина

            def speed_ramp(t):
                if t < phase1_end:
                    return 1.0  # Медленно
                elif t < phase2_end:
                    return 1.8  # Быстро
                else:
                    return 0.8  # Медленный финал

            final = final.with_effects([vfx.TimeMirror(speed_ramp)])
        except Exception as e:
            logger.warning(f"[ModeN Assembler] Speed ramping failed: {e}")

    # ===== FINAL HOLD =====
    if final_hold_duration > 0:
        try:
            from moviepy import ImageClip
            last_frame_time = max(0, final.duration - 0.05)
            last_frame = final.get_frame(last_frame_time)
            freeze_frame = ImageClip(last_frame).set_duration(final_hold_duration).with_fps(fps)
            freeze_frame = freeze_frame.resized((target_w, target_h))
            final = concatenate_videoclips([final, freeze_frame], method="compose")
        except Exception as e:
            logger.warning(f"[ModeN Assembler] Final hold failed: {e}")

    # Сборка аудио
    valid_audios = [a for a in original_audios if a is not None]
    combined_video_audio = None
    if valid_audios:
        try:
            combined_video_audio = concatenate_audioclips(valid_audios)
            if speed_multiplier != 1.0:
                from moviepy import afx as audio_fx
                combined_video_audio = combined_video_audio.with_effects([
                    audio_fx.MultiplySpeed(speed_multiplier)
                ])
            max_dur = min(final.duration, combined_video_audio.duration) - 0.05
            combined_video_audio = combined_video_audio.subclipped(0, max(0.1, max_dur))
        except Exception as e:
            logger.warning(f"[ModeN Assembler] Audio combine failed: {e}")

    # Фоновая музыка на 10%
    bg_audio = None
    try:
        from agents.video_editor.moviepy_editor import _pick_background_music
        music_path = _pick_background_music(topic="ambient", duration=final.duration)
        if music_path:
            bg = AudioFileClip(str(music_path))
            if bg.duration < final.duration:
                loops = int(final.duration / bg.duration) + 1
                bg = concatenate_audioclips([bg] * loops)
            fade_dur = min(2.0, final.duration * 0.1)
            bg = bg.subclipped(0, min(final.duration, bg.duration) - 0.05)
            bg = bg.with_effects([
                afx.MultiplyVolume(0.1),
                afx.AudioFadeIn(fade_dur),
                afx.AudioFadeOut(fade_dur),
            ])
            bg_audio = bg
    except Exception as e:
        logger.warning(f"[ModeN Assembler] Background music failed: {e}")

    # Микширование
    if combined_video_audio and bg_audio:
        final_audio = CompositeAudioClip([combined_video_audio, bg_audio])
        final = final.with_audio(final_audio)
    elif combined_video_audio:
        final = final.with_audio(combined_video_audio)
    elif bg_audio:
        final = final.with_audio(bg_audio)

    # Рендеринг
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(
        str(output_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="fast",
        logger=None,
    )

    # Cleanup
    final.close()
    for c in clips:
        try:
            c.close()
        except Exception:
            pass
    for vc in original_vcs:
        try:
            vc.close()
        except Exception:
            pass

    logger.success(f"[ModeN Assembler] Done -> {output_path}")
    return output_path
```

---

## Шаг 5: Publishing Metadata (опционально)

### `modes/modeN/publishing_metadata.py`

```python
"""
Mode N Publishing Metadata Generator.

Генерирует Title, Description, Hashtags, Tags для YouTube Shorts.
"""

from __future__ import annotations

import json
import random
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from utils.llm import make_llm


PUBLISHING_PROMPT = """Generate YouTube Shorts publishing content.

CONTEXT:
- Style: {style}
- Location: {location}
- Stages: {stages_description}
- Title: {title}

OUTPUT STRUCTURE:

1. TITLE
- Short, attention-grabbing
- First 2 words must be strong keywords
- Max 1 emoji at the end
- Max 2-3 hashtags at the end

2. DESCRIPTION
- First line: 1 short sentence
- Then naturally include 4-5 keywords
- Must read naturally

3. HASHTAGS (separate block)
- 4-5 relevant hashtags
- Focus on niche

4. TAGS (for YouTube Studio)
- 10-15 tags
- Mix: specific, general, viral

OUTPUT FORMAT (JSON):
{{
  "title": "...",
  "description": "...",
  "hashtags": ["#tag1", ...],
  "tags": ["tag1", ...]
}}

Language: {language}
"""


FALLBACK_TEMPLATES = {
    "en": {
        "titles": ["Title 1", "Title 2"],
        "descriptions": ["Desc 1", "Desc 2"],
        "hashtags": ["#tag1", "#tag2"],
        "tags": ["tag1", "tag2"],
    },
}


async def generate_publishing_metadata(
    style: str,
    location: str,
    stages: list[dict],
    title: str,
    language: str = "en",
) -> dict[str, Any]:
    """Генерация метаданных для публикации."""
    stages_desc = " → ".join([s.get("name_en", f"Stage {i+1}") for i, s in enumerate(stages[:6])])
    
    prompt = PUBLISHING_PROMPT.format(
        style=style.replace("_", " ").title(),
        location=location.replace("_", " ").title(),
        stages_description=stages_desc or "Stages",
        title=title or "Video",
        language=language,
    )
    
    try:
        llm = make_llm(temperature=0.8)
        messages = [
            SystemMessage(content="You are a YouTube Shorts SEO expert."),
            HumanMessage(content=prompt),
        ]
        response = await llm.ainvoke(messages)
        raw = response.content.strip() if hasattr(response, 'content') else str(response)
        
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
        
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            result = json.loads(json_match.group())
            logger.success(f"[ModeN Publishing] Generated: {result.get('title', 'N/A')}")
            return result
    except Exception as e:
        logger.warning(f"[ModeN Publishing] LLM failed: {e}")
    
    # Fallback
    templates = FALLBACK_TEMPLATES.get(language, FALLBACK_TEMPLATES["en"])
    return {
        "title": random.choice(templates["titles"]),
        "description": random.choice(templates["descriptions"]),
        "hashtags": templates["hashtags"],
        "tags": templates["tags"],
    }
```

---

## Шаг 6: Главный Pipeline

### `modes/modeN/pipeline.py`

```python
"""
Mode N Pipeline — Главный пайплайн режима.

Flow:
  1. Scenario Writer — Генерация структурированного сценария
  2. Video Generator — Последовательные изображения + keyframe видео
  3. Video Assembler — Сборка финального видео
  4. Publishing Metadata — Метаданные для публикации
"""

from __future__ import annotations

import functools
import time
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings
from modes.modeN.scenario_writer import run_modeN_scenario_writer
from modes.modeN.video_generator import generate_videos
from modes.modeN.video_assembler import assemble_modeN_video
from modes.modeN.publishing_metadata import generate_publishing_metadata


async def run_modeN_pipeline(
    session_id: str | None = None,
    local_only: bool = True,
    style: str | None = None,
    location: str | None = None,
    num_stages: int = 5,
    language: str = "ru",
    control: dict | None = None,
) -> dict[str, Any]:
    """
    Запуск пайплайна Mode N.
    
    Args:
        session_id: Уникальный ID сессии
        local_only: Если True, пропустить публикацию
        style: Стиль (или None для случайного)
        location: Локация (или None для случайной)
        num_stages: Количество этапов (5-8)
        language: Язык ("ru" или "en")
        control: Контроль паузы/отмены
    
    Returns:
        dict с video_path, session_id, publishing metadata и т.д.
    """
    import asyncio
    from pipeline_control import checkpoint

    session_id = session_id or str(int(time.time() * 1000))
    videos_dir = settings.videos_dir
    clips_dir = videos_dir / session_id / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        f"=== Mode N Pipeline | session={session_id} | "
        f"style={style or 'random'} | location={location or 'random'} ==="
    )

    # Step 1: Генерация сценария
    await checkpoint(control)
    logger.info("Step 1/4 - Generating Scenario...")
    
    scenario = await run_modeN_scenario_writer(
        preferred_style=style,
        preferred_location=location,
        num_stages=num_stages,
        language=language,
        control=control,
    )
    
    title = scenario.get("title", "Video")
    style_name = scenario.get("style_name", "default")
    location_name = scenario.get("location_name", "default")
    stages = scenario.get("scenes", [])
    
    logger.success(f"[ModeN] Scenario: {title} | {len(stages)} stages")

    # Step 2: Генерация видео
    await checkpoint(control)
    logger.info("Step 2/4 - Video Generator (Sequential + Keyframes)")
    
    video_paths, enriched_scenario = await generate_videos(
        scenario=scenario,
        output_dir=clips_dir,
        session_id=session_id,
        language=language,
    )
    
    valid_paths = [p for p in video_paths if p and Path(p).exists()]
    if not valid_paths:
        raise RuntimeError("[ModeN] No video clips generated")
    
    expected_videos = len(stages) - 1 if len(stages) > 1 else 1
    logger.success(f"[ModeN] Generated {len(valid_paths)}/{expected_videos} clips")

    # Step 3: Сборка финального видео
    await checkpoint(control)
    logger.info("Step 3/4 - Video Assembly")
    
    output_path = videos_dir / f"video_{session_id}.mp4"
    
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(
            assemble_modeN_video,
            valid_paths,
            output_path,
            title=title,
        ),
    )

    # Запись в историю
    from agents.topics_history import mark_topic_used
    mark_topic_used(
        topic=f"[ModeN] {title}",
        session_id=session_id,
        video_path=str(output_path),
        video_angle=f"style={style_name},location={location_name}",
    )

    video_path = str(output_path.resolve())

    # Step 4: Генерация метаданных
    logger.info("Step 4/4 - Generating Publishing Metadata...")
    publishing = await generate_publishing_metadata(
        style=style_name,
        location=location_name,
        stages=stages,
        title=title,
        language=language,
    )

    logger.success(f"=== Mode N Pipeline DONE | video={video_path} ===")

    return {
        "session_id": session_id,
        "video_path": video_path,
        "topic": title,
        "scenario": enriched_scenario,
        "style": style_name,
        "location": location_name,
        "stages": len(stages),
        "publishing": publishing,
    }
```

---

## Шаг 7: Интеграция в систему

### `orchestrator/dispatcher.py`

```python
from modes.modeN import run_modeN_pipeline

MODE_REGISTRY = {
    "mode1": run_mode1_pipeline,
    # ... другие режимы
    "modeN": run_modeN_pipeline,  # ← Добавить
}
```

### `server.py`

```python
from modes.modeN import run_modeN_pipeline

@app.post("/api/generate")
async def api_generate(request: Request):
    data = await request.json()
    mode = data.get("mode", "mode1")
    
    if mode == "modeN":
        result = await run_modeN_pipeline(
            style=data.get("style"),
            location=data.get("location"),
            num_stages=data.get("num_stages", 5),
            language=data.get("language", "ru"),
        )
    # ... другие режимы
```

---

## Ключевые паттерны из Mode 8

### 1. Последовательная генерация изображений

```python
# Цепочка референсов: каждое следующее изображение 
# использует предыдущее как референс
ref_image_paths: list[Path | None] = []
previous_image: Path | None = None

for i, scene in enumerate(scenes):
    refs = [previous_image] if previous_image else []
    image_path = await _generate_single_image_with_ref(..., refs)
    if image_path:
        ref_image_paths.append(image_path)
        previous_image = image_path  # Цепочка!
```

### 2. Retry-логика

```python
image_retries = 2

for retry in range(image_retries + 1):
    image_path = await _generate_single_image_with_ref(...)
    if image_path and Path(image_path).exists():
        break
    if retry < image_retries:
        logger.warning(f"Retry {retry + 2}/{image_retries + 1}...")
```

### 3. Keyframe видео

```python
# N изображений → N-1 видео (переходы между этапами)
num_videos = len(scenes) - 1

for i in range(num_videos):
    start_frame = ref_image_paths[i]
    end_frame = ref_image_paths[i + 1]
    
    video = await generate_video_from_keyframes(
        prompt=prompt,
        start_frame_path=start_frame,
        end_frame_path=end_frame,
    )
```

### 4. Детальные параметры сцены

```python
class SceneStage(BaseModel):
    build_intensity: str = "medium"   # low | medium | high
    time_of_day: str = "midday"       # morning | midday | afternoon | golden_hour
    is_peak_moment: bool = False      # Пиковый момент
    workers: str | None = None        # Описание работников
    machinery: str | None = None      # Описание техники
    micro_actions: list[str] = []     # Микро-действия
```

### 5. Короткий промпт для FastGen

```python
def _build_keyframe_video_prompt(...) -> str:
    """~700 символов для оптимальной работы FastGen."""
    prompt = f"""Wide shot (WS), timelapse: {stage_name}.
    
SUBJECT: {action}. Workers: {workers_short}. Equipment: {machinery_short}.

CAMERA: Locked-off tripod, static frame.
TEMPORAL: Time-lapse, forward motion ONLY.

TRANSITION: "{start_state}" → "{end_state}".

TECHNICAL: Vertical 9:16, cinematic, photorealistic 4K."""
    return prompt
```

---

## Чек-лист создания режима

- [ ] `modes/modeN/__init__.py` создан
- [ ] `modes/modeN/scenario_writer.py` с Pydantic моделями
- [ ] `modes/modeN/video_generator.py` с последовательной генерацией
- [ ] `modes/modeN/video_assembler.py` с crossfade и speed ramping
- [ ] `modes/modeN/publishing_metadata.py` (опционально)
- [ ] `modes/modeN/pipeline.py` главный пайплайн
- [ ] `orchestrator/dispatcher.py` обновлён
- [ ] `server.py` обновлён с роутом
- [ ] `.env` содержит `FASTGEN_API_KEY`

---

## Архитектура Mode 8

```
┌─────────────────────────────────────────────────────────────────┐
│                    pipeline.py                                  │
│  1. Scenario Writer → 2. Video Generator → 3. Assembler         │
└────────────────────┬────────────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
┌─────────────────┐   ┌─────────────────────────────┐
│ scenario_writer │   │     video_generator.py      │
│  Pydantic models│   │                             │
│  Stage configs  │   │  STEP 1: Images (sequential)│
│  Visual prompts │   │  ┌─────┐    ┌─────┐        │
└─────────────────┘   │  │Img 0│───→│Img 1│───→...  │
                      │  └─────┘    └─────┘        │
                      │     ↑            ↑          │
                      │   no ref      ref=Img 0     │
                      │                             │
                      │  STEP 2: Videos (parallel)  │
                      │  ┌─────┐    ┌─────┐        │
                      │  │Vid 0│    │Vid 1│  ...    │
                      │  └──┬──┘    └──┬──┘        │
                      │  start=Img0    start=Img1   │
                      │  end=Img1      end=Img2     │
                      └──────────────┬──────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │    video_assembler.py       │
                      │  - Crossfade transitions    │
                      │  - Speed ramping            │
                      │  - Final hold frame         │
                      │  - Audio mixing             │
                      └──────────────┬──────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │   publishing_metadata.py    │
                      │  - Title, Description       │
                      │  - Hashtags, Tags           │
                      └─────────────────────────────┘
```
