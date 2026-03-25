const BASE = import.meta.env.VITE_API_URL || '';

function reportClientError(message, url = '') {
  // Не слать на сервер при сетевых ошибках — сервер всё равно недоступен
  if (/failed to fetch|connection refused|network error/i.test(message)) return;
  try {
    fetch(`${BASE}/api/log/client-error`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, url }),
    }).catch(() => {});
  } catch {}
}

const DEBUG_API = false; // Включить для отладки API

async function request(path, opts = {}) {
  const url = `${BASE}${path}`;
  if (DEBUG_API) console.log(`[API] fetch ${url}`);
  try {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...opts.headers },
      ...opts,
    });
    const ct = res.headers.get('content-type') || '';
    if (DEBUG_API) console.log(`[API] ${path} → ${res.status} Content-Type: ${ct.slice(0, 50)}`);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      if (DEBUG_API) console.error(`[API] ${path} ERROR:`, err);
      reportClientError(`${res.status}: ${err.detail || res.statusText}`, path);
      throw Object.assign(new Error(err.detail || 'Request failed'), { status: res.status });
    }

    if (res.status === 204) return null;

    const text = await res.text();
    if (DEBUG_API && (path.includes('videos') || path.includes('topics') || path.includes('sessions'))) {
      const preview = text.slice(0, 200);
      console.log(`[API] ${path} body preview:`, preview + (text.length > 200 ? '...' : ''));
    }

    if (!ct.includes('application/json')) {
      if (DEBUG_API) console.error(`[API] ${path} НЕ JSON! Получен:`, text.slice(0, 300));
      reportClientError(`Expected JSON, got ${ct}`, path);
      throw new Error(`Сервер вернул HTML вместо JSON. Проверь маршрутизацию.`);
    }

    try {
      return JSON.parse(text);
    } catch (parseErr) {
      if (DEBUG_API) console.error(`[API] ${path} JSON parse error:`, parseErr, 'text:', text.slice(0, 200));
      throw new Error('Сервер вернул некорректный JSON');
    }
  } catch (e) {
    if (DEBUG_API) console.error(`[API] ${path} catch:`, e);
    reportClientError(e.message || String(e), path);
    throw e;
  }
}

export const api = {
  uploadImage:        (file)       => {
    const fd = new FormData();
    fd.append('file', file);
    return fetch((import.meta.env.VITE_API_URL || '') + '/api/upload/image', {
      method: 'POST',
      body: fd,
      headers: {},
    }).then(r => r.ok ? r.json() : r.json().then(e => { throw new Error(e.detail || 'Upload failed'); }));
  },
  startPipeline:      (data)       => request('/api/pipeline/start', { method: 'POST', body: JSON.stringify(data) }),
  listPipelineSessions: ()         => request('/api/pipeline/sessions'),
  getPipelineStatus:  (sid)       => request(`/api/pipeline/${sid}/status`),
  pausePipeline:      (sid)       => request(`/api/pipeline/${sid}/pause`, { method: 'POST' }),
  resumePipeline:     (sid)       => request(`/api/pipeline/${sid}/resume`, { method: 'POST' }),
  cancelPipeline:     (sid)       => request(`/api/pipeline/${sid}/cancel`, { method: 'POST' }),
  restartPipeline:    (sid)       => request(`/api/pipeline/${sid}/restart`, { method: 'POST' }),
  generateScenario:   (data)       => request('/api/scenario/generate', { method: 'POST', body: JSON.stringify(data) }),
  listVideos:         ()           => request('/api/videos'),
  getTopicsHistory:   ()           => request('/api/topics/history'),
  clearTopicsHistory: ()           => request('/api/topics/history', { method: 'DELETE' }),
  removeTopic:        (sid)        => request(`/api/topics/history/${sid}`, { method: 'DELETE' }),
  regenerateTopic:    (sid)        => request(`/api/topics/regenerate/${sid}`, { method: 'POST' }),
  videoUrl:           (sid, fname) => `${BASE}/api/video/${sid ?? ''}/${fname ?? ''}`,
  thumbnailUrl:       (sid)        => `${BASE}/api/video/${sid}/thumbnail`,
  deleteVideo:        (sid)        => request(`/api/videos/${sid}`, { method: 'DELETE' }),
  // Keyframe video generation (start + end frame)
  generateKeyframeVideo: (data) => request('/api/video/keyframe', { method: 'POST', body: JSON.stringify(data) }),
  regenerateVideo: (sid, opts = {}) =>
    request(`/api/videos/${sid}/regenerate`, {
      method: 'POST',
      body: JSON.stringify(opts.filename ? { filename: opts.filename } : {}),
    }),
};

/** Subscribe to SSE log stream. Returns cleanup function. */
export function subscribeToStream(sessionId, onMessage, onDone, onError) {
  const es = new EventSource(`${BASE}/api/pipeline/${sessionId}/stream`);
  let closed = false;

  const finish = () => {
    closed = true;
    try {
      es.close();
    } catch {/* ignore */}
  };

  es.onmessage = (e) => {
    if (closed) return;
    try {
      const data = JSON.parse(e.data);
      if (data.type === 'done') {
        finish();
        onDone(data);
      } else if (data.type === 'error') {
        finish();
        onError(data.error);
      } else if (data.type === 'log') {
        onMessage(data);
      }
    } catch {/* ignore */}
  };

  es.onerror = () => {
    if (closed) return;
    finish();
    onError('Connection lost');
  };

  return () => {
    finish();
  };
}
