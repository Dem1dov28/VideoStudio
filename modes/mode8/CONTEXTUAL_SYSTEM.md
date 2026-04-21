# Mode 8 Contextual Prompt Generation System

## Overview

Интеллектуальная система генерации промптов для Mode8 с использованием LLM на каждом этапе.

## Архитектура

Система состоит из 3 этапов:

### 1. Context Analysis (LLM)
**Файл:** `modes/mode8/contextual_prompt_generator.py`  
**Класс:** `ContextAnalyzer`

Анализирует сценарий и создает план визуальной прогрессии:
- Извлекает ключевые визуальные элементы для каждой стадии
- Определяет эмоциональную прогрессию (начало → середина → кульминация)
- Уникальные особенности каждой стадии

```python
context = await ContextAnalyzer.analyze(scenario)
```

### 2. Image Prompt Generation (LLM + Context)
**Класс:** `ImagePromptGenerator`

Генерирует ВСЕ фото-промпты одной серией с учетом:
- Анализа контекста из Этапа 1
- Визуальной прогрессии (каждая стадия уникальна)
- Предыдущих промптов (перед генерацией следующего)

```python
image_prompts = await ImagePromptGenerator.generate_all_prompts(
    scenario=scenario,
    context=context,
    language="en",
)
```

### 3. Video Prompt Generation (LLM + Recursive Analysis)
**Класс:** `VideoPromptGenerator`

Для КАЖДОГО видео LLM делает:
1. АНАЛИЗ: Смотрит сцену перехода (stage_i → stage_i+1)
2. АНАЛИЗ: Читает фото-промпты обеих стадий
3. АНАЛИЗ: Проверяет предыдущие видео-промпты на повторения
4. ГЕНЕРАЦИЯ: Создает уникальный промпт для этого перехода

```python
video_prompts = await VideoPromptGenerator.generate_all_prompts(
    scenario=scenario,
    context=context,
    image_prompts=image_prompts,
    language="en",
)
```

## Интеграция в Pipeline

Автоматически используется в `modes/mode8/pipeline.py`:

```python
video_paths, enriched_scenario = await generate_house_videos(
    scenario=scenario,
    output_dir=clips_dir,
    session_id=session_id,
    language=language,
    use_contextual=True,  # Включает новую систему
)
```

## Отключение системы

Для отключения контекстной системы передайте `use_contextual=False`:

```python
await generate_house_videos(
    scenario=scenario,
    use_contextual=False,  # Использовать стандартные промпты
)
```

## Тестирование

Запуск тестового скрипта:

```bash
python test_mode8_contextual.py
```

## Ключевые преимущества

1. **История-aware**: Каждый промпт анализирует все предыдущие
2. **LLM на каждом этапе**: Интеллектуальный контекстный анализ
3. **Без повторений**: Система предотвращает дублирование описаний
4. **Визуальная прогрессия**: Четкое развитие от стадии к стадии
5. **Перекрестные зависимость**: Видео-промпты учитывают фото-промпты

## Структура данных

### StageContext
```python
{
    "index": 0,
    "stage_key": "empty_land",
    "name_en": "empty land",
    "visual_theme": "untouched natural landscape",
    "key_elements": ["open terrain", "natural vegetation", "clear sky"],
    "emotional_tone": "anticipation",
    "progression_notes": "Initial state before construction begins"
}
```

### GeneratedPrompt
```python
{
    "stage_index": 0,
    "stage_key": "empty_land",
    "prompt_text": "Create a photorealistic still image...",
    "language": "en",
    "prompt_type": "image",
    "analysis_notes": "Generated with context from 0 previous stages"
}
```

## Производительность

- Контекстный анализ: ~10-15 секунд (1 LLM вызов)
- Генерация фото-промптов: ~2-3 секунды на стадию (N LLM вызовов)
- Генерация видео-промптов: ~3-5 секунд на переход (N-1 LLM вызовов)

Для 5 стадий: ~30-45 секунд на полную генерацию промптов
