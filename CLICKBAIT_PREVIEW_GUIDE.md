# Clickbait Preview System для Social Media

## Обзор

Система автоматически генерирует **максимально кликбейтные и красивые превью** для социальных сетей на основе последнего кадра сгенерированного видео (дома в mode8 или техники в mode9).

Превью вставляется в **конец видео на 0.3 секунды** во время монтажа.

---

## Архитектура

### Компоненты

1. **`modes/clickbait_preview.py`** - Основной модуль генерации превью
   - `_build_clickbait_prompt_house()` - Промпт для домов
   - `_build_clickbait_prompt_vehicle()` - Промпт для техники
   - `generate_clickbait_preview()` - Главная функция генерации
   - `generate_multiple_preview_variations()` - Генерация нескольких вариантов

2. **`modes/mode8/video_generator.py`** - Генерация видео для домов
   - Добавлена генерация preview после генерации всех видео
   - Использует последний кадр как reference

3. **`modes/mode9/video_generator.py`** - Генерация видео для техники
   - Аналогично mode8, но для vehicles

4. **`modes/mode8/video_assembler.py`** - Монтаж финального видео
   - Параметр `preview_image_path` - путь к превью
   - Параметр `preview_duration` - длительность показа (0.3 сек)
   - Вставляет превью в конец видео

5. **`modes/mode9/video_assembler.py`** - Монтаж для техники
   - Аналогично mode8

6. **`modes/mode8/pipeline.py`** и **`modes/mode9/pipeline.py`**
   - Связывают генератор и assembler через preview_path

---

## Стилевые шаблоны

Система поддерживает 4 стиля кликбейтных превью:

### 1. Dramatic Reveal (по умолчанию)
- Высокий контраст, драматичное освещение
- Насыщенные цвета
- Кинематографичная цветокоррекция
- Объемные лучи света (god rays)

### 2. Before/After Split
- Вертикальное разделение экрана
- Слева - начальное состояние, справа - результат
- Явный контраст между двумя сторонами

### 3. Extreme Close-up Detail
- Макросъемка деталей
- Малая глубина резкости (боке)
- Акцент на текстуры и материалы

### 4. Epic Wide Angle Showcase
- Широкоугольная эпическая съемка
- Низкий угол для величия
- Драматичное небо и окружение

---

## Рабочий процесс

### Mode 8 (Дом)

```
1. Генерация сценария → 5-8 стадий строительства
2. Генерация reference изображений (последовательно с chaining)
3. Параллельная генерация:
   a) Keyframe видео (переходы между стадиями)
   b) Bonus drone shot (финальный показ)
   c) [NEW] Clickbait preview из последнего кадра ← ПАРАЛЛЕЛЬНО!
4. Ассемблер вставляет preview в конец на 0.3 сек
```

**Оптимизация:** Preview генерируется параллельно с drone video, используя тот же последний кадр. Это экономит время, так как preview не зависит от других видео.

### Mode 9 (Техника)

Аналогично, но для vehicle assembly.

**Ключевое изменение:** Preview теперь генерируется параллельно с финальным drone video, что ускоряет общий процесс генерации.

---

## Интеграция в Pipeline

### Изменения в video_generator

```python
async def generate_house_videos(
    scenario: dict[str, Any],
    output_dir: Path,
    session_id: str,
    language: str = "ru",
    use_contextual: bool = True,
    generate_preview: bool = True,  # NEW параметр
) -> tuple[list[Path | None], dict[str, Any]]:
    # ... генерация видео ...
    
    # STEP 3: CLICKBAIT PREVIEW GENERATION (OPTIONAL)
    if generate_preview and final_frame and Path(final_frame).exists():
        preview_path = await generate_clickbait_preview(
            final_frame_path=Path(final_frame),
            scenario=enriched_scenario,
            output_dir=output_dir / "previews",
            mode="house",
            style_key="dramatic_reveal",
            language="en",
        )
        enriched_scenario["preview_path"] = str(preview_path)
    
    return valid_paths, enriched_scenario
```

### Изменения в video_assembler

```python
def assemble_mode8_video(
    video_paths: list[Path | str],
    output_path: Path,
    title: str | None = None,
    preview_image_path: Path | str | None = None,  # NEW
    preview_duration: float = 0.3,  # NEW
) -> tuple[Path, float]:
    # ... стандартная сборка ...
    
    # APPEND CLICKBAIT PREVIEW (OPTIONAL)
    if preview_image_path and Path(preview_image_path).exists():
        from PIL import Image
        from moviepy import ImageClip, concatenate_videoclips
        
        preview_img = Image.open(str(preview_image_path))
        preview_clip = ImageClip(np.array(preview_img))\
            .with_duration(preview_duration)\
            .with_fps(fps)
        preview_clip = preview_clip.resized((target_w, target_h))
        
        final_with_preview = concatenate_videoclips([final, preview_clip])
        final_with_preview = final_with_preview.with_audio(final.audio)
        
        # Re-render with preview
        # Replace original file
```

### Изменения в pipeline

