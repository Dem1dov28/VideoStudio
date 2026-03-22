const BASE = import.meta.env.VITE_API_URL || '';

async function request(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw Object.assign(new Error(err.detail || 'Request failed'), { status: res.status });
  }
  return res.status === 204 ? null : res.json();
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
  generateScenario:   (data)       => request('/api/scenario/generate', { method: 'POST', body: JSON.stringify(data) }),
  listVideos:         ()           => request('/api/videos'),
  getTopicsHistory:   ()           => request('/api/topics/history'),
  clearTopicsHistory: ()           => request('/api/topics/history', { method: 'DELETE' }),
  removeTopic:        (sid)        => request(`/api/topics/history/${sid}`, { method: 'DELETE' }),
  regenerateTopic:    (sid)        => request(`/api/topics/regenerate/${sid}`, { method: 'POST' }),
  videoUrl:           (sid, fname) => `${BASE}/api/video/${sid}/${fname}`,
};

/** Subscribe to SSE log stream. Returns cleanup function. */
export function subscribeToStream(sessionId, onMessage, onDone, onError) {
  const es = new EventSource(`${BASE}/api/pipeline/${sessionId}/stream`);

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === 'done') {
        onDone(data);
        es.close();
      } else if (data.type === 'error') {
        onError(data.error);
        es.close();
      } else if (data.type === 'log') {
        onMessage(data);
      }
      // heartbeat — ignore
    } catch {/* ignore */}
  };

  es.onerror = () => {
    onError('Connection lost');
    es.close();
  };

  return () => es.close();
}
