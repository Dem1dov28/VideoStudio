const BASE = import.meta.env.VITE_API_URL || '';

// Global flag to prevent error reporting loops
let isServerUnavailable = false;
const SERVER_UNAVAILABLE_TIMEOUT = 30000; // 30 seconds cooldown
const clientErrorCooldownMs = 5000;
const recentClientErrors = new Map();

function reportClientError(message, url = '') {
  // Don't send errors if server is already unavailable (prevent spam)
  if (isServerUnavailable) return;
  const key = `${url}::${message}`;
  const now = Date.now();
  const lastAt = recentClientErrors.get(key) || 0;
  if (now - lastAt < clientErrorCooldownMs) return;
  recentClientErrors.set(key, now);
  
  // Don't send network errors - server is unavailable anyway
  if (/failed to fetch|connection refused|network error|ECONNREFUSED/i.test(message)) {
    isServerUnavailable = true;
    console.warn('[API] Server unavailable, stopping error reports for 30s');
    setTimeout(() => {
      isServerUnavailable = false;
    }, SERVER_UNAVAILABLE_TIMEOUT);
    return;
  }
  
  try {
    fetch(`${BASE}/api/log/client-error`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, url }),
    }).catch(() => {}); // Ignore errors silently
  } catch (e) {
    // Ignore silently - don't create more errors
  }
}

