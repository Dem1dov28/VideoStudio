# Руководство по созданию нового режима генерации видео

Полное руководство по добавлению нового режима в VideoStudio с поддержкой:
- Параллельной генерации фото через несколько браузеров
- Прикрепления нескольких референсных изображений (фото персонажей)
- Двухэтапного workflow: сначала все фото → потом все видео
- UI для выбора режима на localhost

---

## Структура режима

### Файловая структура

```
modes/
├── modeN/
│   ├── __init__.py
│   ├── pipeline.py           # Главный пайплайн режима
│   ├── scenario_writer.py    # Генерация сценария через LLM
│   ├── video_generator.py    # Генерация фото + видео через FastGen
│   └── video_assembler.py    # Сборка финального видео
```

---

## Шаг 1: Создание модуля режима

### `modes/modeN/__init__.py`

```python
"""Mode N: Название режима."""
from modes.modeN.pipeline import run_modeN_pipeline

__all__ = ["run_modeN_pipeline"]
```

---

## Шаг 2: Video Generator с параллельной генерацией

### `modes/modeN/video_generator.py`

```python
"""
Mode N Video Generator — Двухэтапная генерация:
1. Параллельная генерация ВСЕХ референсных изображений
2. Параллельная генерация ВСЕХ видео с референсами

Ключевые особенности:
- generate_images_with_references_fastgen() — параллельная генерация фото
- Фото персонажей прикрепляются как референсы при генерации
- До 3 референсов на одно изображение/видео (лимит FastGen)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from agents.content_generator.fastgen_scraper import (
    generate_images_with_references_fastgen,  # ← Параллельная генерация с refs
    generate_single_video_multi_ref,          # ← Генерация видео с refs
)
from config import settings


# ═══════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

# Путь к фото персонажей (или другим референсам)
PERSONS_DIR = Path(__file__).resolve().parent.parent.parent / "PEROSNS"

# Визуальные описания персонажей для промптов
CHARACTER_VISUALS = {
    "Персонаж1": "описание внешности персонажа 1",
    "Персонаж2": "описание внешности персонажа 2",
    # ...
}


# ═══════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ═══════════════════════════════════════════════════════════════════════════

def get_character_image_path(character_name: str) -> Path | None:
    """Получить путь к фото персонажа по имени."""
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        path = PERSONS_DIR / f"{character_name}{ext}"
        if path.exists():
            return path
    return None


def get_character_image_paths(character_names: list[str]) -> list[Path]:
    """Получить пути к фото нескольких персонажей."""
    images = []
    for name in character_names:
        path = get_character_image_path(name)
        if path:
            images.append(path)
    return images


def _build_image_prompt(scene: dict[str, Any], index: int, language: str = "ru") -> str:
    """Построить промпт для генерации референсного изображения."""
    characters = scene.get("characters", [])
    action = scene.get("action", "")
    emotion = scene.get("emotion", "neutral")
    location = scene.get("location", "")
    
    # Формируем описания персонажей
    char_descriptions = []
    for char in characters:
        visual = CHARACTER_VISUALS.get(char, f"{char} character")
        char_descriptions.append(f"{char} ({visual})")
    characters_block = "\n".join(f"{i+1}. {desc}" for i, desc in enumerate(char_descriptions))
    
    prompt = f"""Create a high-quality still image for a video scene.

STYLE: [Ваш стиль: 3D cartoon, realistic, anime, etc.]

CHARACTERS IN SCENE:
{characters_block}

LOCATION: {location or "neutral setting"}

SCENE DESCRIPTION:
{action}

EMOTION: {emotion}

COMPOSITION:
- Full body visible for all characters
- Vertical 9:16 aspect ratio
- Characters positioned clearly
- Dynamic poses matching the emotion"""
    
    return prompt


def _build_video_prompt(scene: dict[str, Any], index: int, total: int, language: str = "ru") -> str:
    """Построить промпт для генерации видео."""
    # Аналогично _build_image_prompt, но с дополнительными правилами
    # для аудио, движения камеры, цензуры и т.д.
    # ... (см. modes/mode6/video_generator.py для полного примера)
    pass


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
    Двухэтапная генерация видео с референсными изображениями.
    
    Workflow:
    1. Параллельная генерация ВСЕХ референсных изображений (несколько браузеров)
    2. Параллельная генерация ВСЕХ видео с референсами
    """
    scenes = scenario.get("scenes", [])
    
    if not scenes:
        raise ValueError("No scenes to generate")
    
    fastgen_key = getattr(settings, "fastgen_api_key", "") or ""
    if not fastgen_key:
        raise RuntimeError("FASTGEN_API_KEY not set")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "reference_images"
    images_dir.mkdir(parents=True, exist_ok=True)
    
    # ═══════════════════════════════════════════════════════════════════════
    # ЭТАП 1: Параллельная генерация ВСЕХ референсных изображений
    # ═══════════════════════════════════════════════════════════════════════
    
    logger.info(f"STEP 1: Generating {len(scenes)} reference images in PARALLEL...")
    
    # Формируем список (prompt, reference_image_paths) для каждой сцены
    prompts_with_refs: list[tuple[str, list[Path]]] = []
    scene_data = []
    
    for i, scene in enumerate(scenes):
        # Получаем персонажей для этой сцены (макс 3 для FastGen)
        scene_characters = scene.get("characters", [])[:3]
        character_images = get_character_image_paths(scene_characters)
        
        # Fallback если нет фото персонажей
        if not character_images:
            fallback = scenario.get("characters", [])
            if fallback:
                character_images = get_character_image_paths(fallback[:1])
        
        # Строим промпты
        image_prompt = _build_image_prompt(scene, i, language)
        video_prompt = _build_video_prompt(scene, i, len(scenes), language)
        
        # Добавляем в список для параллельной генерации
        prompts_with_refs.append((image_prompt, character_images))
        
        # Сохраняем данные для генерации видео
        scene_data.append({
            "index": i,
            "video_prompt": video_prompt,
            "character_images": character_images,
        })
        
        logger.info(f"Scene {i+1}: characters={scene_characters}, refs={[p.name for p in character_images]}")
    
    # 🚀 ПАРАЛЛЕЛЬНАЯ генерация изображений с референсами
    image_paths = await generate_images_with_references_fastgen(
        prompts_with_refs,
        images_dir,
        parallel=True,  # ← Включает параллельный режим
    )
    
    # Переименовываем изображения
    ref_image_paths: list[Path | None] = []
    for i, img_path in enumerate(image_paths):
        if img_path and Path(img_path).exists():
            new_path = images_dir / f"scene_{i:03d}_ref.png"
            Path(img_path).rename(new_path)
            ref_image_paths.append(new_path)
        else:
            ref_image_paths.append(None)
    
    # ═══════════════════════════════════════════════════════════════════════
    # ЭТАП 2: Параллельная генерация ВСЕХ видео
    # ═══════════════════════════════════════════════════════════════════════
    
    logger.info(f"STEP 2: Generating {len(scenes)} videos in PARALLEL...")
    
    video_tasks = []
    for i, data in enumerate(scene_data):
        # Комбинируем фото персонажей + сгенерированное референсное изображение
        ref_image = ref_image_paths[i] if i < len(ref_image_paths) else None
        all_references = data["character_images"].copy()
        
        if ref_image and ref_image.exists():
            all_references.append(ref_image)
        
        # Лимит 3 референса (FastGen limit)
        all_references = all_references[:3]
        
        task = _generate_single_video(
            index=i,
            prompt=data["video_prompt"],
            reference_image_paths=all_references,
            output_dir=output_dir,
        )
        video_tasks.append(task)
    
    # 🚀 ПАРАЛЛЕЛЬНАЯ генерация видео
    video_paths = await asyncio.gather(*video_tasks, return_exceptions=True)
    
    # Обработка результатов
    valid_paths: list[Path | None] = []
    for i, result in enumerate(video_paths):
        if isinstance(result, Exception):
            logger.error(f"Scene {i+1} video failed: {result}")
            valid_paths.append(None)
        else:
            valid_paths.append(result)
    
    return valid_paths, scenario


async def _generate_single_video(
    index: int,
    prompt: str,
    reference_image_paths: list[Path],
    output_dir: Path,
) -> Path | None:
    """Генерация одного видео с референсами."""
    try:
        result = await generate_single_video_multi_ref(
            index=index,
            prompt=prompt,
            output_dir=output_dir,
            reference_image_paths=reference_image_paths,
        )
        if result and Path(result).exists():
            logger.success(f"Scene {index+1} video saved")
            return result
        return None
    except Exception as e:
        logger.error(f"Scene {index+1} failed: {e}")
        return None
```

