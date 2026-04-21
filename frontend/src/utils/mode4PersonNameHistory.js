/**
 * Локальная история имён для режима 4 (цитата + фото): частота использования в этом браузере.
 */

const STORAGE_KEY = 'mode4_person_name_history_v1';
const MAX_ITEMS = 40;

function _normalizeKey(name) {
  return String(name || '').trim().toLowerCase();
}

function _readRaw() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function _write(items) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    /* quota / private mode */
  }
}

/**
 * Сохранить имя после успешного запуска (непустая строка).
 * Совпадение без учёта регистра увеличивает счётчик; отображаемое имя — последний ввод.
 */
export function recordMode4PersonName(name) {
  const trimmed = String(name || '').trim();
  if (!trimmed) return;
  const key = _normalizeKey(trimmed);
  const items = _readRaw().filter((x) => x && typeof x.name === 'string');
  const now = Date.now();
  let found = false;
  const next = items.map((x) => {
    if (_normalizeKey(x.name) !== key) return x;
    found = true;
    return {
      name: trimmed,
      count: Number(x.count || 0) + 1,
      lastAt: now,
    };
  });
  if (!found) {
    next.push({ name: trimmed, count: 1, lastAt: now });
  }
  next.sort((a, b) => {
    const dc = Number(b.count || 0) - Number(a.count || 0);
    if (dc !== 0) return dc;
    return Number(b.lastAt || 0) - Number(a.lastAt || 0);
  });
  _write(next.slice(0, MAX_ITEMS));
}

/** Имена для подсказок: сначала по частоте, затем по свежести. */
export function getMode4PersonNameSuggestions(limit = 12) {
  const n = Math.max(1, Math.min(30, Number(limit) || 12));
  return _readRaw()
    .filter((x) => x && String(x.name || '').trim())
    .slice(0, n)
    .map((x) => String(x.name).trim());
}
