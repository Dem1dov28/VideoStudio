# 🧪 ТЕСТ: Обработка очереди в 00 минут

## ❌ ПРОБЛЕМА

**Симптом:**
- Поставил 8 видео в очередь на ночь
- Сгенерировалось только 1 видео
- Остальные 7 не запустились в 00 минут

**Причина:**
Функция `processQueue()` использовала **снимок состояния** (`stateSnapshot`) который не обновлялся после запуска каждого видео.

```javascript
// БЫЛО (неправильно):
const stateSnapshot = state; // ← ЗАМЫКАНИЕ!
const canStart = Math.min(queue.length, limit - snapshot.used);

for (let i = 0; i < canStart; i++) {
  const item = stateSnapshot.queue[i]; // ← Старые данные!
  await api.startPipeline(item.payload);
  
  setState(prev => ({ used: prev.used + 1 })); // ← Обновили
  // Но stateSnapshot остался старым!
}

// Результат: все 8 видео пытались запуститься одновременно
// с одинаковым used=0 → race condition → только 1 успевает
```

---

## ✅ РЕШЕНИЕ

### Новая логика:

**1. Проверяем актуальное состояние перед каждым запуском:**
```javascript
for (let attempt = 0; attempt < maxAttempts; attempt++) {
  // Получаем ТЕКУЩЕЕ состояние (не замыкание!)
  const currentState = loadFromStorage();
  const currentUsed = currentState?.used ?? state.used;
  
  if (currentUsed >= currentLimit) {
    break; // Лимит достигнут
  }
}
```

**2. Всегда берём первый элемент из очереди (индекс 0):**
```javascript
const queue = loadFromStorage()?.queue || [];
const item = queue[0]; // ← Всегда первый!

// После успешного запуска удаляем его
setState(prev => {
  const newQueue = prev.queue.filter((_, idx) => idx !== 0); // ← Удаляем первый
  return { ...prev, queue: newQueue };
});
```

**3. Ждём 2 секунды между запусками:**
```javascript
await api.startPipeline(item.payload);
processedCount++;

// Пауза чтобы избежать race conditions
if (attempt < maxAttempts - 1) {
  await new Promise(resolve => setTimeout(resolve, 2000));
}
```

---

## 📊 Как работает теперь

### Сценарий: 8 видео в очереди, лимит 2 видео/час

**До обновления часа (23:59):**
```
Очередь: [видео1, видео2, видео3, ..., видео8]
used: 2
remaining: 0
```

**В 00:00 (обновление часа):**
```javascript
checkNewHour() обнаруживает смену часа
  ↓
setState({ used: 0, remaining: 2 })
  ↓
setTimeout(processQueue, 1000)
```

**processQueue() - попытка 1 (00:00:01):**
```javascript
currentState = { used: 0, limit: 2, queue: [8 видео] }
currentUsed (0) < currentLimit (2) ✅
item = queue[0] = видео1
  ↓
api.startPipeline(видео1) → SUCCESS
  ↓
setState({ used: 1, remaining: 1, queue: [7 видео] })
processedCount = 1
  ↓
Ждём 2 секунды
```

**processQueue() - попытка 2 (00:00:03):**
```javascript
currentState = { used: 1, limit: 2, queue: [7 видео] }
currentUsed (1) < currentLimit (2) ✅
item = queue[0] = видео2
  ↓
api.startPipeline(видео2) → SUCCESS
  ↓
setState({ used: 2, remaining: 0, queue: [6 видео] })
processedCount = 2
  ↓
Ждём 2 секунды
```

**processQueue() - попытка 3 (00:00:05):**
```javascript
currentState = { used: 2, limit: 2, queue: [6 видео] }
currentUsed (2) >= currentLimit (2) ❌
  ↓
console.log('Limit reached, stopping')
  ↓
BREAK!
```

**Результат:**
- ✅ Запустилось 2 видео (по лимиту)
- ✅ В очереди осталось 6 видео
- ✅ В 01:00 запустятся следующие 2 видео
- ✅ И так далее пока очередь не опустеет