---

## Шаг 3: Pipeline режима

### `modes/modeN/pipeline.py`

```python
"""
Mode N Pipeline — Главный пайплайн режима.

Шаги:
1. Генерация сценария (scenario_writer)
2. Параллельная генерация фото + видео (video_generator)
3. Сборка финального видео (video_assembler)
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from loguru import logger

from config import settings
from modes.modeN.scenario_writer import generate_scenario
from modes.modeN.video_generator import generate_videos
from modes.modeN.video_assembler import assemble_final_video


async def run_modeN_pipeline(
    topic: str,
    session_id: str | None = None,
    language: str = "ru",
    control: dict | None = None,
) -> dict[str, Any]:
    """
    Запуск пайплайна режима N.
    
    Args:
        topic: Тема/идея для видео
        session_id: Уникальный ID сессии
        language: Язык ("ru", "en", etc.)
        control: Контроль паузы/отмены
    
    Returns:
        dict с video_path, session_id, topic
    """
    from pipeline_control import checkpoint
    
    session_id = session_id or str(int(time.time() * 1000))
    output_dir = settings.output_dir / session_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"=== Mode N Pipeline | topic={topic!r} | session={session_id} ===")
    
    await checkpoint(control)
    
    # Шаг 1: Генерация сценария
    logger.info("Step 1/3 - Generating scenario...")
    scenario = await generate_scenario(topic, language=language)
    
    await checkpoint(control)
    
    # Шаг 2: Параллельная генерация фото + видео
    logger.info("Step 2/3 - Generating photos and videos in parallel...")
    video_paths, enriched_scenario = await generate_videos(
        scenario=scenario,
        output_dir=output_dir,
        session_id=session_id,
        language=language,
    )
    
    await checkpoint(control)
    
    # Шаг 3: Сборка финального видео
    logger.info("Step 3/3 - Assembling final video...")
    final_video = await assemble_final_video(
        video_paths=video_paths,
        output_dir=output_dir,
        scenario=enriched_scenario,
    )
    
    logger.success(f"=== Mode N Pipeline DONE | video={final_video} ===")
    
    return {
        "session_id": session_id,
        "video_path": str(final_video) if final_video else None,
        "topic": topic,
    }
```