const DEBUG_API = false; // Включить для отладки API
const makeActionId = () => `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

async function request(path, opts = {}) {
  const url = `${BASE}${path}`;
  const { timeoutMs = 0, ...fetchOpts } = opts;
  const controller = new AbortController();
  const timeoutId =
    timeoutMs > 0
      ? setTimeout(() => controller.abort(new DOMException('Request timeout', 'AbortError')), timeoutMs)
      : null;
  if (DEBUG_API) console.log(`[API] fetch ${url}`);
  try {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...fetchOpts.headers },
      ...fetchOpts,
      signal: controller.signal,
    });
    const ct = res.headers.get('content-type') || '';
    if (DEBUG_API) console.log(`[API] ${path} → ${res.status} Content-Type: ${ct.slice(0, 50)}`);

    if (!res.ok) {
      const raw = await res.text().catch(() => '');
      let err = { detail: res.statusText };
      try {
        err = raw ? JSON.parse(raw) : err;
      } catch {
        if (raw && raw.trim()) {
          // Keep first line only; avoid giant HTML dumps
          err = { detail: raw.trim().split('\n')[0] };
        }
      }
      if (DEBUG_API) console.error(`[API] ${path} ERROR:`, err);
      let msg = err.detail ?? err.message ?? res.statusText;
      if (Array.isArray(msg)) {
        msg = msg.map((x) => (typeof x === 'object' && x.msg ? x.msg : String(x))).join('; ');
      } else if (msg && typeof msg === 'object') {
        msg = JSON.stringify(msg);
      }
      reportClientError(`${res.status}: ${msg}`, path);
      throw Object.assign(new Error(msg || 'Request failed'), {
        status: res.status,
        alreadyReported: true,
      });
    }

    if (res.status === 204) return null;

    const text = await res.text();
    if (DEBUG_API && (path.includes('videos') || path.includes('topics') || path.includes('sessions'))) {
      const preview = text.slice(0, 200);
      console.log(`[API] ${path} body preview:`, preview + (text.length > 200 ? '...' : ''));
    }

    if (!/json|\+json/i.test(ct)) {
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
    if (e?.name === 'AbortError') {
      const t = timeoutMs > 0 ? ` (${Math.round(timeoutMs / 1000)}с)` : '';
      const timeoutError = new Error(`Таймаут запроса${t}`);
      reportClientError(timeoutError.message, path);
      throw timeoutError;
    }
    if (DEBUG_API) console.error(`[API] ${path} catch:`, e);
    if (!e?.alreadyReported) {
      reportClientError(e.message || String(e), path);
    }
    throw e;
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

async function requestForm(path, formData, opts = {}) {
  const url = `${BASE}${path}`;
  const { timeoutMs = 0, ...fetchOpts } = opts;
  const controller = new AbortController();
  const timeoutId =
    timeoutMs > 0
      ? setTimeout(() => controller.abort(new DOMException('Request timeout', 'AbortError')), timeoutMs)
      : null;
  try {
    const res = await fetch(url, {
      method: 'POST',
      body: formData,
      ...fetchOpts,
      signal: controller.signal,
    });
    if (!res.ok) {
      const raw = await res.text().catch(() => '');
      let msg = raw || res.statusText || 'Upload failed';
      try {
        const parsed = raw ? JSON.parse(raw) : {};
        msg = parsed.detail || parsed.message || msg;
      } catch {
        // keep text fallback
      }
      throw Object.assign(new Error(String(msg)), { status: res.status });
    }
    return await res.json();
  } catch (e) {
    reportClientError(e?.message || String(e), path);
    throw e;
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

export const api = {
  uploadImage:        (file)       => {
    const fd = new FormData();
    fd.append('file', file);
    return requestForm('/api/upload/image', fd);
  },
  uploadAudio:        (file)       => {
    const fd = new FormData();
    fd.append('file', file);
    return requestForm('/api/upload/audio', fd);
  },
  /** Короткий WAV с фильтрами пресета (предпрослушивание mode 13). */
  mode13VoicePreview: async (body) => {
    const url = `${BASE}/api/mode13/voice-preview`;
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || r.statusText || 'Voice preview failed');
    }
    return r.blob();
  },
  startPipeline:      (data)       => request('/api/pipeline/start', { method: 'POST', body: JSON.stringify(data) }),
  mode4RegenerateClip: (sid, index) =>
    request(`/api/mode4/${sid}/regenerate-clip`, {
      method: 'POST',
      body: JSON.stringify({ index }),
      timeoutMs: 900000,
    }),
  mode4SetClipTrim: (sid, index, startSec, endSec) =>
    request(`/api/mode4/${sid}/set-clip-trim`, {
      method: 'POST',
      body: JSON.stringify({ index, start_sec: startSec, end_sec: endSec }),
    }),
  mode4ClearClipTrim: (sid, index) =>
    request(`/api/mode4/${sid}/clear-clip-trim`, {
      method: 'POST',
      body: JSON.stringify({ index }),
    }),
  mode4Assemble: (sid, showSubtitles = undefined) =>
    request(`/api/mode4/${sid}/assemble`, {
      method: 'POST',
      body: JSON.stringify(
        showSubtitles === undefined ? {} : { show_subtitles: showSubtitles },
      ),
    }),
  mode4LocationOptions: (personName, quote = '', limit = 7) =>
    request('/api/mode4/location-options', {
      method: 'POST',
      body: JSON.stringify({ person_name: personName, quote, limit }),
    }),
  mode13RegenerateSegment: (sid, chunkIndex, segmentIndex) =>
    request(`/api/mode13/${sid}/regenerate-segment`, {
      method: 'POST',
      body: JSON.stringify({ chunk_index: chunkIndex, segment_index: segmentIndex }),
    }),
  mode5RegenerateImage: (sid, chunkIndex, segmentIndex) =>
    request(`/api/mode5/${sid}/regenerate-image`, {
      method: 'POST',
      body: JSON.stringify({ chunk_index: chunkIndex, segment_index: segmentIndex }),
    }),
  mode5RegenerateChunk: (sid, chunkIndex, text) =>
    request(`/api/mode5/${sid}/regenerate-chunk`, {
      method: 'POST',
      body: JSON.stringify({ chunk_index: chunkIndex, text }),
    }),
  mode5Assemble: (sid) =>
    request(`/api/mode5/${sid}/assemble`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  mode5ReviewState: (sid) =>
    request(`/api/mode5/${sid}/review-state`),
  mode5ContinueGeneration: (sid) =>
    request(`/api/mode5/${sid}/continue-generation`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  mode5LiveRegenerateImage: (sid, chunkIndex, segmentIndex, actionId = makeActionId()) =>
    request(`/api/mode5/${sid}/live/regenerate-image`, {
      method: 'POST',
      body: JSON.stringify({ chunk_index: chunkIndex, segment_index: segmentIndex, action_id: actionId }),
      timeoutMs: 120000,
    }),
  mode5LiveRegenerateAudio: (sid, chunkIndex, actionId = makeActionId()) =>
    request(`/api/mode5/${sid}/live/regenerate-audio`, {
      method: 'POST',
      body: JSON.stringify({ chunk_index: chunkIndex, action_id: actionId }),
      timeoutMs: 120000,
    }),
  mode5LiveRebuildChunkPreview: (sid, chunkIndex, actionId = makeActionId()) =>
    request(`/api/mode5/${sid}/live/rebuild-chunk-preview`, {
      method: 'POST',
      body: JSON.stringify({ chunk_index: chunkIndex, action_id: actionId }),
      timeoutMs: 120000,
    }),
  mode5LiveRegenerateBlockLoop: (sid, chunkIndex, actionId = makeActionId()) =>
    request(`/api/mode5/${sid}/live/regenerate-block-loop`, {
      method: 'POST',
      body: JSON.stringify({ chunk_index: chunkIndex, action_id: actionId }),
      timeoutMs: 180000,
    }),
  mode5LiveRegenerateIntroPreview: (sid, previewIndex, actionId = makeActionId()) =>
    request(`/api/mode5/${sid}/live/regenerate-intro-preview`, {
      method: 'POST',
      body: JSON.stringify({ chunk_index: previewIndex, action_id: actionId }),
      timeoutMs: 180000,
    }),
  mode5LiveRebuildFinal: (sid, actionId = makeActionId()) =>
    request(`/api/mode5/${sid}/live/rebuild-final`, {
      method: 'POST',
      body: JSON.stringify({ action_id: actionId }),
      timeoutMs: 180000,
    }),
  mode5LiveRegeneratePublishThumbnail: (sid, actionId = makeActionId()) =>
    request(`/api/mode5/${sid}/live/regenerate-publish-thumbnail`, {
      method: 'POST',
      body: JSON.stringify({ action_id: actionId }),
      timeoutMs: 180000,
    }),
  mode5PublishThumbnailUrl: (sid) => `${BASE}/api/mode5/${encodeURIComponent(sid)}/publish-thumbnail`,
  mode5LivePauseChunk: (sid, chunkIndex, actionId = makeActionId()) =>
    request(`/api/mode5/${sid}/live/pause-chunk`, {
      method: 'POST',
      body: JSON.stringify({ chunk_index: chunkIndex, action_id: actionId }),
    }),
  mode5LiveResumeChunk: (sid, chunkIndex, actionId = makeActionId()) =>
    request(`/api/mode5/${sid}/live/resume-chunk`, {
      method: 'POST',
      body: JSON.stringify({ chunk_index: chunkIndex, action_id: actionId }),
    }),
  mode5TopicIdeas: (subMode, limit = 8, seed = null) =>
    request('/api/mode5/topic-ideas', {
      method: 'POST',
      body: JSON.stringify({ sub_mode: subMode, limit, seed }),
    }),
  mode5CachedTopicIdeas: (subMode, limit = 8) =>
    request(`/api/mode5/topic-ideas?sub_mode=${encodeURIComponent(subMode)}&limit=${encodeURIComponent(limit)}`),
  mode5ConsumeIdea: (ideaId, status = 'clicked') =>
    request('/api/mode5/topic-ideas/consume', {
      method: 'POST',
      body: JSON.stringify({ idea_id: ideaId, status }),
    }),
  mode13Assemble: (sid, showSubtitles = undefined) =>
    request(`/api/mode13/${sid}/assemble`, {
      method: 'POST',
      body: JSON.stringify(
        showSubtitles === undefined ? {} : { show_subtitles: showSubtitles },
      ),
    }),
  listPipelineSessions: ()         => request('/api/pipeline/sessions'),
  getPipelineStatus:  (sid)       => request(`/api/pipeline/${sid}/status`),
  getPipelineStartRequest: (sid) => request(`/api/pipeline/${sid}/start-request`),
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
  deleteVideo:        (sid, filename) => {
    const q =
      filename != null && String(filename).trim() !== ''
        ? `?filename=${encodeURIComponent(String(filename).trim())}`
        : '';
    return request(`/api/videos/${sid}${q}`, { method: 'DELETE' });
  },
  // Keyframe video generation (start + end frame)
  generateKeyframeVideo: (data) => request('/api/video/keyframe', { method: 'POST', body: JSON.stringify(data) }),
  regenerateVideo: (sid, opts = {}) =>
    request(`/api/videos/${sid}/regenerate`, {
      method: 'POST',
      body: JSON.stringify(opts.filename ? { filename: opts.filename } : {}),
    }),
  // Rate Limit API
  getRateLimitStatus: () => request('/api/rate-limit/status'),
  setRateLimit: (limit) => request('/api/rate-limit/set', { method: 'POST', body: JSON.stringify({ limit }) }),
  checkRateLimit: () => request('/api/rate-limit/check', { method: 'POST' }),
  incrementRateLimit: () => request('/api/rate-limit/increment', { method: 'POST' }),
  // Queue API (server-side)
  queueAdd: (payload) => request('/api/queue/add', { method: 'POST', body: JSON.stringify({ payload }) }),
  queueStatus: () => request('/api/queue/status'),
  queueDelete: (itemId) => request(`/api/queue/${itemId}`, { method: 'DELETE' }),
  queueMove: (itemId, direction) =>
    request(`/api/queue/${itemId}/move`, { method: 'POST', body: JSON.stringify({ direction }) }),
  /** YouTube Data API: статус OAuth и загрузка Shorts */
  /** @param {boolean} [quick] только диск, без channels.list */
  youtubeStatus: (quick = false) =>
    request(quick ? '/api/youtube/status?quick=true' : '/api/youtube/status'),
  youtubeOAuthStart: (profile = 'primary') =>
    request(`/api/youtube/oauth/authorize?profile=${encodeURIComponent(profile)}`),
  youtubeUpload: (body) =>
    request('/api/youtube/upload', {
      method: 'POST',
      body: JSON.stringify(body),
      timeoutMs: 16 * 60 * 1000,
    }),
  youtubeResetTokens: () => request('/api/youtube/reset', { method: 'POST' }),
  /** Казино: TikTok-каналы + health для сайдбара YouTube */
  fetchCasinoHealth: () => request('/api/casino/health'),
  fetchYoutubeChannelsList: (profile = 'primary') =>
    request(`/api/youtube/channels?profile=${encodeURIComponent(profile)}`),
  fetchSocialChannels: () => request('/api/social/channels'),
  fetchSocialChannel: (id) => request(`/api/social/channels/${encodeURIComponent(id)}`),
  createSocialChannel: (body) =>
    request('/api/social/channels', { method: 'POST', body: JSON.stringify(body) }),
  cancelSocialChannel: (id) =>
    request(`/api/social/channels/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),
  startSocialChannel: (id) =>
    request(`/api/social/channels/${encodeURIComponent(id)}/start`, { method: 'POST' }),
  deleteSocialChannel: (id, wipe) =>
    request(
      `/api/social/channels/${encodeURIComponent(id)}${wipe ? '?wipe=true' : ''}`,
      { method: 'DELETE' },
    ),
};

