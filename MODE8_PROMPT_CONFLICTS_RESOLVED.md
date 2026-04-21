# Mode 8 Prompt Conflicts - RESOLVED ✅

## КОНФЛИКТ #1: Параметры камеры (CRITICAL) - УСТРАНЕН ✅

### Проблема:
Разные значения параметров камеры в разных файлах:
- **video_generator.py**: Y=1.5m, Z=5.0m, 50mm, Horizon 40%
- **contextual_prompt_generator.py**: Y=8.0m, Z=25.0m, 35mm, Horizon 60%

### Решение:
**Унифицированные параметры для ПОЛНОГО обзора дома:**
```
Position: X=0.0m (center), Y=8.0m (height - elevated), Z=25.0m (distance - far)
Angle: Horizontal=0°, Vertical=-10° (slight downward angle from height)
Focal Length: 35mm full-frame equivalent (wide enough for entire house)
Horizon Line: 60% from bottom edge (elevated viewpoint)
Cloud Motion: ALWAYS moving RIGHT (never static, never left)
```

**Измененные файлы:**
1. `video_generator.py` (строки 254-261, 328-335) - обновлены параметры
2. `contextual_prompt_generator.py` (строки 176-183, 555-563) - обновлены параметры

---

## КОНФЛИКТ #2: Статичная vs Динамическая камера - УСТРАНЕН ✅

### Проблема:
Неясность относительно того, где камера должна быть статичной, а где может двигаться.

### Решение:
**Четкое разделение:**

1. **ALL Image Prompts** (все изображения):
   - STATIC CAMERA - COMPLETELY LOCKED
   - Tripod-mounted, bolted to concrete
   - ZERO movement allowed
   - Background FROZEN

2. **ALL Keyframe Video Prompts** (все переходы между стадиями):
   - STATIC CAMERA - SAME position across ALL stages
   - Locked-off tripod
   - Camera must not move

3. **Final Drone Showcase Video** (последний фрагмент - обзор дома):
   - SUBTLE MICRO-MOTION allowed
   - Slight camera vibration for realism
   - ONLY in final showcase (not construction stages)

**Документировано в:**
- `video_generator.py` строка 658: "CRITICAL: ALL keyframe videos use STATIC CAMERA - NO movement except final drone showcase"
- `video_generator.py` строка 708: "CAMERA: Locked-off tripod, static frame. CRITICAL: camera must not move - SAME position across ALL stages"

---

## КОНФЛИКТ #3: Дистанция камеры для полного обзора дома - УСТРАНЕН ✅

### Проблема:
Недостаточно четких указаний на то, что дом должен быть полностью виден в кадре.

### Решение:
**Явные требования к фреймингу:**

1. **House Occupancy**: 40-50% of frame
2. **Distance**: Z=25.0m (far enough for complete view)
3. **Height**: Y=8.0m (elevated for full perspective)
4. **Coverage**: ENTIRE house from foundation to roof, left edge to right edge
5. **NO CROPPING**: Never crop any part of the house

**Добавлено в промпты:**
- `video_generator.py`:
  - Строка 286: "Wide shot showing the ENTIRE house and building site (house occupies 40-50% of frame)"
  - Строка 367: "Wide shot showing the ENTIRE house and building site (house occupies 40-50% of frame)"
  
- `contextual_prompt_generator.py`:
  - Строка 154-156: "FRAMING REQUIREMENT: House should occupy 40-50% of frame"
  - Строка 162-164: "COMPOSITION RULE: Frame the shot to capture the ENTIRE house - imagine you're photographing from 25 meters away at 8 meters height"
  - Строка 560: "- Framing: ENTIRE house must be fully visible with surrounding landscape"

---

## КОНФЛИКТ #4: Стиль генерации изображений - УСТРАНЕН ✅

### Проблема:
Разные указания на стиль генерации (smartphone camera vs professional photograph vs 3D render).

### Решение:
**Единый стандарт для ВСЕХ промптов:**

```
STYLE: Photorealistic, shot on smartphone camera, natural lighting, 
authentic construction site look. NOT 3D render, NOT CGI, NOT animated, 
NOT cartoon. Must look like REAL smartphone footage.
```

**Добавлено в:**
1. `video_generator.py`:
   - Строка 273: Полный текст стиля
   - Строка 348: Полный текст стиля
   
2. `contextual_prompt_generator.py`:
   - Строка 186: Добавлен STYLE раздел в IMAGE_PROMPT_GENERATION_PROMPT
   - Строка 560: "- STYLE: Photorealistic smartphone photo, NOT 3D render, NOT CGI"

---

## ИТОГОВАЯ ПРОВЕРКА

### ✅ Все параметры камеры унифицированы:
- X=0.0m, Y=8.0m, Z=25.0m
- 35mm focal length
- 60% horizon line
- -10° vertical angle

### ✅ Все промпты используют статичную камеру:
- Image prompts: FULLY STATIC
- Keyframe video prompts: FULLY STATIC
- Final drone showcase: SUBTLE MICRO-MOTION (только этот)

### ✅ Полный обзор дома гарантирован:
- House occupies 40-50% of frame
- Distance 25m, Height 8m
- Wide angle 35mm
- Explicit "ENTIRE HOUSE" requirements

### ✅ Единый стиль генерации:
- Smartphone camera photorealism
- NOT 3D render/CGI/cartoon
- Natural lighting
- Authentic construction site look

---

## ФАЙЛЫ С ИЗМЕНЕНИЯМИ

1. **modes/mode8/video_generator.py**
   - Обновлены все CAMERA CALIBRATION DATA секции
   - Добавлен STYLE раздел во все image prompts
   - Обновлены COMPOSITION требования
   - Обновлен _build_keyframe_video_prompt

2. **modes/mode8/contextual_prompt_generator.py**
   - Обновлены CAMERA CALIBRATION DATA в IMAGE_PROMPT_GENERATION_PROMPT
   - Добавлен STYLE раздел
   - Обновлена функция _get_camera_specs_for_scenario
   - Добавлены явные framing requirements

---

## РЕКОМЕНДАЦИИ ДЛЯ БУДУЩЕГО

1. **Всегда проверяйте консистентность параметров камеры** при добавлении новых промптов
2. **Используйте копипасту утвержденных параметров** вместо изобретения велосипеда
3. **Тестируйте генерацию** на предмет соответствия требованиям:
   - Дом полностью виден?
   - Фон не меняется между стадиями?
   - Камера статична (кроме финального дрона)?
   - Стиль соответствует smartphone photography?