---

## Шаг 4: Интеграция с FastGen Scraper

### Необходимые функции из `agents/content_generator/fastgen_scraper.py`

```python
# Импорты для video_generator.py
from agents.content_generator.fastgen_scraper import (
    generate_images_with_references_fastgen,  # Параллельная генерация фото с refs
    generate_single_video_multi_ref,          # Генерация видео с refs
)
```

### Ключевые функции в fastgen_scraper.py:

| Функция | Описание |
|---------|----------|
| `generate_images_with_references_fastgen(prompts_with_refs, output_dir, parallel=True)` | Параллельная генерация изображений с multiple references |
| `generate_single_video_multi_ref(index, prompt, output_dir, reference_image_paths)` | Генерация видео с multiple references |
| `_upload_multiple_reference_images(page, image_paths)` | Загрузка до 3 референсных изображений в FastGen UI |
| `_run_fastgen_images_with_refs_parallel_sync()` | ThreadPoolExecutor для параллельной генерации |

### Логика загрузки референсов:

```python
async def _upload_multiple_reference_images(page: Page, image_paths: list[Path]) -> int:
    """
    Загрузка нескольких изображений в FastGen.
    
    UI селекторы:
    - Первый слот: уже открыт
    - Добавление слота: div.aspect-square.flex.flex-col.items-center.justify-center.rounded-lg.border-2.border-dashed.cursor-pointer
    
    Лимит: 3 референса max
    """
    MAX_REFS = 3
    images_to_upload = image_paths[:MAX_REFS]
    
    for i, img_path in enumerate(images_to_upload):
        if i > 0:  # Для второго и третьего — кликаем кнопку добавления
            add_btn = page.locator('div.aspect-square.flex.flex-col.items-center.justify-center.rounded-lg.border-2.border-dashed.cursor-pointer').first
            await add_btn.click()
            await asyncio.sleep(0.5)
        
        # Загружаем изображение
        await _upload_reference_image(page, img_path)
    
    return len(images_to_upload)
```

