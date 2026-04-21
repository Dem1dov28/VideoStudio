# План стиля видео (реализовано)

## 1. Единые дизайн-токены и шрифты

- **`agents/video_editor/design_tokens.py`** — цвета (акцент violet), радиусы pill/hook/badge, отступы субтитров.
- **`agents/video_editor/fonts.py`** — приоритет `assets/fonts/Inter-Bold.ttf` и `Inter-Regular.ttf`, иначе Segoe / Arial (см. `assets/fonts/README.md`).

## 2. Субтитры в стиле Shorts

- **`agents/video_editor/subtitles.py`** — «капсула» под текст (не на всю ширину), обводка, акцентная рамка.
- **Караоке** (`SUBTITLE_KARAOKE=true`): текущее слово подсвечивается по времени сцены (равные доли на слово, без Whisper).
- Отключение: `SUBTITLE_KARAOKE=false` — классика: первое слово золотым, числа фиолетовые.

## 3. Переходы FFmpeg xfade

- **`agents/video_editor/ffmpeg_xfade.py`** — цепочка `xfade` + `acrossfade`.
- **`VIDEO_TRANSITION_ENGINE=xfade`** — рендер каждого сегмента + склейка (нужен **ffmpeg** в PATH; дольше, чем один проход MoviePy).
- **`VIDEO_TRANSITION_STYLES`** — список через запятую, по кругу: `slideleft`, `zoomin`, `smoothleft`, `wipeleft`, `fade`, …
- По умолчанию **`moviepy`** — прежний dissolve в одном проходе; при ошибке xfade — автоматический откат на MoviePy.

## 4. Карточки и оверлеи

- Титул, аутро, хук, счётчик, ватермарк используют **те же токены** и **тот же шрифт**, что и субтитры.

## Зависимости

| Функция        | Требование                          |
|----------------|-------------------------------------|
| Inter          | Файлы в `assets/fonts/` (по желанию)|
| xfade          | `ffmpeg` в PATH                     |
| Караоке        | только настройка в `.env`           |
