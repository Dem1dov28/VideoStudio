"""
Clickbait Preview Generator for Social Media.

Generates eye-catching preview images from the final frame of timelapse videos.
Optimized for maximum CTR (Click-Through Rate) on social platforms.

Features:
- Uses AI image generation to enhance the last frame
- Adds dramatic visual effects and text overlays
- Creates curiosity and emotional response
- Platform-optimized formats (TikTok, Instagram Reels, YouTube Shorts)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from agents.content_generator.fastgen_scraper import generate_images_with_references_fastgen
from config import settings


# ═══════════════════════════════════════════════════════════════════════════
# CLICKBAIT STYLE TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════

CLICKBAIT_STYLES = {
    "dramatic_reveal": {
        "name_en": "Dramatic Reveal",
        "name_ru": "Драматичное раскрытие",
        "prompt_en": """Create an EXTREMELY DRAMATIC and EYE-CATCHING social media preview image.

CRITICAL REQUIREMENTS FOR MAXIMUM CTR:
- HIGH CONTRAST: Dramatic lighting with deep shadows and bright highlights
- SATURATED COLORS: Rich, vibrant colors that pop
- CINEMATIC MOOD: Epic, Hollywood-style color grading
- EMOTIONAL IMPACT: Make viewers say "WOW!" instantly

VISUAL ELEMENTS:
- Golden hour or dramatic sunset lighting
- Volumetric light rays (god rays) breaking through clouds
- Enhanced atmospheric perspective
- Slight lens flare for cinematic feel
- Sharp focus on the main subject
- Background slightly blurred for depth

COMPOSITION RULES:
- Rule of thirds for maximum visual appeal
- Strong leading lines drawing attention to subject
- Clear focal point in center-third area
- Negative space at top for potential text overlay

COLOR GRADING:
- Teal and orange cinematic look OR
- Warm golden tones for aspirational feel OR
- High contrast B&W for dramatic impact

TECHNICAL:
- Ultra sharp, crystal clear details
- Professional photography quality
- Shot on premium camera (Hasselblad/Phase One quality)
- Perfect exposure, no blown highlights
- Rich blacks, clean whites""",
        
        "prompt_ru": """Создайте ЧРЕЗВЫЧАЙНО драматичное и ПРИВЛЕКАТЕЛЬНОЕ превью для соцсетей.

КРИТИЧЕСКИЕ ТРЕБОВАНИЯ ДЛЯ МАКСИМАЛЬНОГО CTR:
- ВЫСОКИЙ КОНТРАСТ: Драматичное освещение с глубокими тенями и яркими бликами
- НАСЫЩЕННЫЕ ЦВЕТА: Богатые, яркие цвета, которые 'выпрыгивают'
- КИНЕМАТОГРАФИЧНОЕ НАСТРОЕНИЕ: Эпичная, голливудская цветокоррекция
- ЭМОЦИОНАЛЬНЫЙ УДАР: Чтобы зрители мгновенно сказали 'ВАУ!'

ВИЗУАЛЬНЫЕ ЭЛЕМЕНТЫ:
- Золотой час или драматичное закатное освещение
- Объемные лучи света (божественные лучи), пробивающиеся сквозь облака
- Усиленная атмосферная перспектива
- Легкий блик объектива для кинематографичности
- Резкий фокус на главном объекте
- Фон слегка размыт для глубины

ПРАВИЛА КОМПОЗИЦИИ:
- Правило третей для максимальной визуальной привлекательности
- Сильные направляющие линии, привлекающие внимание к объекту
- Четкая точка фокуса в центральной трети
- Негативное пространство сверху для возможного текстового оверлея

ЦВЕТОВОЙ ГРЕЙДИНГ:
- Бирюзово-оранжевый кинематографичный стиль ИЛИ
- Теплые золотистые тона для вдохновляющего чувства ИЛИ
- Высококонтрастный ч/б для драматичного воздействия

ТЕХНИЧЕСКИ:
- Ультра четкие, кристально ясные детали
- Качество профессиональной фотографии
- Съемка на премиальную камеру (Hasselblad/Phase One)
- Идеальная экспозиция, без пересветов
- Богатые черные, чистые белые""",
    },
    
    "before_after_split": {
        "name_en": "Before/After Split",
        "name_ru": "Разделение До/После",
        "prompt_en": """Create a COMPELLING split-screen preview showing transformation.