---

## Шаг 5: Интеграция в UI (Frontend)

### 5.1. Добавление режима в конфигурацию

#### `frontend/src/context/ModeContext.jsx`

```jsx
export const MODES = {
  MODE1: { id: 'mode1', name: 'Short Facts', icon: 'facts' },
  MODE2: { id: 'mode2', name: 'Long Facts', icon: 'book' },
  // ... другие режимы
  MODEN: { id: 'modeN', name: 'Mode N Name', icon: 'new_icon' },  // ← Добавить
};

export const ModeProvider = ({ children }) => {
  const [currentMode, setCurrentMode] = useState(MODES.MODE1);
  // ...
};
```

### 5.2. Компонент выбора режима

#### `frontend/src/components/ModeSelector.jsx`

```jsx
import { MODES } from '../context/ModeContext';

const ModeSelector = ({ currentMode, onModeChange }) => {
  return (
    <div className="flex flex-wrap gap-2 p-4 bg-gray-800 rounded-lg">
      {Object.values(MODES).map((mode) => (
        <button
          key={mode.id}
          onClick={() => onModeChange(mode)}
          className={`px-4 py-2 rounded-lg transition-all ${
            currentMode.id === mode.id
              ? 'bg-blue-600 text-white'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          <span className="mr-2">{getIcon(mode.icon)}</span>
          {mode.name}
        </button>
      ))}
    </div>
  );
};
```

### 5.3. Страница генерации

#### `frontend/src/pages/Generate.jsx`

```jsx
import { useMode } from '../context/ModeContext';
import ModeSelector from '../components/ModeSelector';

const Generate = () => {
  const { currentMode, setCurrentMode } = useMode();
  const [topic, setTopic] = useState('');
  const [language, setLanguage] = useState('ru');
  const [isGenerating, setIsGenerating] = useState(false);
  
  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      const response = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: currentMode.id,  // ← Режим передаётся на бэкенд
          topic,
          language,
        }),
      });
      const data = await response.json();
      // Обработка результата
    } finally {
      setIsGenerating(false);
    }
  };
  
  return (
    <div className="p-6">
      <ModeSelector 
        currentMode={currentMode} 
        onModeChange={setCurrentMode} 
      />
      
      <div className="mt-6 space-y-4">
        <textarea
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="Введите тему для видео..."
          className="w-full p-4 bg-gray-800 rounded-lg text-white"
          rows={4}
        />
        
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="p-2 bg-gray-800 rounded-lg text-white"
        >
          <option value="ru">Русский</option>
          <option value="en">English</option>
        </select>
        
        <button
          onClick={handleGenerate}
          disabled={isGenerating || !topic}
          className="px-6 py-3 bg-blue-600 rounded-lg text-white"
        >
          {isGenerating ? 'Генерация...' : 'Сгенерировать'}
        </button>
      </div>
    </div>
  );
};
```

---

## Шаг 6: Интеграция в Backend

### `server.py` — добавление роута для нового режима

```python
from modes.modeN import run_modeN_pipeline

@app.post("/api/generate")
async def api_generate(request: Request):
    """API endpoint для генерации видео."""
    data = await request.json()
    mode = data.get("mode", "mode1")
    topic = data.get("topic", "")
    language = data.get("language", "ru")
    
    # Маршрутизация по режимам
    if mode == "modeN":
        result = await run_modeN_pipeline(
            topic=topic,
            language=language,
        )
    elif mode == "mode1":
        result = await run_mode1_pipeline(...)
    # ... другие режимы
    else:
        raise HTTPException(400, f"Unknown mode: {mode}")
    
    return result
```

---

## Шаг 7: Dispatcher для WebSocket прогресса

### `orchestrator/dispatcher.py`

```python
from modes.modeN import run_modeN_pipeline

MODE_REGISTRY = {
    "mode1": run_mode1_pipeline,
    "mode2": run_mode2_pipeline,
    # ...
    "modeN": run_modeN_pipeline,  # ← Добавить
}

