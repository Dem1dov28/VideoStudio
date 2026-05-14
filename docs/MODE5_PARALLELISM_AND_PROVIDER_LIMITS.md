# Mode 5: параллельность и лимиты провайдеров

## Что гарантирует код

В приложении задаются **верхние границы** (через `config.py` / переменные окружения `MODE5_*`, `VOICEAPI_*`). Реальное число одновременных операций **не превышает**:

1. **TTS (VoiceAPI)** — минимум из:
   - `MODE5_FACTS50_PARALLEL` (желаемая параллельность чанков на этапе TTS),
   - `voiceapi_mode5_recommended_tts_parallel()` → см. `agents/video_editor/tts.py`:  
     `min(VOICEAPI_MAX_CONCURRENCY, max(1, VOICEAPI_PROVIDER_ACTIVE_TASK_LIMIT - VOICEAPI_ACTIVE_TASK_HEADROOM))`.

   То есть без корректного `VOICEAPI_PROVIDER_ACTIVE_TASK_LIMIT` под **ваш** аккаунт высокий `MODE5_FACTS50_PARALLEL` **не даст** больше параллельных POST/поллов, чем позволяет эта формула.

2. **Картинки по сегментам** — семафор в `_generate_chunk_images`: не больше `MODE5_MAX_PARALLEL_IMAGES` (по умолчанию **10**, в ритме с `FASTGEN_*_PARALLEL_WORKERS`) и не больше `MODE5_PARALLEL_IMAGES_HARD_MAX` в `modes/mode5/pipeline.py`.

3. **Параллель чанков в image phase (facts50 / long-form)** — `MODE5_FACTS50_IMAGE_PARALLEL` и `MODE5_LONGFORM_CHUNK_IMAGE_PARALLEL` (отдельно от TTS).

4. **Превью MP4 по чанкам** — `ThreadPoolExecutor` с `MODE5_PREVIEW_MP4_WORKERS`.

5. **Block-loop видео** — `MODE5_BLOCK_LOOP_PARALLEL` (не больше числа блоков и пула).

6. **Intro pool** — `MODE5_INTRO_POOL_PARALLEL`.

7. **Sleep-tail картинки** — `MODE5_SLEEP_TAIL_IMAGE_PARALLEL` и воркеры FFmpeg для сегментов хвоста (связаны с `MODE5_PREVIEW_MP4_WORKERS` в коде пайплайна).

Отдельно **OpenRouter** и **FastGen** имеют свои квоты/лимиты; параллельные LLM-вызовы в генераторах книги / unwritten chapter используют `MODE5_FACTS50_PARALLEL` как размер семафора — при 429 у провайдера LLM значение нужно уменьшать.

## Официальная документация Voicer API

Swagger / описание лимитов: **[voiceapi.csv666.ru/docs](https://voiceapi.csv666.ru/docs)** (там же ссылка на [GET /llm.md](https://voiceapi.csv666.ru/llm.md) для LLM-потребителей).

По этой странице (разделы TTS и Image v2):

| Сервис | Лимит параллельности (как в доке) |
|--------|-------------------------------------|
| **TTS** (`POST /tasks` …) | **не более 5 одновременных задач** |
| **Изображения v2** (асинхронная генерация) | **не более 3 одновременных задач** |

Дефолты **`VOICEAPI_*` в `config.py`** выставлены под **5** одновременных TTS (и формулу в `agents/video_editor/tts.py`). Если у аккаунта другой лимит — правьте `VOICEAPI_PROVIDER_ACTIVE_TASK_LIMIT` / `VOICEAPI_MAX_CONCURRENCY`.

Mode 5 в основном рисует кадры через **FastGen**, а не через VoiceAPI Image — лимит «3 картинки» относится к вызовам **Voicer Image v2**, если вы их используете.

## FastGen (картинки и видео)

Параллель HTTP и браузерных батчей задаётся **`FASTGEN_IMAGE_PARALLEL_WORKERS`** и **`FASTGEN_VIDEO_PARALLEL_WORKERS`** (дефолт **10** каждый). Дополнительно весь процесс делит **`FASTGEN_GLOBAL_MEDIA_CONCURRENCY`** (дефолт **10**): не больше стольких одновременных задач «картинка или видео» суммарно по HTTP и Playwright (см. `agents/content_generator/fastgen_global_media.py`). Для Mode 5 дефолты **`MODE5_MAX_PARALLEL_IMAGES`**, **`MODE5_FACTS50_IMAGE_PARALLEL`**, **`MODE5_LONGFORM_CHUNK_IMAGE_PARALLEL`**, **`MODE5_SLEEP_TAIL_IMAGE_PARALLEL`** также **10**, чтобы суммарная одновременная нагрузка на FastGen не уходила далеко за этот ориентир. При другом лимите тарифа поднимайте значения в `.env` осознанно.

## Практическая настройка

1. Узнать лимит аккаунта (по умолчанию совпадает с [докой Voicer](https://voiceapi.csv666.ru/docs): **5** TTS) → **`VOICEAPI_PROVIDER_ACTIVE_TASK_LIMIT`**.
2. **`VOICEAPI_ACTIVE_TASK_HEADROOM`** — запас под чужие/зависшие задачи; при малом лимите аккаунта большой headroom резко снижает эффективный параллелизм.
3. **`VOICEAPI_MAX_CONCURRENCY`** — не обязательно выше, чем `limit - headroom`; иначе всё равно обрежется формулой выше.
4. **`MODE5_FACTS50_PARALLEL`** — держать в разумных пределах относительно пункта 1 (иначе чанки будут ждать в очереди семафора, а не реально исполняться параллельно).
5. При **429** на TTS — уменьшить `MODE5_FACTS50_PARALLEL` и/или `VOICEAPI_MAX_CONCURRENCY` и/или поднять `VOICEAPI_PROVIDER_ACTIVE_TASK_LIMIT`, если тариф позволяет.
6. **FastGen** — держать `FASTGEN_*_PARALLEL_WORKERS` и связанные `MODE5_*_PARALLEL_*` / `MODE5_MAX_PARALLEL_IMAGES` в одном диапазоне (дефолт **10**); при ошибках/таймаутах провайдера сначала уменьшить параллель.

## Связанные файлы

- `config.py` — все `MODE5_*` и `VOICEAPI_*` с `ge`/`le`.
- `agents/video_editor/tts.py` — `_voiceapi_effective_concurrency`, `voiceapi_mode5_recommended_tts_parallel`.
- `agents/content_generator/fastgen_http.py`, `fastgen_playwright.py` — `FASTGEN_IMAGE_PARALLEL_WORKERS`, `FASTGEN_VIDEO_PARALLEL_WORKERS`.
- `agents/content_generator/fastgen_global_media.py` — общий потолок `FASTGEN_GLOBAL_MEDIA_CONCURRENCY`.
- `modes/mode5/pipeline.py` — семафоры TTS/картинок/превью, `MODE5_PARALLEL_IMAGES_HARD_MAX`.
- `.env.example` — пример переменных для копирования в `.env`.