/** URL для <video src> — скачанный ролик канала (Range). */
export function socialVideoFileUrl(channelId, videoKey) {
  const path = `/api/social/channels/${encodeURIComponent(channelId)}/videos/${encodeURIComponent(videoKey)}/file`;
  return `${BASE}${path}`;
}

/** Subscribe to SSE log stream. Returns cleanup function. */
export function subscribeToStream(sessionId, onMessage, onDone, onError, options = {}) {
  const maxReconnectAttempts = Number.isFinite(options?.maxReconnectAttempts) ? options.maxReconnectAttempts : 4;
  const reconnectBaseMs = Number.isFinite(options?.reconnectBaseMs) ? options.reconnectBaseMs : 1200;
  let es = null;
  let closed = false;
  let reconnectAttempts = 0;
  let reconnectTimer = null;

  const finish = () => {
    closed = true;
    try {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = null;
      if (es) es.close();
    } catch {/* ignore */}
  };

  const connect = () => {
    if (closed) return;
    es = new EventSource(`${BASE}/api/pipeline/${sessionId}/stream`);

    es.onopen = () => {
      reconnectAttempts = 0;
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
      try {
        es.close();
      } catch {/* ignore */}
      if (reconnectAttempts >= maxReconnectAttempts) {
        finish();
        onError('Connection lost, switched to polling mode');
        return;
      }
      const delay = reconnectBaseMs * (2 ** reconnectAttempts);
      reconnectAttempts += 1;
      reconnectTimer = setTimeout(connect, delay);
      onError(`Connection lost, reconnecting (${reconnectAttempts}/${maxReconnectAttempts})...`);
    };
  };
  connect();

  return () => {
    finish();
  };
}