COMPOSITION:
- VERTICAL SPLIT: Left side shows starting point, right side shows amazing result
- CLEAR CONTRAST: Obvious visual difference between two sides
- SEAMLESS DIVISION: Clean dividing line down the middle
- MATCHED PERSPECTIVE: Same camera angle on both sides for fair comparison

LEFT SIDE (BEFORE):
- Empty land or basic starting state
- Muted, desaturated colors
- Flat lighting, less interesting
- Represents 'struggle' or 'potential'

RIGHT SIDE (AFTER):
- Stunning completed result
- Vibrant, saturated colors
- Dramatic golden hour lighting
- Represents 'success' and 'achievement'

VISUAL ENHANCEMENTS:
- Add subtle glow effect on the 'after' side
- Color grade 'after' warmer and more appealing
- Slightly higher contrast on 'after' side
- Consider adding motion blur or transition effect at division line

TEXT SPACE:
- Leave room at top for "BEFORE / AFTER" or "ДО / ПОСЛЕ" text
- Or "YOU WON'T BELIEVE" style hook

GOAL: Make the transformation so dramatic viewers MUST click to see the full story.""",
        
        "prompt_ru": """Создайте ЗАХВАТЫВАЮЩИЙ сплит-скрин превью, показывающий трансформацию.

КОМПОЗИЦИЯ:
- ВЕРТИКАЛЬНОЕ РАЗДЕЛЕНИЕ: Левая сторона показывает начальное состояние, правая - потрясающий результат
- ЯВНЫЙ КОНТРАСТ: Очевидная визуальная разница между двумя сторонами
- ПЛАВНОЕ РАЗДЕЛЕНИЕ: Чистая разделительная линия посередине
- СОГЛАСОВАННАЯ ПЕРСПЕКТИВА: Одинаковый угол камеры на обеих сторонах для честного сравнения

ЛЕВАЯ СТОРОНА (ДО):
- Пустая земля или базовое начальное состояние
- Приглушенные, ненасыщенные цвета
- Плоское освещение, менее интересное
- Представляет 'борьбу' или 'потенциал'

ПРАВАЯ СТОРОНА (ПОСЛЕ):
- Потрясающий завершенный результат
- Яркие, насыщенные цвета
- Драматичное освещение золотого часа
- Представляет 'успех' и 'достижение'

ВИЗУАЛЬНЫЕ УЛУЧШЕНИЯ:
- Добавить тонкий эффект свечения на стороне 'после'
- Цветокоррекция 'после' теплее и привлекательнее
- Немного более высокий контраст на стороне 'после'
- Рассмотреть добавление размытия движения или эффекта перехода на линии раздела

ПРОСТРАНСТВО ДЛЯ ТЕКСТА:
- Оставить место сверху для текста "BEFORE / AFTER" или "ДО / ПОСЛЕ"
- Или хук в стиле "ВЫ НЕ ПОВЕРИТЕ"

ЦЕЛЬ: Сделать трансформацию настолько драматичной, чтобы зрители ДОЛЖНЫ были кликнуть, чтобы увидеть полную историю.""",
    },
    
    "extreme_closeup": {
        "name_en": "Extreme Close-up Detail",
        "name_ru": "Экстремальный крупный план деталей",
        "prompt_en": """Create an INTENSE close-up preview focusing on stunning details.

COMPOSITION:
- MACRO SHOT: Extremely close to the subject
- FILL THE FRAME: Subject dominates 80%+ of the frame
- SHALLOW DEPTH OF FIELD: Background beautifully blurred (bokeh)
- CRITICAL FOCUS: Razor-sharp focus on most important detail

WHAT TO SHOW:
- Intricate architectural details (for house)
- Sleek surface textures and reflections (for vehicle)
- Premium materials and craftsmanship
- Unique design elements that stand out

LIGHTING:
- Side lighting to reveal texture and depth
- Rim lighting to separate subject from background
- Specular highlights on reflective surfaces
- Dramatic shadows for contrast

