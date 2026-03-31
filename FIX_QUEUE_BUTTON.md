# Исправление: Кнопка "Сгенерировать timelapse" всегда добавляет в очередь

## 🐛 Проблема

**До исправления:**
- Первый клик на "Сгенерировать timelapse" → видео в очередь ✅
- Второй клик → запускает пайплайн ❌ (должно тоже в очередь)

## ✅ Решение

Добавлена новая функция `queueVideo()` в контексте `RateLimitContext`, которая **ВСЕГДА** добавляет видео в очередь, независимо от доступности лимита.

### Изменения

#### 1. RateLimitContext.jsx
Добавлена новая функция:
```javascript
const queueVideo = useCallback((payload) => {
  // Always adds to queue, no limit check
  const queueItem = { ... };
  setState(prev => ({ ...prev, queue: [...prev.queue, queueItem] }));
  return { status: 'queued', queue_item: queueItem };
}, []);
```

Экспортируется через context:
```javascript
const value = {
  ...state,
  setLimit,
  checkAndStartVideo,
  addToQueue,
  queueVideo, // NEW: always queue
  removeFromQueue,
  processQueue,
  fetchRateLimitStatus,
  isInitialized,
};
```

#### 2. Generate.jsx
Импортируем новую функцию:
```javascript
const { checkAndStartVideo, addToQueue, queueVideo } = useRateLimit();
```

Изменены функции:
- `handleMode8Launch()` — теперь использует `queueVideo()` вместо `checkAndStartVideo()`
- `handleMode9Launch()` — теперь использует `queueVideo()` вместо `checkAndStartVideo()`
- `handleMode10Launch()` — теперь использует `queueVideo()` вместо `checkAndStartVideo()`

**Пример:**
```javascript
// БЫЛО:
const result = await checkAndStartVideo(payload);
if (result.status === 'started') {
  setStartedSession(result.session_id);
} else if (result.status === 'queued') {
  setError('Лимит исчерпан...');
}

// СТАЛО:
const result = queueVideo(payload);
setStep('form');
setError('Видео добавлено в очередь. Запустится при обновлении лимита.');
```

## 🎯 Результат

Теперь при нажатии на кнопку **"Сгенерировать timelapse"** (Mode 8, 9, 10):
- ✅ **ВСЕГДА** добавляется в очередь
- ✅ Никогда не запускается сразу
- ✅ Очередь обрабатывается автоматически в 00 минут
- ✅ Можно добавить сколько угодно видео в очередь

## 📝 Поведение для других режимов

Остальные режимы (Mode 1-7) используют `checkAndStartVideo()`:
- Если лимит доступен → запускаются сразу
- Если лимит исчерпан → добавляются в очередь

Это правильное поведение, так как только Mode 8/9/10 должны работать через очередь.

## ✅ Тестирование

1. Откройте http://localhost:5173
2. Выберите Mode 8, 9 или 10
3. Нажмите "Сгенерировать timelapse"
4. Проверьте левую панель → видео должно быть в очереди
5. Нажмите ещё раз → второе видео тоже в очереди
6. Третий раз → третье видео в очереди
7. Все видео ждут обновления лимита в 00 минут

## 🔍 Проверка

**Очередь отображается:**
- Левая панель → раздел "В очереди"
- Видны все добавленные видео
- Можно удалить кнопкой ❌

**Автозапуск:**
- Дождитесь следующего часа (00 минут)
- Очередь должна запуститься автоматически

---

**Готово!** Теперь кнопка работает корректно - все видео попадают в очередь. 🎉