async def dispatch_generation(
    mode: str,
    topic: str,
    language: str,
    ws_callback: Callable,
):
    """Запуск генерации с WebSocket уведомлениями."""
    pipeline = MODE_REGISTRY.get(mode)
    if not pipeline:
        raise ValueError(f"Unknown mode: {mode}")
    
    # Уведомление о начале
    await ws_callback({"status": "started", "mode": mode})
    
    try:
        result = await pipeline(
            topic=topic,
            language=language,
            control={"ws_callback": ws_callback},
        )
        await ws_callback({"status": "completed", "result": result})
    except Exception as e:
        await ws_callback({"status": "error", "message": str(e)})
        raise
```

---

## Конфигурация

### `.env` — переменные окружения

```env
# FastGen API
FASTGEN_API_KEY=your_api_key_here
FASTGEN_HEADLESS=true
FASTGEN_MODEL=Imagen 3
FASTGEN_IMAGE_TIMEOUT=180
FASTGEN_IMAGE_PARALLEL_WORKERS=5  # Количество параллельных браузеров для фото
FASTGEN_VIDEO_PARALLEL_WORKERS=3  # Количество параллельных браузеров для видео
```

### `config.py` — настройки

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    fastgen_api_key: str = ""
    fastgen_headless: bool = True
    fastgen_model: str = ""
    fastgen_image_timeout: int = 180
    fastgen_image_parallel_workers: int = 5
    fastgen_video_parallel_workers: int = 3
```

---

## Чек-лист для проверки

### Backend:
- [ ] `modes/modeN/__init__.py` создан
- [ ] `modes/modeN/pipeline.py` реализован
- [ ] `modes/modeN/scenario_writer.py` реализован
- [ ] `modes/modeN/video_generator.py` с параллельной генерацией
- [ ] `modes/modeN/video_assembler.py` реализован
- [ ] `server.py` обновлён с роутом для режима
- [ ] `orchestrator/dispatcher.py` обновлён

### Frontend:
- [ ] `ModeContext.jsx` обновлён с новым режимом
- [ ] `ModeSelector.jsx` отображает новый режим
- [ ] `Generate.jsx` передаёт правильный mode_id

### Конфигурация:
- [ ] `.env` содержит FASTGEN_API_KEY
- [ ] `config.py` имеет все необходимые настройки

### Тестирование:
- [ ] Генерация одного изображения с refs работает
- [ ] Параллельная генерация 3+ изображений работает
- [ ] Генерация видео с refs работает
- [ ] WebSocket уведомления приходят
- [ ] UI корректно отображает прогресс

---

## Архитектура параллельной генерации

```
                    ┌─────────────────────────────────┐
                    │     video_generator.py          │
                    │  generate_videos()              │
                    └────────────┬────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│ Browser 1       │   │ Browser 2       │   │ Browser N       │
│ Scene 1 photo   │   │ Scene 2 photo   │   │ Scene N photo   │
│ + char refs     │   │ + char refs     │   │ + char refs     │
└─────────────────┘   └─────────────────┘   └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────────────┐
                    │   Все фото готовы               │
                    │   reference_images/             │
                    └────────────┬────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│ Browser 1       │   │ Browser 2       │   │ Browser N       │
│ Scene 1 video   │   │ Scene 2 video   │   │ Scene N video   │
│ + refs          │   │ + refs          │   │ + refs          │
└─────────────────┘   └─────────────────┘   └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────────────┐
                    │   video_assembler.py            │
                    │   Финальная сборка              │
                    └─────────────────────────────────┘
```

---

## Пример полного workflow

```
1. Пользователь выбирает режим в UI
   ↓
2. UI отправляет POST /api/generate {mode: "modeN", topic: "...", language: "ru"}
   ↓
3. Dispatcher запускает run_modeN_pipeline()
   ↓
4. scenario_writer генерирует сценарий с 6 сценами
   ↓
5. video_generator:
   5.1. Собирает (prompt, [char1.png, char2.png]) для каждой сцены
   5.2. Запускает 5 параллельных браузеров
   5.3. Каждый браузер: загружает фото персонажей → генерирует фото
   5.4. Сохраняет 6 изображений в reference_images/
   ↓
6. video_generator (продолжение):
   6.1. Для каждого видео: комбинирует char refs + generated ref
   6.2. Запускает 3 параллельных браузера для видео
   6.3. Каждый браузер: загружает до 3 refs → генерирует видео
   ↓
7. video_assembler склеивает все видео в одно
   ↓
8. WebSocket отправляет уведомление о завершении
   ↓
9. UI показывает готовое видео
```