COLOR AND MOOD:
- Rich, luxurious color palette
- Warm tones for comfort/aspiration OR cool tones for sophistication
- High saturation for visual punch
- Cinematic color grading

EMOTIONAL TRIGGER:
- Make viewers FEEL the quality and craftsmanship
- Create desire and aspiration
- Trigger 'I want this' response

GOAL: Make the detail so irresistible viewers must see the full creation process.""",
        
        "prompt_ru": """Создайте ИНТЕНСИВНЫЙ превью с фокусом на потрясающих деталях.

КОМПОЗИЦИЯ:
- МАКРО СЪЕМКА: Экстремально близко к объекту
- ЗАПОЛНЕНИЕ КАДРА: Объект занимает 80%+ кадра
- МАЛАЯ ГЛУБИНА РЕЗКОСТИ: Фон красиво размыт (боке)
- КРИТИЧЕСКИЙ ФОКУС: бритвенно-резкий фокус на самой важной детали

ЧТО ПОКАЗАТЬ:
- Замысловатые архитектурные детали (для дома)
- Гладкие текстуры поверхности и отражения (для техники)
- Премиальные материалы и качество исполнения
- Уникальные элементы дизайна, которые выделяются

ОСВЕЩЕНИЕ:
- Боковое освещение для выявления текстуры и глубины
- Контурное освещение для отделения объекта от фона
- Блики на отражающих поверхностях
- Драматичные тени для контраста

ЦВЕТ И НАСТРОЕНИЕ:
- Богатая, роскошная цветовая палитра
- Теплые тона для уюта/стремления ИЛИ холодные тона для изысканности
- Высокая насыщенность для визуального воздействия
- Кинематографичная цветокоррекция

ЭМОЦИОНАЛЬНЫЙ ТРИГГЕР:
- Заставить зрителей ПОЧУВСТВОВАТЬ качество и мастерство
- Создать желание и стремление
- Вызвать реакцию 'хочу это'

ЦЕЛЬ: Сделать деталь настолько непреодолимой, чтобы зрители должны были увидеть полный процесс создания.""",
    },
    
    "epic_wide_angle": {
        "name_en": "Epic Wide Angle Showcase",
        "name_ru": "Эпический широкоугольный показ",
        "prompt_en": """Create a BREATHTAKING wide-angle epic showcase shot.

COMPOSITION:
- ULTRA WIDE: Capture everything in one magnificent frame
- LOW ANGLE: Camera positioned low, looking slightly up for grandeur
- EXPANSIVE VIEW: Show subject + environment + sky
- HERO POSITIONING: Subject centered or rule-of-thirds, dominant in frame

ENVIRONMENT:
- Dramatic sky (sunset, sunrise, or moody clouds)
- Beautiful landscaping/natural setting
- Contextual elements that add scale (trees, people, vehicles)
- Sense of place and atmosphere

SCALE AND PROPORTION:
- Make subject look IMPRESSIVE and GRAND
- Use foreground elements for depth
- Layering: foreground, midground (subject), background
- Leading lines drawing eye to subject

LIGHTING:
- Golden hour magic light
- Long dramatic shadows
- Sky on fire with color
- Subject perfectly lit, no harsh shadows

MOOD AND ATMOSPHERE:
- Awe-inspiring and majestic
- Makes viewer feel small (in a good way)
- Aspirational lifestyle imagery
- 'This could be yours' feeling

COLOR:
- Rich, cinematic color grade
- Warm oranges and teals
- Deep blue sky gradient
- Vibrant but natural

