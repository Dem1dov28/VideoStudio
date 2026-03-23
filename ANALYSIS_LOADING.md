# Анализ: «Ничего не загружается» при 200 OK в логах

## Цепочка загрузки

```
1. Пользователь → /history
2. BrowserRouter (pathname=/history) → Routes рендерит <History />
3. History — lazy: Suspense показывает Spinner, пока chunk не загрузится
4. History chunk загружен → History монтируется
5. useEffect → api.listVideos() → fetch('/api/videos')
6. Сервер 200 OK, JSON {"videos":[...]}
7. .then(r => setVideos(r.videos), setLoading(false))
8. React re-render → рендерим grid с VideoCard
```

## Возможные точки отказа

### A. Запрос не уходит от History
- **Причина**: Логи могут быть от Layout (sessions) или другого компонента
- **Проверка**: В Network смотреть именно запрос `/api/videos` при открытии «Видео»
- **Решение**: Убедиться, что History делает fetch; добавить явный лог при mount

### B. Promise не resolve, хотя 200 OK
- **Причина**: `res.text()` + `JSON.parse` — если после text() что-то throw, promise reject
- **Сценарий**: Content-Type text/html → мы throw до return
- **Проверка**: В request() логировать каждый шаг
- **Решение**: Обойти наш request() — использовать нативный fetch + res.json()

### C. Component unmount до setState
- **Причина**: `cancelled = true` в cleanup → мы не вызываем setVideos/setLoading
- **Сценарий**: Быстрая навигация (History→Topics→History), lazy chunk перезагружается
- **Решение**: Убрать lazy для History/Topics ИЛИ использовать глобальный кэш

### D. Routes / Suspense ремаунтируют детей
- **Причина**: `<Route element={<History />}>` — каждый render создаёт новый элемент
- **Проверка**: React DevTools — смотреть, сколько раз History mount/unmount
- **Решение**: Использовать `element={React.createElement(History)}` или кэш

### E. Framer Motion скрывает контент
- **Причина**: `initial={{ opacity: 0 }}` — если animate не срабатывает, opacity остаётся 0
- **Проверка**: Inspect DOM — есть ли grid с opacity:0
- **Решение**: Убрать initial или использовать CSS вместо motion

### F. Кэш браузера
- **Причина**: Старый JS с багом продолжает выполняться
- **Решение**: Ctrl+Shift+R, очистка кэша, или режим инкогнито

### G. BASE URL неверный
- **Причина**: VITE_API_URL при билде → запросы идут на другой origin
- **Проверка**: В Network смотреть полный URL запроса
- **Решение**: Для same-origin билд: VITE_API_URL не задавать

### H. Строгая проверка Content-Type
- **Причина**: Сервер возвращает 200 + JSON, но Content-Type: text/html
- **Проверка**: Network → Headers → Response Headers
- **Решение**: Временно не проверять ct, просто парсить

### I. React 18 batching / concurrent
- **Причина**: Теоретически, баг в batching
- **Решение**: flushSync для теста (не рекомендуется в проде)

### J. Множественные экземпляры History
- **Причина**: По какой-то причине два History в дереве
- **Решение**: Проверить структуру Routes

## Изменения в этом коммите

1. **Прямой fetch в History** — обходим api.listVideos(), используем fetch + res.json()
2. **Убираем lazy для History и Topics** — мгновенный mount, нет Suspense
3. **Упрощаем motion** — убираем initial opacity 0 с grid
4. **Единый источник BASE** — везде используем api или константу
