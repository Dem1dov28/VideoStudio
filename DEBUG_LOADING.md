# Диагностика: «Ничего не загружается»

## Шаг 1. Открой DevTools (F12)

Перейди на вкладку **Console**. При загрузке страницы должны появиться логи:

- `[API Diag]` — результат запроса к `/api/debug/diag` (подтверждает, что API доступен)
- `[API] fetch /api/videos` — запрос списка видео
- `[API] /api/videos → 200 Content-Type: application/json` — ответ успешен
- `[API] /api/videos body preview: {"videos":[...]}` — превью ответа

## Шаг 2. Проверь, что означают логи

### Вариант A: `[API Diag]` показывает объект с `api_ok: true`
→ API доступен. Бэкенд отвечает.

### Вариант B: `[API Diag] недоступен: Failed to fetch` или CORS error
→ Запрос не доходит до сервера. Возможные причины:
- Сервер не запущен (`python server.py`)
- Другой порт (ожидается 8000)
- CORS блокирует запрос (проверь `allow_origins` в `server.py`)
- Блокировка антивирусом/фаерволом

### Вариант C: `[API] /api/videos → 200` но `Content-Type: text/html`
→ **Ошибка маршрутизации**: запрос к API попадает в SPA handler и возвращает `index.html` вместо JSON.
- В логах сервера будет: `[ROUTING BUG] /api/ запрос попал в SPA!`
- Решение: порядок маршрутов в FastAPI (API routes должны быть до SPA catch-all)

### Вариант D: `[API] /api/videos НЕ JSON!`
→ Та же проблема: сервер вернул HTML (страницу приложения) вместо JSON.

### Вариант E: Все запросы 200, Content-Type application/json
→ API работает. Если список пустой — проверь:
- `videos_dir` в конфиге (папка с видео)
- Реальное наличие `.mp4` в этой папке
- В DevTools → Network: проверь тело ответа `/api/videos` — есть ли в нём массив `videos`?

## Шаг 3. Вкладка Network

1. F12 → **Network**
2. Обнови страницу (F5)
3. Найди запросы `/api/videos`, `/api/topics/history`, `/api/pipeline/sessions`
4. Кликни по запросу → **Response** — что в теле ответа?
5. **Headers** → Status Code: должен быть 200

## Шаг 4. Прямая проверка API

В браузере открой в новой вкладке:
- `http://localhost:8000/api/debug/diag` — диагностика
- `http://localhost:8000/api/videos` — список видео
- `http://localhost:8000/api/health` — проверка работоспособности

Должен вернуться JSON, а не HTML-страница приложения.

## Шаг 5. Логи сервера

Запусти сервер в терминале и смотри вывод. При каждом запросе:
```
[API] GET /api/videos → 200 (15ms)
[API /videos] returning 3 videos
```

Если видишь `[ROUTING BUG]` — API-запросы неправильно попадают в SPA.

## Исправления, которые уже внесены

1. **React key** — карточки видео используют `session_id + filename` вместо одного `session_id` (избегаем дубликатов при video_ru/video_en)
2. **SPA safeguard** — если `/api/*` попадает в SPA handler, возвращается 404 вместо HTML
3. **Диагностика** — детальные логи в консоли браузера
4. **Проверка Content-Type** — если ответ не JSON, выводится явная ошибка

## Отключение логов

В `frontend/src/services/api.js` установи `const DEBUG_API = false;` и пересобери фронтенд.