GOAL: Create an image so epic and aspirational viewers can't scroll past.""",
        
        "prompt_ru": """Создайте ЗАХВАТЫВАЮЩИЙ дух широкоугольный эпический показ.

КОМПОЗИЦИЯ:
- УЛЬТРА ШИРОКИЙ: Захватить все в одном великолепном кадре
- НИЗКИЙ УГОЛ: Камера расположена низко, смотрит немного вверх для величия
- ОБШИРНЫЙ ВИД: Показать объект + окружение + небо
- ГЕРОИЧЕСКАЯ ПОЗИЦИЯ: Объект по центру или по правилу третей, доминирует в кадре

ОКРУЖЕНИЕ:
- Драматичное небо (закат, рассвет или мрачные облака)
- Красивый ландшафт/природная обстановка
- Контекстные элементы, добавляющие масштаб (деревья, люди, техника)
- Чувство места и атмосферы

МАСШТАБ И ПРОПОРЦИИ:
- Сделать объект ВПЕЧАТЛЯЮЩИМ и ВЕЛИЧЕСТВЕННЫМ
- Использовать элементы переднего плана для глубины
- Слои: передний план, средний план (объект), фон
- Направляющие линии, привлекающие взгляд к объекту

ОСВЕЩЕНИЕ:
- Магический свет золотого часа
- Длинные драматичные тени
- Небо в огне с цветом
- Объект идеально освещен, без резких теней

НАСТРОЕНИЕ И АТМОСФЕРА:
- Вдохновляющий и величественный
- Заставляет зрителя чувствовать себя маленьким (в хорошем смысле)
- Изображение аспирационного образа жизни
- Чувство 'это может быть твоим'

ЦВЕТ:
- Богатый, кинематографичный цветовой грейд
- Теплые оранжевые и бирюзовые
- Глубокий синий градиент неба
- Яркий, но естественный

ЦЕЛЬ: Создать изображение настолько эпичное и аспирационное, что зрители не смогут прокрутить дальше.""",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# PROMPT BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

def _build_clickbait_prompt_house(
    final_frame_path: Path,
    scenario: dict[str, Any],
    style_key: str = "dramatic_reveal",
    language: str = "en",
) -> str:
    """
    Build clickbait preview prompt for house building timelapse.
    
    Args:
        final_frame_path: Path to the last frame image
        scenario: Scenario dict with house style, location, etc.
        style_key: Which clickbait style to use
        language: Prompt language ('en' or 'ru')
    
    Returns:
        Enhanced clickbait prompt
    """
    house_style = scenario.get("house_style", "modern")
    location = scenario.get("location", "suburbs")
    
    # Get base style template
    style_template = CLICKBAIT_STYLES.get(style_key, CLICKBAIT_STYLES["dramatic_reveal"])
    base_prompt = style_template["prompt_en"] if language == "en" else style_template["prompt_ru"]
    
    # Add house-specific context
    house_context = f"""
    
SPECIFIC SUBJECT: Luxury {house_style} house construction timelapse.
LOCATION: {location} setting.

CRITICAL INSTRUCTIONS:
- The attached reference image shows the COMPLETED house
- Use it as the BASE but ENHANCE it dramatically
- Boost saturation, contrast, and visual impact by 200%
- Make it IRRESISTIBLE to scroll past
- This is a THUMBNAIL for viral video - CTR is everything

Remember: Keep the house recognizable but make it EPIC."""
    
    return base_prompt + house_context


def _build_clickbait_prompt_vehicle(
    final_frame_path: Path,
    scenario: dict[str, Any],
    style_key: str = "dramatic_reveal",
    language: str = "en",
) -> str:
    """
    Build clickbait preview prompt for vehicle assembly timelapse.
    
    Args:
        final_frame_path: Path to the last frame image
        scenario: Scenario dict with vehicle type, location, etc.
        style_key: Which clickbait style to use
        language: Prompt language ('en' or 'ru')
    
    Returns:
        Enhanced clickbait prompt
    """
    vehicle_type = scenario.get("vehicle_type", "car_modern")
    location = scenario.get("location", "factory")
    
    # Get base style template
    style_template = CLICKBAIT_STYLES.get(style_key, CLICKBAIT_STYLES["dramatic_reveal"])
    base_prompt = style_template["prompt_en"] if language == "en" else style_template["prompt_ru"]
    
    # Add vehicle-specific context
    vehicle_context = f"""
    
SPECIFIC SUBJECT: {vehicle_type} assembly timelapse.
LOCATION: {location} setting.

CRITICAL INSTRUCTIONS:
- The attached reference image shows the COMPLETED vehicle
- Use it as the BASE but ENHANCE it dramatically
- Boost saturation, contrast, and visual impact by 200%
- Make it IRRESISTIBLE to scroll past
- Emphasize sleek design, premium materials, craftsmanship
- This is a THUMBNAIL for viral video - CTR is everything

Remember: Keep the vehicle recognizable but make it EPIC."""
    
    return base_prompt + vehicle_context


