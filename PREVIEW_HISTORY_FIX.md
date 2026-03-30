# 🎯 Исправление: Удаление лишних "Видео #_preview" из истории

## 🐛 Проблема

В истории видео создавались лишние пустые записи "Видео #_preview", потому что preview task:
1. Добавлялся в `video_tasks` 
2. Возвращал результат (Path к preview изображению)
3. Попадал в `video_paths` после `asyncio.gather()`
4. Не удалялся корректно из списка результатов
5. Передавался в pipeline как обычное видео

---

## ✅ Решение

### 1️⃣ Явное удаление preview из video_paths

**Файлы:** `modes/mode8/video_generator.py` и `modes/mode9/video_generator.py`

**Добавлено:**
```python
# После asyncio.gather() явно удаляем последний элемент если это preview
if generate_preview and len(video_tasks) > 0:
    preview_result = video_paths[-1] if len(video_paths) > 0 else None
    
    if isinstance(preview_result, Path):
        preview_path = preview_result
        video_paths = video_paths[:-1]  # Удаляем preview из списка
        logger.success(f"Clickbait preview generated: {preview_path.name}")
        
    elif isinstance(preview_result, Exception):
        logger.error(f"Preview generation failed: {preview_result}")
        video_paths = video_paths[:-1]  # Всё равно удаляем
        
    else:
        # Preview task вернул None - всё равно удаляем!
        logger.debug("No preview result from last task")
        video_paths = video_paths[:-1]  # КРИТИЧЕСКИ ВАЖНО!
```

**Ключевой момент:** Даже если preview task вернул None или Exception, мы ВСЕГДА удаляем последний элемент из video_paths.

---

### 2️⃣ Дополнительная фильтрация valid_paths

**Добавлена явная проверка:**

```python
valid_paths: list[Path | None] = []
for i, result in enumerate(video_paths):
    if isinstance(result, Exception):
        logger.error(f"Keyframe video {i + 1} failed: {result}")
        valid_paths.append(None)
    elif result is None:
        valid_paths.append(None)
    else:
        # Явно пропускаем preview paths
        result_path = Path(result) if not isinstance(result, Path) else result
        if 'preview' in str(result_path).lower():
            logger.warning(f"Skipping preview path in video results: {result_path}")
            continue  # НЕ добавляем в valid_paths!
        valid_paths.append(result)
```

**Защита от дублирования:** Даже если preview каким-то образом попал в video_paths после удаления, эта проверка его отфильтрует.

---

## 📊 Полный поток данных (исправленный)

```
1. Создание video_tasks
   ├─ Keyframe videos (N-1 штук)
   ├─ Drone shot (1 штука)
   └─ Preview task (1 штука, если generate_preview=True)
      └─ ДОБАВЛЯЕТСЯ ПОСЛЕДНИМ в video_tasks

2. Выполнение: video_paths = asyncio.gather(*video_tasks)
   └─ Возвращает список [video1, video2, ..., drone_shot, preview_result]

3. Обработка результатов (ИСПРАВЛЕНО!)
   ├─ Проверка последнего элемента
   ├─ Если preview_result is Path:
   │  ├─ preview_path = preview_result
   │  └─ video_paths = video_paths[:-1]  ← УДАЛЯЕМ!
   ├─ Если preview_result is Exception:
   │  └─ video_paths = video_paths[:-1]  ← ТОЖЕ УДАЛЯЕМ!
   └─ Если preview_result is None:
      └─ video_paths = video_paths[:-1]  ← ВСЁ РАВНО УДАЛЯЕМ!

4. Фильтрация valid_paths (ДОПОЛНИТЕЛЬНАЯ ЗАЩИТА!)
   ├─ Для каждого result в video_paths:
   │  └─ Если 'preview' в имени файла:
   │     └─ logger.warning() + continue  ← ПРОПУСКАЕМ!
   └─ Только реальные видео попадают в valid_paths

5. Передача в pipeline
   └─ valid_paths содержит ТОЛЬКО видео (без preview)
   └─ preview_path передается отдельно через enriched_scenario
```

---

## 🔑 Ключевые изменения

### БЫЛО (неправильно):

```python
# Preview task добавлен в video_tasks
video_tasks.append(preview_task)

# После gather все результаты вместе
video_paths = await asyncio.gather(*video_tasks)

# Попытка удалить preview (НЕРАБОТАЛА!)
if generate_preview and len(video_paths) > num_total_videos:
    preview_result = video_paths.pop()
    # ... но если preview_result was None, он оставался в списке!
```

**Проблема:** Если preview task возвращал None, условие `len(video_paths) > num_total_videos` могло быть FALSE, и preview оставался в списке как обычный результат.

---

### СТАЛО (правильно):

```python
# Preview task добавлен последним
video_tasks.append(preview_task)

# После gather все результаты вместе
video_paths = await asyncio.gather(*video_tasks)

# ВСЕГДА проверяем и удаляем последний элемент если это preview task
if generate_preview and len(video_tasks) > 0:
    preview_result = video_paths[-1]
    
    # Всегда удаляем независимо от результата!
    if isinstance(preview_result, Path):
        preview_path = preview_result
        video_paths = video_paths[:-1]
    else:
        # None или Exception - всё равно удаляем!
        video_paths = video_paths[:-1]

# Дополнительная защита при создании valid_paths
for result in video_paths:
    if 'preview' in str(result).lower():
        continue  # Пропускаем preview
    valid_paths.append(result)
```

---

## 🧪 Как проверить что исправление работает

### В логах должно быть:

#### ✅ Успешная генерация preview:

```
[Mode8] Clickbait preview generated: clickbait_preview_dramatic_reveal.png
[Mode8] Preview full path: /path/to/previews/clickbait_preview_dramatic_reveal.png
[Mode8] Preview appended (+0.3s)  # В assembler
```

#### ❌ Если preview не сгенерировался:

```
[Mode8] No preview result from last task  # Но preview удален из video_paths
```

#### ✅ Важно - НЕ должно быть:

```
[Mode8] Skipping preview path in video results: /path/to/preview.png
```

Если видите это сообщение - значит preview каким-то образом попал в video_paths после удаления (маловероятно).

---

## 📁 Измененные файлы

1. ✅ **`modes/mode8/video_generator.py`** (строки 1362-1410)
   - Явное удаление preview из video_paths
   - Дополнительная фильтрация valid_paths

2. ✅ **`modes/mode9/video_generator.py`** (строки 1254-1310)
   - Аналогично mode8

---

## 🎉 Итог

Теперь preview:
- ✅ Генерируется в `previews/clickbait_preview.png`
- ✅ **ВСЕГДА удаляется из video_paths** независимо от результата
- ✅ **НИКОГДА не попадает в valid_paths** (двойная защита)
- ✅ **НЕ создает лишних записей** в истории видео
- ✅ Передается отдельно через `enriched_scenario["preview_path"]`
- ✅ Вставляется в финальное видео при монтаже (через assembler)

**Результат:**
- ✅ В истории видео только реальные construction stages + drone shot
- ✅ Preview отображается как часть финального видео (0.3 сек в конце)
- ✅ Нет пустых или лишних записей "Видео #_preview"

---

**Дата исправления:** 2026-03-30  
**Статус:** ✅ ИСПРАВЛЕНО  
**Тип:** Багфикс - устранение лишних записей в истории
