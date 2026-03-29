# Clickbait Titles Implementation for Mode8 & Mode9

## Обзор изменений

Реализована генерация кликбейтных заголовков для видео в режимах Mode8 (строительство домов) и Mode9 (сборка транспорта) с использованием **реальной длительности** финального видео.

## Примеры заголовков

```
Я ПОСТРОИЛ ДОМ С НУЛЯ ЗА 20 СЕКУНД 🏗️
Я ПОСТРОИЛ ВИЛЛУ В ПУСТЫНЕ ЗА 30 СЕКУНД 🌵
Я ПОСТРОИЛ ДОМ В ЛЕСУ ЗА 15 СЕКУНД 🌲
Я ПОСТРОИЛ ОСОБНЯК С НУЛЯ… СМОТРИ 👀
Я ПОСТРОИЛ ДОМ НА СКАЛЕ ЗА 25 СЕКУНД 🪨
Я СОБРАЛ СПОРТИВНУЮ МАШИНУ ЗА 30 СЕКУНД 🏎️
Я СОБРАЛ САМОЛЕТ НА ЗАВОДЕ ЗА 25 СЕКУНД ✈️
```

## Архитектура

### 1. **clickbait_titles.py** (новый файл)
Расположение: `modes/mode8/clickbait_titles.py` и `modes/mode9/clickbait_titles.py`

**Функция:** `generate_clickbait_title(content_type, style_or_type, location, duration_seconds)`

- Принимает реальную длительность видео в секундах
- Округляет до ближайших 5 секунд (для коротких видео < 30 сек)
- Генерирует случайный шаблон из предопределенных вариантов
- Поддерживает множество типов домов и транспортных средств
- Добавляет релевантные эмодзи

**Логика округления:**
- `< 5 сек` → `5 сек`
- `5-30 сек` → округление до ближайших 5
- `> 30 сек` → округление до ближайших 10

### 2. **Изменения в video_assembler.py**

**Mode8:** `assemble_mode8_video()` теперь возвращает `tuple[Path, float]`
**Mode9:** `assemble_mode9_video()` теперь возвращает `tuple[Path, float]`

Возвращаемое значение:
- `Path` — путь к финальному видео
- `float` — длительность видео в секундах (после всех трансформаций: speed multiplier, crossfades, final hold)

### 3. **Изменения в pipeline.py**

**Последовательность действий:**

```python
# Step 3: Assembly
assembled_path, video_duration = await loop.run_in_executor(
    None,
    functools.partial(assemble_modeX_video, ...)
)

# Step 4: Clickbait Title Generation
from modes.modeX.clickbait_titles import generate_clickbait_title

clickbait_title_ru = generate_clickbait_title(
    content_type="house" | "vehicle",
    style_or_type=house_style_name | vehicle_type_name,
    location=location_name,
    duration_seconds=video_duration,  # Реальная длительность!
)

# Generate publishing metadata with clickbait title
publishing_ru = await generate_publishing_metadata(
    ...,
    title=clickbait_title_ru,  # Используем кликбейтный заголовок
    ...
)
```

## Типы контента

### Mode8 (Дома)
Поддерживаемые стили:
- `modern`, `contemporary`, `minimalist`, `scandinavian`
- `cottage`, `villa`, `farmhouse`, `colonial`, `victorian`, `mediterranean`
- `cabin`, `log_house`, `chalet`, `adobe`
- `mansion`, `estate`

Локации:
- `suburbs`, `forest`, `seaside`, `countryside`, `mountains`
- `desert`, `oasis`, `tropical`, `island`
- И многие другие (полный карта в `clickbait_titles.py`)

### Mode9 (Транспорт)
Поддерживаемые типы:
- **Авиация:** `airplane_passenger`, `airplane_private`, `helicopter`, `drone`
- **Авто:** `car_modern`, `car_sport`, `car_suv`, `car_electric`, `truck_cargo`
- **Спецтехника:** `tractor`, `excavator`, `bulldozer`, `crane_construction`
- **Водный:** `ship_cargo`, `yacht`, `submarine`, `ferry`
- **Индустрия:** `wind_turbine`, `industrial_robot`, `solar_farm`

## Преимущества

1. **Реальное время** — заголовки используют фактическую длительность видео после всех трансформаций
2. **Виральность** — проверенные шаблоны, оптимизированные для YouTube Shorts
3. **Рандомизация** — несколько вариантов шаблонов для разнообразия
4. **Эмодзи** — автоматический подбор релевантных эмодзи
5. **Гибкость** — поддержка множества типов контента и локаций

## Тестирование

Запуск тестов:
```bash
python -m modes.mode8.clickbait_titles
python -m modes.mode9.clickbait_titles
```

Пример генерации:
```python
from modes.mode8.clickbait_titles import generate_clickbait_title

title = generate_clickbait_title(
    content_type="house",
    style_or_type="villa",
    location="desert",
    duration_seconds=23.7,  # Реальная длительность
)
# Результат: "Я ПОСТРОИЛ РОСКОШНУЮ ВИЛЛУ В ПУСТЫНЕ ЗА 25 СЕКУНД 🏰"
```

## Интеграция

Изменения полностью интегрированы в pipeline:
- ✅ Mode8 pipeline обновлен
- ✅ Mode9 pipeline обновлен
- ✅ Ассемблеры возвращают длительность
- ✅ История использует новые заголовки
- ✅ Publishing metadata генерируется с кликбейтными заголовками

## Будущие улучшения

Возможные расширения:
- A/B тестирование разных шаблонов
- Анализ CTR для оптимизации формулировок
- Поддержка дополнительных языков (пока только русский)
- Динамическая генерация на основе трендов