# ═══════════════════════════════════════════════════════════════════════════
# MAIN GENERATION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

async def generate_clickbait_preview(
    final_frame_path: Path,
    scenario: dict[str, Any],
    output_dir: Path,
    mode: str = "house",  # "house" or "vehicle"
    style_key: str = "dramatic_reveal",
    language: str = "en",
) -> Path | None:
    """
    Generate a clickbait social media preview from the final frame.
    
    Args:
        final_frame_path: Path to the last frame of the timelapse
        scenario: Scenario dict with style/location info
        output_dir: Directory to save the preview
        mode: "house" (mode8) or "vehicle" (mode9)
        style_key: Clickbait style template to use
        language: Prompt language ('en' recommended for FastGen)
    
    Returns:
        Path to generated preview image, or None if failed
    
    Workflow:
    1. Load final frame as reference
    2. Build enhanced clickbait prompt
    3. Generate AI-enhanced preview using FastGen
    4. Save to output directory
    """
    try:
        # Validate input
        if not final_frame_path.exists():
            logger.error(f"[Clickbait Preview] Final frame not found: {final_frame_path}")
            return None
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Build prompt based on mode
        if mode == "house":
            prompt = _build_clickbait_prompt_house(final_frame_path, scenario, style_key, language)
        elif mode == "vehicle":
            prompt = _build_clickbait_prompt_vehicle(final_frame_path, scenario, style_key, language)
        else:
            logger.error(f"[Clickbait Preview] Invalid mode: {mode}")
            return None
        
        logger.info(f"[Clickbait Preview] Generating {style_key} preview for {mode}...")
        logger.debug(f"[Clickbait Preview] Prompt length: {len(prompt)} chars")
        
        # Generate with FastGen using reference image
        prompts_with_refs = [(prompt, [final_frame_path])]
        
        image_paths = await generate_images_with_references_fastgen(
            prompts_with_refs,
            output_dir,
            parallel=False,
        )
        
        if image_paths and len(image_paths) > 0:
            img_path = image_paths[0]
            if img_path and Path(img_path).exists():
                # Rename to standard name
                new_path = output_dir / f"clickbait_preview_{style_key}.png"
                Path(img_path).rename(new_path)
                logger.success(f"[Clickbait Preview] Generated: {new_path.name}")
                return new_path
        
        logger.error("[Clickbait Preview] Generation failed - no image returned")
        return None
        
    except Exception as e:
        logger.error(f"[Clickbait Preview] Generation failed: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# ALTERNATIVE: MULTIPLE VARIATIONS
# ═══════════════════════════════════════════════════════════════════════════

async def generate_multiple_preview_variations(
    final_frame_path: Path,
    scenario: dict[str, Any],
    output_dir: Path,
    mode: str = "house",
    num_variations: int = 3,
    language: str = "en",
) -> list[Path]:
    """
    Generate multiple preview variations with different styles.
    
    Args:
        final_frame_path: Path to the last frame
        scenario: Scenario dict
        output_dir: Output directory
        mode: "house" or "vehicle"
        num_variations: How many variations to generate (max 4)
        language: Prompt language
    
    Returns:
        List of generated preview paths
    """
    # Select random styles for variety
    available_styles = list(CLICKBAIT_STYLES.keys())
    selected_styles = random.sample(available_styles, min(num_variations, len(available_styles)))
    
    tasks = []
    for style_key in selected_styles:
        task = generate_clickbait_preview(
            final_frame_path=final_frame_path,
            scenario=scenario,
            output_dir=output_dir,
            mode=mode,
            style_key=style_key,
            language=language,
        )
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    valid_paths = []
    for i, result in enumerate(results):
        if isinstance(result, Path):
            valid_paths.append(result)
        elif isinstance(result, Exception):
            logger.error(f"[Preview Variations] Style {selected_styles[i]} failed: {result}")
    
    logger.info(f"[Preview Variations] Generated {len(valid_paths)}/{len(selected_styles)} variations")
    return valid_paths


# Import random for variations
import random
