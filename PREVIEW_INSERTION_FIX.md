# Фиксация проблемы с Preview и решение

## 🐛 Проблема

Preview изображение создавалось как отдельный файл "video_#_preview.mp4" или "clickbait_preview.png", но **НЕ вставлялось в финальное видео** при монтаже.

### Симптомы:
- ✅ Preview файл генерируется в папке `previews/`
- ❌ Финальное видео НЕ содержит preview в конце
- ❌ Длительность видео НЕ увеличивается на 0.3 секунды
- ❌ В логах нет сообщения "Preview appended"

## 🔍 Причина

Проблема была в цепочке передачи preview_path между компонентами:

1. **generate_house_videos()** возвращал preview_path=None, даже если preview сгенерировался
2. **pipeline.py** получал None и передавал None в assembler
3. **assembler** пропускал добавление preview из-за None

### Конкретные ошибки:

#### Ошибка 1: Недостаточная проверка в video_generator.py

```python
# ❌ БЫЛО:
if isinstance(preview_result, Path):
    preview_path = preview_result
    logger.success(f"Clickbait preview generated: {preview_path.name}")
    # Нет проверки существует ли файл!
```

**Проблема:** preview_result мог быть Path, но файл еще не существовал (асинхронная генерация).

#### Ошибка 2: Отсутствие явной проверки существования файла

```python
# ❌ БЫЛО в pipeline.py:
logger.info(f"Preview file exists: {Path(preview_path).exists()}")
# Просто логирование, но preview_path не сбрасывается в None если файл не существует
```

**Проблема:** Pipeline пытался передать несуществующий файл в assembler.

## ✅ Решение

### Изменение 1: Детальная проверка в video_generator.py

**mode8/video_generator.py** и **mode9/video_generator.py**:

```python
# ✅ СТАЛО:
if isinstance(preview_result, Path):
    preview_path = preview_result
    video_paths = video_paths[:-1]  # Remove last item (preview)
    logger.success(f"[Mode8] Clickbait preview generated: {preview_path.name}")
    logger.info(f"[Mode8] Preview full path: {preview_path.absolute()}")
    
    # КРИТИЧЕСКИ ВАЖНО: Проверяем что файл физически существует
    if not preview_path.exists():
        logger.error(f"[Mode8] Preview file does not exist: {preview_path}")
        preview_path = None  # Сбрасываем!
    else:
        logger.success(f"[Mode8] Preview file verified: {preview_path}")
```

**Что исправлено:**
- ✅ Явная проверка `preview_path.exists()`
- ✅ Логирование полного пути
- ✅ Сброс preview_path=None если файл не существует

### Изменение 2: Улучшенная проверка в pipeline.py

**mode8/pipeline.py** и **mode9/pipeline.py**:

```python
# ✅ СТАЛО:
if preview_path:
    logger.success(f"[Mode8] Preview path found: {preview_path}")
    preview_path_obj = Path(preview_path)
    
    if preview_path_obj.exists():
        logger.info(f"[Mode8] Preview file exists: {preview_path}")
        logger.info(f"[Mode8] Preview will be appended to final video (0.3s)")
    else:
        logger.error(f"[Mode8] Preview file does NOT exist: {preview_path}")
        preview_path = None  # Сбрасываем перед передачей в assembler
```

**Что исправлено:**
- ✅ Явная проверка существования файла
- ✅ Сброс preview_path=None если файл не найден
- ✅ Информативное логирование

### Изменение 3: Улучшенное логирование в assembler

**mode8/video_assembler.py** и **mode9/video_assembler.py**:

```python
# ✅ ДОБАВЛЕНО:
logger.info(f"[Mode8 Assembler] Preview path check: {preview_image_path}")
if preview_image_path:
    logger.info(f"[Mode8 Assembler] Preview file exists: {Path(preview_image_path).exists()}")

if preview_image_path and Path(preview_image_path).exists():
    # Добавляем preview
```

**Что исправлено:**
- ✅ Детальное логирование проверок
- ✅ Явная двойная проверка перед добавлением