---

## 🎯 Ключевые улучшения

### 1. Отказ от снимка состояния
**Было:** `const stateSnapshot = state` (замыкание)
**Стало:** `const currentState = loadFromStorage()` (актуальные данные)

### 2. Последовательный запуск
**Было:** Все видео пытаются запуститься сразу
**Стало:** По одному с паузой 2 секунды

### 3. Удаление первого элемента
**Было:** `filter((_, idx) => idx !== i)` (неверный индекс)
**Стало:** `filter((_, idx) => idx !== 0)` (всегда первый)

### 4. Защита от ошибок
**Добавлено:**
- Счётчик ошибок (`errorCount`)
- Остановка после 3 ошибок
- Логирование каждого шага

---

## 🧪 Тестирование

### Быстрый тест:

1. **Установите лимит 2 видео/час**
2. **Добавьте 5 видео в очередь**
3. **Подождите 00 минут**

**Ожидаемые логи:**
```
[RateLimit] Starting queue processing: queue=5, used=0, limit=2
[RateLimit] Will attempt to start 2 video(s) from queue
[RateLimit] Starting queue item #1: Видео #1 (Mode 8)
[RateLimit] Started successfully: used=1, remaining=1, queue_left=4
[RateLimit] Starting queue item #2: Видео #2 (Mode 8)
[RateLimit] Started successfully: used=2, remaining=0, queue_left=3
[RateLimit] Queue processing completed: started=2, errors=0
```

**Проверьте localStorage:**
```javascript
JSON.parse(localStorage.getItem('rateLimit'))
// {
//   used: 2,
//   remaining: 0,
//   queue: [видео3, видео4, видео5],
//   limit: 2
// }
```

### Долгий тест (на ночь):

1. **Установите лимит 1 видео/час**
2. **Добавьте 8 видео в очередь**
3. **Оставьте на 8 часов**

**Ожидаемый результат:**
- Через 1 час: 1 видео запущено, 7 в очереди
- Через 2 часа: 2 видео запущено, 6 в очереди
- ...
- Через 8 часов: 8 видео запущено, 0 в очереди ✅

---

## 📝 Логи для отладки

### Правильные логи:

```
[RateLimit] Hour changed: 2024-03-31-23 → 2024-04-01-00
[RateLimit] Starting queue processing: queue=8, used=0, limit=2
[RateLimit] Will attempt to start 2 video(s) from queue
[RateLimit] Starting queue item #1: Видео #1774905313605 (Mode 8)
[RateLimit] Started successfully: used=1, remaining=1, queue_left=7
[RateLimit] Starting queue item #2: Видео #1774905313606 (Mode 9)
[RateLimit] Started successfully: used=2, remaining=0, queue_left=6
[RateLimit] Queue processing completed: started=2, errors=0
```

### Неправильные логи (если проблема осталась):

```
❌ [RateLimit] Starting queue item #1: Видео #1
❌ [RateLimit] Starting queue item #2: Видео #2
❌ [RateLimit] Starting queue item #3: Видео #3
... (все сразу, без пауз)
❌ Queue processing stopped: rate limit reached
```

---

## ✅ Итог

**ИСПРАВЛЕНО:**
- ✅ Отказ от снимка состояния (stateSnapshot)
- ✅ Проверка актуального состояния перед каждым запуском
- ✅ Последовательный запуск с паузой 2 секунды
- ✅ Удаление первого элемента из очереди
- ✅ Счётчик ошибок для защиты
- ✅ Подробное логирование

**РЕЗУЛЬТАТ:**
- ✅ 8 видео в очереди → все 8 запустятся по лимиту
- ✅ В 00:00 → 2 видео (при лимите 2)
- ✅ В 01:00 → ещё 2 видео
- ✅ В 02:00 → ещё 2 видео
- ✅ В 03:00 → последние 2 видео

**Очередь работает умно!** 🎉