```python
# Step 2: Generate video clips
video_paths, enriched_scenario = await generate_house_videos(
    scenario=scenario,
    output_dir=clips_dir,
    session_id=session_id,
    language=language,
    use_contextual=True,
    generate_preview=True,  # Включаем генерацию preview
)

# Step 3: Assemble final video
preview_path = enriched_scenario.get("preview_path")

assembled_path, video_duration = await loop.run_in_executor(
    None,
    functools.partial(
        assemble_mode8_video,
        valid_paths,
        output_path,
        title=title,
        preview_image_path=preview_path,  # Передаем preview
        preview_duration=0.3,
    ),
)
```

---

## Промпт для генерации preview

### Для домов (House)

```
Create an EXTREMELY DRAMATIC and EYE-CATCHING social media preview image.

CRITICAL REQUIREMENTS FOR MAXIMUM CTR:
- HIGH CONTRAST: Dramatic lighting with deep shadows and bright highlights
- SATURATED COLORS: Rich, vibrant colors that pop
- CINEMATIC MOOD: Epic, Hollywood-style color grading
- EMOTIONAL IMPACT: Make viewers say "WOW!" instantly

SPECIFIC SUBJECT: Luxury {house_style} house construction timelapse.
LOCATION: {location} setting.

The attached reference image shows the COMPLETED house.
Use it as the BASE but ENHANCE it dramatically.
Boost saturation, contrast, and visual impact by 200%.
Make it IRRESISTIBLE to scroll past.
```

### Для техники (Vehicle)

```
Create an EXTREMELY DRAMATIC and EYE-CATCHING social media preview image.

[Same requirements as above]

SPECIFIC SUBJECT: {vehicle_type} assembly timelapse.
LOCATION: {location} setting.

Emphasize sleek design, premium materials, craftsmanship.
Keep the vehicle recognizable but make it EPIC.
```

---

## Структура выходных файлов

```
output/
└── videos/
    └── {session_id}/
        ├── clips/
        │   ├── stage_000_ref.png
        │   ├── stage_001_ref.png
        │   ├── ...
        │   ├── video_000.mp4
        │   ├── video_001.mp4
        │   ├── ...
        │   └── previews/
        │       └── clickbait_preview_dramatic_reveal.png
        └── video_{session_id}.mp4  # Финальное видео с preview в конце
```

---

## Настройки и параметры

### Можно настроить

- `preview_duration` - Длительность показа preview (по умолчанию 0.3 сек)
- `style_key` - Стиль превью (dramatic_reveal, before_after_split, extreme_closeup, epic_wide_angle)
- `generate_preview` - Включить/выключить генерацию preview
- `language` - Язык промпта ('en' рекомендуется для FastGen)

### Отключение preview

Если нужно отключить генерацию preview:

```python
video_paths, enriched_scenario = await generate_house_videos(
    # ...
    generate_preview=False,  # Отключить preview
)
```

---

## Технические детали

### Требования

- **FastGen API Key** - Для генерации изображений
- **Pillow (PIL)** - Для работы с изображениями
- **MoviePy 2.x** - Для видеомонтажа

### Производительность

- Генерация preview: ~10-20 секунд (зависит от FastGen)
- Вставка в видео: +0.3 сек к длительности + ~5-10 сек на рендер

### Формат preview

- Разрешение: matching video resolution (1080x1920 для vertical 9:16)
- Формат: PNG
- Длительность: 0.3 секунды (300 мс)

---

## Примеры использования

### Базовое использование

```python
from modes.mode8.pipeline import run_mode8_pipeline

result = await run_mode8_pipeline(
    session_id="test_123",
    house_style="modern",
    location="seaside",
    num_stages=5,
    language="ru",
)

# Preview автоматически сгенерировано и вставлено в конец видео
print(f"Video with preview: {result['video_path']}")
print(f"Preview path: {result['scenario'].get('preview_path')}")
```

### Генерация нескольких вариантов

```python
from modes.clickbait_preview import generate_multiple_preview_variations

variations = await generate_multiple_preview_variations(
    final_frame_path=Path("path/to/final_frame.png"),
    scenario=scenario,
    output_dir=Path("output/previews"),
    mode="house",
    num_variations=3,  # Сгенерировать 3 разных стиля
)

# Выбрать лучший вариант вручную или автоматически
best_preview = variations[0]  # Или использовать scoring
```

---

## Будущие улучшения

- [ ] A/B тестирование разных стилей превью для оптимизации CTR
- [ ] Автоматический выбор лучшего стиля на основе контента
- [ ] Добавление текстовых оверлеев ("ШОК!", "ВЫ НЕ ПОВЕРИТЕ!")
- [ ] Sound effect при показе preview (whoosh, boom, etc.)
- [ ] Интеграция с платформами для автоматического upload

---

## Заключение

Система кликбейтных превью автоматически создает **визуально потрясающие** изображения, которые:

✅ Максимально привлекательны для соцсетей  
✅ Используют AI для усиления визуальных эффектов  
✅ Вставляются в конец видео на 0.3 секунды  
✅ Увеличивают CTR и удержание аудитории  

**Результат:** Видео с профессиональным превью, которое невозможно прокрутить! 🎬✨
