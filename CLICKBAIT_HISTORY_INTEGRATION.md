# Clickbait Title Integration in Topics History

## Изменение

Кликбейтные заголовки теперь правильно подставляются в поле `title` внутри объектов `publishing.ru` и `publishing.en` в файле `topics_history.json`.

## Пример структуры в topics_history.json

**До изменений:**
```json
{
  "topic": "[Timelapse] Timelapse: Строительство коттедж",
  "publishing": {
    "ru": {
      "title": "Строительство Коттеджа: Преображение! 🏠 #Коттедж #Тимелапс",
      "description": "...",
      "tags": [...]
    },
    "en": {
      "title": "House Build Transformation 🏡",
      "description": "...",
      "tags": [...]
    }
  }
}
```

**После изменений:**
```json
{
  "topic": "[Timelapse] Я ПОСТРОИЛ КОТТЕДЖ В ЛЕСУ ЗА 20 СЕКУНД 🌲",
  "publishing": {
    "ru": {
      "title": "Я ПОСТРОИЛ КОТТЕДЖ В ЛЕСУ ЗА 20 СЕКУНД 🌲",
      "description": "...",
      "tags": [...]
    },
    "en": {
      "title": "Я ПОСТРОИЛ КОТТЕДЖ В ЛЕСУ ЗА 20 СЕКУНД 🌲",
      "description": "...",
      "tags": [...]
    }
  }
}
```

## Реализация

### Файл: `modes/mode8/pipeline.py` (и mode9 аналогично)

**Шаг 1:** Генерация кликбейтного заголовка с реальной длительностью
```python
from modes.mode8.clickbait_titles import generate_clickbait_title

clickbait_title_ru = generate_clickbait_title(
    content_type="house",
    style_or_type=house_style_name,
    location=location_name,
    duration_seconds=video_duration,
)
```

**Шаг 2:** Формирование правильной структуры publishing
```python
# Combine both versions with clickbait title
publishing = {
    "ru": {
        "title": clickbait_title_ru,
        **publishing_ru,  # Merge rest of RU metadata
    },
    "en": {
        "title": clickbait_title_ru,  # Use same Russian clickbait title for EN
        **publishing_en,  # Merge rest of EN metadata
    },
}
```

**Шаг 3:** Сохранение в историю
```python
mark_topic_used(
    topic=f"[Timelapse] {clickbait_title_ru}",
    session_id=session_id,
    video_path=str(assembled_path),
    video_angle=f"style={house_style_name},location={location_name},stages={len(stages)},duration={video_duration:.2f}s",
    publishing=publishing,
)
```

## Преимущества

1. **Единый кликбейтный заголовок** — используется во всех полях `title`
2. **Согласованность** — RU и EN версии имеют одинаковый привлекательный заголовок
3. **История с длительностью** — в `video_angle` добавляется информация о реальной длительности видео
4. **Вирусный эффект** — заголовки оптимизированы для YouTube Shorts алгоритма

## Тестирование

После генерации видео проверьте файл `output/topics_history.json`:

```bash
# Пример проверки последней записи
python -c "import json; data=json.load(open('output/topics_history.json', encoding='utf-8')); print(data['topics'][-1]['publishing']['ru']['title']); print(data['topics'][-1]['publishing']['en']['title'])"
```

Оба заголовка должны быть идентичными и содержать кликбейтный формат с временем.

## Примечания

- **RU и EN версии** используют **одинаковый русский кликбейтный заголовок** для консистентности
- Описание и теги остаются уникальными для каждой языковой версии
- Поле `topic` в корне также содержит кликбейтный заголовок с префиксом режима
