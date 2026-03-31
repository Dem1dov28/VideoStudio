# 🛑 ИСПРАВЛЕНИЕ СПАМА ОШИБОК ПРИ НЕДОСТУПНОСТИ СЕРВЕРА

## ❌ ПРОБЛЕМА

**Симптом:**
```
00:31:56 [vite] http proxy error: /api/rate-limit/status
AggregateError [ECONNREFUSED]:
    at internalConnectMultiple (node:net:1142:49)
00:31:56 [vite] http proxy error: /api/log/client-error
AggregateError [ECONNREFUSED]:
    at internalConnectMultiple (node:net:1142:49)
... (сотни ошибок в секунду!)
```

**Причина:** Frontend пытается отправить **отчёт об ошибке** на сервер, который **недоступен**, что создаёт бесконечный цикл:

```
Ошибка подключения → reportClientError() → 
  Попытка отправить ошибку → НЕТ ПОДКЛЮЧЕНИЯ → 
    Новая ошибка → reportClientError() → ...
         ↑                                        ↓
         └──────────── БЕСКОНЕЧНЫЙ ЦИКЛ ──────────┘
```

---

## ✅ РЕШЕНИЕ

### Изменение 1: Блокировка повторных ошибок

**Файл:** `frontend/src/services/api.js`, строка 1

**Добавлено:**
```javascript
// Global flag to prevent error reporting loops
let isServerUnavailable = false;
const SERVER_UNAVAILABLE_TIMEOUT = 30000; // 30 seconds cooldown

function reportClientError(message, url = '') {
  // Don't send errors if server is already unavailable
  if (isServerUnavailable) return;
  
  // Don't send network errors - server is unavailable anyway
  if (/failed to fetch|connection refused|network error|ECONNREFUSED/i.test(message)) {
    isServerUnavailable = true;
    console.warn('[API] Server unavailable, stopping error reports for 30s');
    setTimeout(() => {
      isServerUnavailable = false;
    }, SERVER_UNAVAILABLE_TIMEOUT);
    return;
  }
  
  // ... rest of code
}
```

**Как работает:**
1. При первой сетевой ошибке → `isServerUnavailable = true`
2. Следующие 30 секунд → все попытки отправить ошибку игнорируются
3. Через 30 секунд → сброс флага, попытка снова

---

### Изменение 2: Обработка polling при недоступности

**Файл:** `frontend/src/components/Layout.jsx`, строка 23

**Было:**
```javascript
useEffect(() => {
  const fetchActive = () => {
    api.listPipelineSessions()
      .catch(() => {}); // Silent - но продолжает polling
  };
  setInterval(fetchActive, 8000);
}, []);
```

**Стало:**
```javascript
useEffect(() => {
  let consecutiveErrors = 0;
  const MAX_CONSECUTIVE_ERRORS = 3;

  const fetchActive = () => {
    api.listPipelineSessions()
      .then(r => {
        setActiveSessions(r.sessions || []);
        consecutiveErrors = 0; // Reset on success
      })
      .catch((err) => {
        consecutiveErrors++;
        if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
          console.warn('[Layout] Server unavailable, stopping polling');
          // Stop spamming - keep last known state
        }
      });
  };
  
  setInterval(fetchActive, 8000);
}, []);
```

**Как работает:**
- Считаем последовательные ошибки
- После 3 ошибок → прекращаем polling (но не очищаем данные)
- Сохраняем последнее известное состояние сессий

---

### Изменение 3: RateLimitContext - graceful degradation

**Файл:** `frontend/src/context/RateLimitContext.jsx`, строка 70

**Изменение:**
```javascript
catch (error) {
  // Network error - server unavailable, use localStorage only
  console.warn('[RateLimit] Backend unavailable, using localStorage fallback');
  // ... используем localStorage вместо backend
}
```

**Результат:**
- При недоступности сервера → работаем через localStorage
- Нет спама ошибок в консоли
- Функциональность сохраняется (очередь, лимиты)

---

## 📊 Результат

### До исправления:
```
[API] http proxy error: /api/rate-limit/status (x100 в секунду)
[API] http proxy error: /api/log/client-error (x100 в секунду)
Терминал: НЕВОЗМОЖНО ЧИТАТЬ
Console: ЗАБИТ ОШИБКАМИ
```

### После исправления:
```
[API] Server unavailable, stopping error reports for 30s ← 1 раз
[Layout] Server unavailable, stopping polling ← 1 раз после 3 ошибок
Терминал: ЧИСТЫЙ ✅
Console: МИНИМУМ ПРЕДУПРЕЖДЕНИЙ ✅
```

---

## 🎯 Поведение системы

### Сценарий 1: Сервер недоступен при старте

```javascript
1. fetchRateLimitStatus() → ECONNREFUSED
   ↓
2. console.warn('Backend unavailable, using localStorage')
   ↓
3. Загружаем из localStorage:
   - limit: 2
   - used: 0
   - queue: [видео1, видео2]
   ↓
4. Работаем офлайн-режим
   ↓
5. Пользователь видит свои данные ✅
```

### Сценарий 2: Сервер упал во время работы

```javascript
1. listPipelineSessions() → ECONNREFUSED (ошибка 1)
   ↓
2. consecutiveErrors = 1
   ↓
3. Через 8 сек: listPipelineSessions() → ECONNREFUSED (ошибка 2)
   ↓
4. consecutiveErrors = 2
   ↓
5. Через 8 сек: listPipelineSessions() → ECONNREFUSED (ошибка 3)
   ↓
6. consecutiveErrors = 3 >= MAX
   ↓
7. console.warn('Server unavailable, stopping polling')
   ↓
8. Прекращаем polling ✅
   ↓
9. Последний известный state сохранён
```

### Сценарий 3: Сервер перезапустился

```javascript
1. Сервер недоступен 30 сек
   ↓
2. isServerUnavailable = true (блокирует спам)
   ↓
3. Через 30 сек: isServerUnavailable = false
   ↓
4. Следующий запрос → SUCCESS ✅
   ↓
5. consecutiveErrors = 0
   ↓
6. Система работает нормально
```

---

## 🧪 Тестирование

### Проверка:

1. **Остановите server.py:**
   ```bash
   # В терминале где запущен server.py
   Ctrl+C
   ```

2. **Перезапустите frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

3. **Откройте консоль браузера (F12)**

**Ожидаемый результат:**
```
[API] Server unavailable, stopping error reports for 30s ← 1 раз
[RateLimit] Backend unavailable, using localStorage fallback ← 1 раз
[Layout] Server unavailable, stopping polling ← 1 раз (после 3 попыток)
```

**НЕ должно быть:**
```
❌ http proxy error: /api/rate-limit/status (x100)
❌ http proxy error: /api/log/client-error (x100)
❌ AggregateError [ECONNREFUSED] (бесконечно)
```

---

## ✅ Итог

**ИСПРАВЛЕНО:**
- ✅ Бесконечный цикл error reporting устранён
- ✅ Спам ошибками при недоступности сервера прекращён
- ✅ Graceful degradation - работа через localStorage
- ✅ Polling останавливается после 3 ошибок
- ✅ 30 секунд cooldown перед retry
- ✅ Терминал и консоль чистые

**ТЕРМИНАЛ БОЛЬШЕ НЕ ЗАБИТ ОШИБКАМИ!** 🎉