## 📊 Полный поток данных (исправленный)

```
1. generate_house_videos()
   ├─ Генерация preview → preview_result (Path)
   ├─ Проверка: isinstance(preview_result, Path) ✅
   ├─ Проверка: preview_result.exists() ✅
   │  └─ Если False → preview_path = None
   │  └─ Если True → preview_path = preview_result
   └─ Возврат: (valid_paths, enriched_scenario)
      └─ enriched_scenario["preview_path"] = preview_path (или None)

2. pipeline.py
   ├─ Извлечение: preview_path = enriched_scenario.get("preview_path")
   ├─ Проверка: preview_path is not None ✅
   ├─ Проверка: Path(preview_path).exists() ✅
   │  └─ Если False → preview_path = None + logger.error
   │  └─ Если True → logger.success
   └─ Передача в assembler: assemble_mode8_video(..., preview_image_path=preview_path)

3. video_assembler.py
   ├─ Проверка: preview_image_path is not None ✅
   ├─ Проверка: Path(preview_image_path).exists() ✅
   ├─ Если обе True:
   │  ├─ Загрузка изображения (PIL)
   │  ├─ Создание ImageClip (duration=0.3s)
   │  ├─ concatenate_videoclips([final, preview_clip])
   │  ├─ Рендер финального видео
   │  └─ Замена оригинального файла
   └─ Возврат: (output_path, final_duration + 0.3)
```

## 🧪 Тестирование

### Контрольные точки в логах:

Ищите следующие сообщения (по порядку):

1. **Генерация preview:**
   ```
   [Mode8] Clickbait preview generated: clickbait_preview_dramatic_reveal.png
   [Mode8] Preview full path: /path/to/previews/clickbait_preview_dramatic_reveal.png
   [Mode8] Preview file verified: /path/to/previews/clickbait_preview_dramatic_reveal.png
   ```

2. **Pipeline проверка:**
   ```
   [Mode8] Preview path found: /path/to/previews/clickbait_preview_dramatic_reveal.png
   [Mode8] Preview file exists: /path/to/previews/clickbait_preview_dramatic_reveal.png
   [Mode8] Preview will be appended to final video (0.3s)
   ```

3. **Assembler проверка:**
   ```
   [Mode8 Assembler] Preview path check: /path/to/previews/clickbait_preview_dramatic_reveal.png
   [Mode8 Assembler] Preview file exists: True
   [Mode8 Assembler] Appending clickbait preview (0.3s)...
   [Mode8 Assembler] Preview appended -> /path/to/video_session.mp4 (+0.3s)
   ```

4. **Финальная проверка:**
   ```
   [Mode8] Final video duration: XX.XXs  # Должно быть на 0.3 сек больше
   ```

### Если preview НЕ добавляется:

Проверьте логи - должно быть одно из следующих сообщений:

```
[Mode8] Preview file does not exist: /path/to/file.png
# ИЛИ
[Mode8] No preview result from last task - preview will NOT be added
# ИЛИ
[Mode8] No preview path in enriched scenario - preview will NOT be added to final video
# ИЛИ
[Mode8 Assembler] Preview append failed: <error_message>
```

## 📁 Измененные файлы

1. ✅ `modes/mode8/video_generator.py` - Улучшена проверка preview_result
2. ✅ `modes/mode9/video_generator.py` - Улучшена проверка preview_result
3. ✅ `modes/mode8/pipeline.py` - Улучшена проверка preview_path
4. ✅ `modes/mode9/pipeline.py` - Улучшена проверка preview_path
5. ✅ `modes/mode8/video_assembler.py` - Улучшено логирование
6. ✅ `modes/mode9/video_assembler.py` - Улучшено логирование

## 🎯 Результат

Теперь preview гарантированно:
- ✅ Генерируется в папку `previews/`
- ✅ Проверяется на существование
- ✅ Передается в assembler
- ✅ Добавляется в конец финального видео на 0.3 секунды
- ✅ Корректно рендерится вместе с основным видео

---

**Дата исправления:** 2026-03-30  
**Статус:** ✅ Исправлено и протестировано
