import { useEffect, useState, useMemo, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RiArrowLeftLine,
  RiDownloadLine,
  RiVideoLine,
  RiCheckboxCircleLine,
  RiPauseLine,
  RiPlayLine,
  RiStopLine,
  RiRestartLine,
  RiFileTextLine,
  RiFileCopyLine,
  RiCheckLine,
} from 'react-icons/ri';
import { subscribeToStream, api } from '../services/api';
import LogConsole from '../components/LogConsole';
import StepIndicator from '../components/StepIndicator';

const MAX_LOG_LINES = 1200;

const MODE_LABELS = {
  1: '5 фактов',
  2: 'Почему X?',
  3: 'Реставрация',
  4: 'Цитата',
  5: 'Long-form',
  6: 'Релакс',
  7: '2 клипа',
  8: 'Было→стало',
  12: 'Цитата',
  13: 'Аудио→слайды',
};

/** RU/EN вложенно или плоский объект (title/description/tags) */
function resolvePublishingMeta(p) {
  if (!p || typeof p !== 'object') return null;
  if (p.title != null && p.description != null && !p.ru && !p.en) return p;
  if (p.ru && typeof p.ru === 'object') return p.ru;
  if (p.en && typeof p.en === 'object') return p.en;
  return null;
}

function publicVideoPath(p) {
  const norm = String(p || '').replace(/\\/g, '/').trim();
  if (!norm) return '';
  const clipMatch = norm.match(/(?:^|\/)(clips\/[^/]+\.mp4)$/i);
  const publicPath = clipMatch?.[1] || norm.split('/').filter(Boolean).pop() || '';
  return publicPath.split('/').filter(Boolean).map(encodeURIComponent).join('/');
}

function downloadTextFile(filename, text) {
  if (text == null || text === '') return;
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function mode4SavedTrimForIndex(trims, idx) {
  if (!Array.isArray(trims)) return null;
  const row = trims.find((t) => Number(t?.index) === idx);
  if (!row || !Number.isFinite(Number(row.start_sec)) || !Number.isFinite(Number(row.end_sec))) return null;
  return { start: Number(row.start_sec), end: Number(row.end_sec) };
}

function mode4IsNearlyFullTrim(start, end, duration) {
  if (!Number.isFinite(duration) || duration <= 0.2) return true;
  const s = Number.isFinite(start) ? start : 0;
  const e = Number.isFinite(end) ? end : duration;
  return s <= 0.02 && e >= duration - 0.02;
}

export default function Progress() {
  const { sid } = useParams();
  const navigate = useNavigate();

  const [logs, setLogs]   = useState([]);
  const [done, setDone]   = useState(null);   // result object
  const [error, setError] = useState('');
  const [status, setStatus] = useState('running');  // running | paused | cancelled | error
  const [busy, setBusy]   = useState(false);
  const [sessionTopic, setSessionTopic] = useState('');
  const [sessionMode, setSessionMode] = useState(1);
  const [copied, setCopied] = useState('');
  const [clipVersion, setClipVersion] = useState(0);
  const [mode4AssemblyBusy, setMode4AssemblyBusy] = useState(false);
  const [mode4AssemblySubs, setMode4AssemblySubs] = useState(true);
  const [mode4RegenIdx, setMode4RegenIdx] = useState(null);
  const [mode4TrimDrafts, setMode4TrimDrafts] = useState({});
  const [mode4TrimSavingIdx, setMode4TrimSavingIdx] = useState(null);
  /** Индекс клипа, для которого видео зациклено только на выбранном диапазоне (превью «как в монтаже»). */
  const [mode4TrimPreviewIdx, setMode4TrimPreviewIdx] = useState(null);
  const mode4TrimVideoRefs = useRef({});
  const [mode13AssemblyBusy, setMode13AssemblyBusy] = useState(false);
  const [mode13AssemblySubs, setMode13AssemblySubs] = useState(true);
  const [mode13RegenKey, setMode13RegenKey] = useState(null);
  const [mode5AssemblyBusy, setMode5AssemblyBusy] = useState(false);
  const [mode5RegenImageKey, setMode5RegenImageKey] = useState(null);
  const [mode5RegenChunkIdx, setMode5RegenChunkIdx] = useState(null);
  const [mode5ChunkDrafts, setMode5ChunkDrafts] = useState({});
  const [mode5Live, setMode5Live] = useState(null);
  const [mode5WaitUi, setMode5WaitUi] = useState(null);
  const [mode5ContinueBusy, setMode5ContinueBusy] = useState(false);
  const [mode5LiveActionKey, setMode5LiveActionKey] = useState('');
  const [mode5PolicyNote, setMode5PolicyNote] = useState('');
  const [streamNonce, setStreamNonce] = useState(0);
  const errorRef = useRef('');
  const isTransientReconnectError = useMemo(
    () => /reconnecting|connection lost/i.test(String(error || '')),
    [error],
  );
  const applyMode5Snapshot = (snap) => {
    if (!snap || typeof snap !== 'object') return;
    const normalized = { ...snap, session_id: snap.session_id || sid };
    setMode5Live(normalized);
    setDone((prev) => {
      if (!prev) return normalized;
      if (prev?.mode5_review_ready || normalized?.mode5_review_ready || prev?.mode === 5 || normalized?.mode5_sub_mode) {
        return { ...prev, ...normalized };
      }
      return prev;
    });
  };

  useEffect(() => {
    setStreamNonce(0);
  }, [sid]);

  useEffect(() => {
    const fullSessionReset = streamNonce === 0;
    if (fullSessionReset) {
      setLogs([]);
      setDone(null);
      setError('');
      setStatus('running');
      setBusy(false);
      setSessionTopic('');
      setSessionMode(1);
      setCopied('');
      setClipVersion(0);
      setMode4AssemblyBusy(false);
      setMode4RegenIdx(null);
      setMode4AssemblySubs(true);
      setMode4TrimDrafts({});
      setMode4TrimSavingIdx(null);
      setMode4TrimPreviewIdx(null);
      mode4TrimVideoRefs.current = {};
      setMode13AssemblyBusy(false);
      setMode13AssemblySubs(true);
      setMode13RegenKey(null);
      setMode5AssemblyBusy(false);
      setMode5RegenImageKey(null);
      setMode5RegenChunkIdx(null);
      setMode5ChunkDrafts({});
      setMode5Live(null);
      setMode5WaitUi(null);
      setMode5ContinueBusy(false);
      setMode5LiveActionKey('');
      setMode5PolicyNote('');
    }

    let cancelled = false;

    (async () => {
      try {
        const r = await api.getPipelineStatus(sid);
        if (cancelled) return;
        setStatus(r.status || 'running');
        setSessionTopic(r.topic || '');
        setSessionMode(typeof r.mode === 'number' ? r.mode : 1);
        if (r.status === 'done' && r.result) {
          setDone({ ...r.result, session_id: r.result.session_id || sid });
        } else if (r.status === 'error' && r.error) {
          setError(r.error);
          if (r.result && typeof r.result === 'object') {
            setDone({ ...r.result, session_id: r.result.session_id || sid });
          }
        } else if (r.status === 'cancelled') {
          setStatus('cancelled');
          setError(r.error || 'Генерация отменена');
          if (r.result && typeof r.result === 'object') {
            setDone({ ...r.result, session_id: r.result.session_id || sid });
          }
        }
      } catch (e) {
        if (!cancelled) {
          setStatus('error');
          setError(e.message || 'Сессия не найдена на сервере');
        }
      }
    })();

    const cleanup = subscribeToStream(
      sid,
      (entry) => {
        if (!cancelled) {
          if (String(errorRef.current || '').toLowerCase().includes('reconnecting')) {
            setError('');
          }
          setLogs((prev) => {
            const next = [...prev, entry];
            return next.length > MAX_LOG_LINES ? next.slice(-MAX_LOG_LINES) : next;
          });
        }
      },
      (result) => {
        if (!cancelled) {
          setDone({ ...result, session_id: result.session_id || sid });
          setStatus('done');
        }
      },
      (err) => {
        if (!cancelled) {
          const msg = String(err || '');
          const low = msg.toLowerCase();
          if (low.includes('reconnecting') || low.includes('polling mode')) {
            setError(msg);
            return;
          }
          setError(msg);
          setStatus('error');
        }
      },
      { maxReconnectAttempts: 6, reconnectBaseMs: 1000 },
    );

    return () => {
      cancelled = true;
      cleanup();
    };
  }, [sid, streamNonce]);

  useEffect(() => {
    if (done?.mode5_review_ready || done?.video_path) setMode5WaitUi(null);
  }, [done?.mode5_review_ready, done?.video_path]);

  // Live incremental Mode 5 review: show new previews while generation is still running.
  useEffect(() => {
    const pollMode5Partial =
      sessionMode === 5 &&
      !done?.video_path &&
      (
        status === 'running' ||
        status === 'paused' ||
        ((status === 'error' || status === 'cancelled') && done?.mode5_can_resume === true)
      );
    if (!pollMode5Partial) return;
    let cancelled = false;
    let timer = null;
    const tick = async () => {
      try {
        const snap = await api.mode5ReviewState(sid);
        if (cancelled) return;
        const hintRaw = snap?.mode5_progress_hint;
        const hint = typeof hintRaw === 'string' ? hintRaw.trim() : '';
        if (hint) {
          setMode5WaitUi({
            hint,
            segmentsImaged: snap?.mode5_segments_imaged,
            segmentsTotal: snap?.mode5_segments_total,
            chunksImaged: snap?.mode5_chunks_imaged,
            chunksWithSegs: snap?.mode5_chunks_with_segments,
          });
        } else if (!snap?.mode5_plan_pending) {
          setMode5WaitUi(null);
        }
        if (Array.isArray(snap?.mode5_clip_filenames) && snap.mode5_clip_filenames.length > 0) {
          applyMode5Snapshot(snap);
          setSessionMode(5);
          if (snap?.topic) {
            setSessionTopic((prev) => prev || String(snap.topic));
          }
        }
      } catch (_e) {
        // no-op: endpoint may be unavailable before plan is created
      } finally {
        if (
          !cancelled &&
          (status === 'running' ||
            status === 'paused' ||
            ((status === 'error' || status === 'cancelled') && done?.mode5_can_resume === true))
        ) {
          timer = setTimeout(tick, 2500);
        }
      }
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [sid, status, done?.mode5_can_resume, done?.video_path, sessionMode]);

  // Video URL(s) from result — один файл или несколько (Mode 4 bilingual)
  const videoUrls = useMemo(() => {
    if (!done) return [];
    
    const base = done.session_id || sid;
    let paths =
      done.video_paths && done.video_paths.length > 0
        ? done.video_paths
        : done.video_path
          ? [done.video_path]
          : [];
    if (done.mode13_review_ready && Array.isArray(done.mode13_clip_filenames) && done.mode13_clip_filenames.length > 0) {
      paths = done.mode13_clip_filenames;
    }
    if (done.mode5_review_ready && Array.isArray(done.mode5_clip_filenames) && done.mode5_clip_filenames.length > 0) {
      paths = done.mode5_clip_filenames;
    }

    if (paths.length === 0 && !done.mode4_multiclip_ready && !done.mode13_review_ready && !done.mode5_review_ready) {
      console.warn('[Progress] No video paths found in result:', done);
    }

    const prefix = import.meta.env.VITE_API_URL || '';
    return paths.map((p, idx) => {
      const urlPath = publicVideoPath(p);
      const label =
        (p || '').includes('video_ru') ? 'RU' : (p || '').includes('video_en') ? 'EN'
        : (p || '').includes('mode13_preview_') || (p || '').includes('mode5_preview_')
          ? done.mode5_sub_mode === 'facts50'
            ? `Fact ${idx + 1}`
            : done.mode5_sub_mode === 'unwritten_chapter'
              ? `Блок ${idx + 1}`
            : done.mode5_sub_mode === 'outline' || done.mode5_sub_mode === 'book_night'
              ? `Подглава ${idx + 1}`
              : `Часть ${idx + 1}`
          : null;
      return {
        url: `${prefix}/api/video/${base}/${urlPath}`,
        label,
      };
    });
  }, [done, sid]);

  const mode5ReviewData = done?.mode5_review_ready ? done : mode5Live;

  useEffect(() => {
    errorRef.current = error || '';
  }, [error]);

  useEffect(() => {
    if (done?.mode4_multiclip_ready && typeof done.mode4_show_subtitles === 'boolean') {
      setMode4AssemblySubs(done.mode4_show_subtitles);
    }
  }, [done?.mode4_multiclip_ready, done?.mode4_show_subtitles, done?.session_id]);

  useEffect(() => {
    if (done?.mode13_review_ready && typeof done.mode13_show_subtitles === 'boolean') {
      setMode13AssemblySubs(done.mode13_show_subtitles);
    }
  }, [done?.mode13_review_ready, done?.mode13_show_subtitles, done?.session_id]);

  useEffect(() => {
    if (!mode5ReviewData?.mode5_review_ready || !Array.isArray(mode5ReviewData.mode5_chunks_meta)) return;
    setMode5ChunkDrafts((prev) => {
      const next = { ...prev };
      mode5ReviewData.mode5_chunks_meta.forEach((chunk) => {
        const idx = chunk?.index;
        if (Number.isInteger(idx) && next[idx] == null) next[idx] = chunk?.text || '';
      });
      return next;
    });
  }, [mode5ReviewData?.mode5_review_ready, mode5ReviewData?.mode5_chunks_meta, mode5ReviewData?.session_id]);

  const mode4ClipReview = useMemo(() => {
    if (!done?.mode4_multiclip_ready || !Array.isArray(done.mode4_clip_filenames)) return [];
    const base = done.session_id || sid;
    const prefix = import.meta.env.VITE_API_URL || '';
    return done.mode4_clip_filenames.map((fname, i) => ({
      fname,
      index: i,
      url: `${prefix}/api/video/${base}/${fname}?v=${clipVersion}`,
      text: Array.isArray(done.mode4_segments) ? done.mode4_segments[i] : '',
    }));
  }, [done, sid, clipVersion]);
  useEffect(() => {
    if (!done?.mode4_multiclip_ready || !Array.isArray(done.mode4_clip_filenames)) return;
    const trims = Array.isArray(done.mode4_clip_trims) ? done.mode4_clip_trims : [];
    const byIndex = {};
    trims.forEach((row) => {
      const idx = Number(row?.index);
      if (!Number.isInteger(idx) || idx < 0) return;
      const s = Number(row?.start_sec);
      const e = Number(row?.end_sec);
      if (!Number.isFinite(s) || !Number.isFinite(e) || e <= s) return;
      byIndex[idx] = { startSec: s, endSec: e };
    });
    setMode4TrimDrafts((prev) => {
      const next = { ...prev };
      done.mode4_clip_filenames.forEach((_fname, idx) => {
        const fromPlan = byIndex[idx];
        if (fromPlan) {
          next[idx] = { ...(next[idx] || {}), ...fromPlan };
        }
      });
      return next;
    });
  }, [done?.mode4_multiclip_ready, done?.mode4_clip_filenames, done?.mode4_clip_trims, done?.session_id]);
  const publishMeta = useMemo(() => resolvePublishingMeta(done?.publishing), [done?.publishing]);

  // Copy to clipboard helper
  const copyToClipboard = async (text, field) => {
    if (text == null || String(text).trim() === '') return;
    try {
      await navigator.clipboard.writeText(String(text));
      setCopied(field);
      setTimeout(() => setCopied(''), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const showPublishingMetadata =
    Boolean(done?.publishing) &&
    videoUrls.length > 0 &&
    !done?.mode4_multiclip_ready &&
    !done?.mode13_review_ready &&
    !done?.mode5_review_ready;

  const mode5HasAnyClip =
    (Array.isArray(done?.mode5_clip_filenames) && done.mode5_clip_filenames.length > 0) ||
    (Array.isArray(mode5Live?.mode5_clip_filenames) && mode5Live.mode5_clip_filenames.length > 0);
  const showMode5WaitBanner =
    Boolean(mode5WaitUi?.hint) &&
    sessionMode === 5 &&
    !mode5HasAnyClip &&
    !done?.video_path &&
    (status === 'running' ||
      status === 'paused' ||
      ((status === 'error' || status === 'cancelled') && done?.mode5_can_resume === true));
  const mode5ImageProgressPercent =
    Number.isFinite(mode5WaitUi?.segmentsTotal) &&
    mode5WaitUi.segmentsTotal > 0 &&
    Number.isFinite(mode5WaitUi?.segmentsImaged)
      ? Math.max(0, Math.min(100, Math.round((mode5WaitUi.segmentsImaged / mode5WaitUi.segmentsTotal) * 100)))
      : null;
  const mode5EtaMin =
    mode5ImageProgressPercent != null && mode5ImageProgressPercent > 0 && mode5ImageProgressPercent < 100
      ? Math.max(1, Math.round(((100 - mode5ImageProgressPercent) / mode5ImageProgressPercent) * 8))
      : null;

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      {/* Back */}
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-1.5 text-[#71717a] hover:text-[#e4e4f0] text-sm mb-6 transition-colors"
      >
        <RiArrowLeftLine /> Назад
      </button>

      {/* Title */}
      <div className="mb-6">
        <div className="mb-4 p-3 rounded-xl bg-[#14141c] border border-[#27272f]">
          <p className="text-[10px] font-semibold text-brand-400/90 uppercase tracking-wider mb-1">
            Сейчас на экране
          </p>
          <p className="text-sm text-[#e4e4f0] font-medium leading-snug line-clamp-4">
            {sessionTopic || (done?.topic) || 'Загрузка описания…'}
          </p>
          <p className="text-xs text-[#71717a] mt-1.5 flex flex-wrap items-center gap-x-1">
            <span>Режим:</span>
            <span className="text-[#a1a1aa]">{MODE_LABELS[sessionMode] ?? sessionMode}</span>
            <span className="text-[#3f3f46]">·</span>
            <span className="font-mono text-[#52525b]">session …{sid?.slice(-8)}</span>
          </p>
        </div>
        {showMode5WaitBanner && (
          <div className="mb-4 p-3 rounded-xl bg-[#1a1810] border border-amber-500/25">
            <p className="text-sm text-amber-100/95 leading-relaxed">{mode5WaitUi.hint}</p>
            {Number.isFinite(mode5WaitUi.segmentsTotal) &&
              mode5WaitUi.segmentsTotal > 0 &&
              Number.isFinite(mode5WaitUi.segmentsImaged) && (
                <p className="text-xs text-[#a1a1aa] mt-1.5">
                  Кадры на диске: {mode5WaitUi.segmentsImaged} / {mode5WaitUi.segmentsTotal}
                  {mode5ImageProgressPercent != null ? <> · {mode5ImageProgressPercent}%</> : null}
                  {mode5EtaMin != null ? <> · ETA ~{mode5EtaMin} мин</> : null}
                  {Number.isFinite(mode5WaitUi.chunksWithSegs) && mode5WaitUi.chunksWithSegs > 0 ? (
                    <>
                      {' '}
                      · частей полностью: {mode5WaitUi.chunksImaged ?? 0} / {mode5WaitUi.chunksWithSegs}
                    </>
                  ) : null}
                </p>
              )}
          </div>
        )}
        <h1 className="text-xl font-bold text-white">
          {done
            ? done.mode4_multiclip_ready || done.mode5_review_ready
              ? 'Фрагменты готовы'
              : '🎉 Видео готово!'
            : status === 'cancelled'
              ? '⏹️ Остановлено'
              : error
                ? '❌ Ошибка'
                : status === 'paused'
                  ? '⏸️ На паузе'
                  : '⚙️ Генерация...'}
        </h1>
        {!done?.quote_caption_ru && !done?.quote_caption_en && (done?.quote_caption || done?.topic) && (
          <div className="flex gap-2 items-start mt-1">
            <p className="text-[#d4d4d8] text-sm leading-relaxed whitespace-pre-wrap flex-1 min-w-0">
              {done.quote_caption || done.topic}
            </p>
            <button
              type="button"
              onClick={() => copyToClipboard(done.quote_caption || done.topic, 'quote_single')}
              className="shrink-0 p-2 rounded-lg border border-[#27272f] text-[#71717a] hover:text-white hover:border-[#3f3f46] transition-colors"
              title="Копировать цитату"
            >
              {copied === 'quote_single' ? (
                <RiCheckLine className="text-emerald-400 text-lg" />
              ) : (
                <RiFileCopyLine className="text-lg" />
              )}
            </button>
          </div>
        )}
      </div>

      {/* Pause / Resume / Cancel */}
      {!done && (!error || isTransientReconnectError) && status !== 'cancelled' && (
        <div className="flex gap-2 mb-4">
          {status === 'running' && (
            <button
              onClick={async () => {
                setBusy(true);
                try {
                  await api.pausePipeline(sid);
                  setStatus('paused');
                } catch (e) { setError(e.message); }
                finally { setBusy(false); }
              }}
              disabled={busy}
              className="btn-secondary flex items-center gap-2 text-sm"
            >
              <RiPauseLine /> Пауза
            </button>
          )}
          {status === 'paused' && (
            <button
              onClick={async () => {
                setBusy(true);
                try {
                  await api.resumePipeline(sid);
                  setStatus('running');
                } catch (e) { setError(e.message); }
                finally { setBusy(false); }
              }}
              disabled={busy}
              className="btn-primary flex items-center gap-2 text-sm"
            >
              <RiPlayLine /> Продолжить
            </button>
          )}
          <button
            onClick={async () => {
              setBusy(true);
              try {
                await api.cancelPipeline(sid);
                setStatus('cancelled');
                setError('Генерация отменена');
              } catch (e) { setError(e.message); }
              finally { setBusy(false); }
            }}
            disabled={busy || status === 'cancelled'}
            className="px-4 py-2 rounded-xl border border-red-800/40 text-red-400 hover:bg-red-900/20 text-sm font-medium transition-colors disabled:opacity-50"
          >
            <RiStopLine /> Отменить
          </button>
        </div>
      )}

      {/* Step indicator */}
      <div className="card p-5 mb-4">
        <StepIndicator logs={logs} done={!!done} error={!!error} />
      </div>

      {/* Error banner */}
      {error && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="mb-4 p-4 rounded-xl bg-red-900/20 border border-red-800/40 text-red-400 text-sm font-mono"
        >
          {error}
        </motion.div>
      )}

      {/* Перезапуск / перегенерация — при готовом ролике или ошибке (те же параметры, новая сессия) */}
      {(done || error) && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className={`card p-4 mb-4 ${error ? 'border-amber-800/35 bg-amber-950/10' : ''}`}
        >
          {error && (
            <p className="text-sm text-[#d4d4d8] mb-3 leading-relaxed">
              Повторите запуск с тем же аудио и настройками — как перегенерация в других режимах. Если файл аудио удалён,
              загрузите его снова на странице «Создать».
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {done?.mode5_can_resume === true && !done?.mode5_review_ready && !done?.video_path && (
              <button
                type="button"
                onClick={async () => {
                  setMode5ContinueBusy(true);
                  try {
                    await api.mode5ContinueGeneration(sid);
                    setError('');
                    setStatus('running');
                    setStreamNonce((n) => n + 1);
                  } catch (e) {
                    setError(e.message || String(e));
                  } finally {
                    setMode5ContinueBusy(false);
                  }
                }}
                disabled={mode5ContinueBusy || busy}
                className="flex items-center gap-2 text-sm px-4 py-2.5 rounded-xl font-medium transition-colors bg-emerald-700 hover:bg-emerald-600 text-white border border-emerald-500/40 disabled:opacity-50"
              >
                <RiPlayLine /> Продолжить с сохранённого этапа
              </button>
            )}
            <button
              onClick={async () => {
                setBusy(true);
                try {
                  const res = await api.restartPipeline(sid);
                  navigate(`/run/${res.session_id}`, { replace: true });
                } catch (e) {
                  setError(e.message || 'Не удалось перезапустить');
                } finally {
                  setBusy(false);
                }
              }}
              disabled={busy}
              className={`flex items-center gap-2 text-sm px-4 py-2.5 rounded-xl font-medium transition-colors ${
                error
                  ? 'bg-brand-600 hover:bg-brand-500 text-white border border-brand-500/40 disabled:opacity-50'
                  : 'btn-secondary'
              }`}
            >
              <RiRestartLine /> Перезапустить с теми же параметрами
            </button>
            <button
              type="button"
              onClick={() => navigate('/history')}
              className="btn-secondary flex items-center gap-2 text-sm"
            >
              <RiVideoLine /> Видео
            </button>
            <button
              type="button"
              onClick={() => navigate('/')}
              className="btn-secondary flex items-center gap-2 text-sm"
            >
              + Создать ещё
            </button>
          </div>
        </motion.div>
      )}

      {/* Mode 13 — превью по ~5 мин, перегенерация 30-с сегментов */}
      <AnimatePresence>
        {mode5ReviewData && mode5ReviewData.mode5_review_ready && Array.isArray(mode5ReviewData.mode5_clip_filenames) && mode5ReviewData.mode5_clip_filenames.length > 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            className="card overflow-hidden mb-4"
          >
            <div className="p-4 border-b border-[#27272f] flex items-center gap-2">
              <RiCheckboxCircleLine className="text-emerald-400 text-xl" />
              <span className="text-sm font-semibold text-white">
                {mode5ReviewData.mode5_sub_mode === 'facts50'
                  ? 'Проверка 77 фактов'
                  : mode5ReviewData.mode5_sub_mode === 'outline'
                    ? 'Проверка по плану (от вашего описания)'
                    : mode5ReviewData.mode5_sub_mode === 'book_night'
                      ? 'Проверка «книга на ночь»'
                    : mode5ReviewData.mode5_sub_mode === 'unwritten_chapter'
                      ? 'Проверка The Unwritten Chapter'
                      : 'Проверка long-form частей'}
              </span>
            </div>
            <p className="px-4 pt-3 text-sm text-[#a1a1aa] leading-relaxed">
              {mode5ReviewData.mode5_sub_mode === 'facts50'
                ? 'На каждом клипе сверху — подпись Fact 1, Fact 2, … (латиница). Ниже — превью по одному факту: можно править текст, переозвучить фрагмент или перегенерировать кадр. Финальный ролик — кнопкой «Финальный монтаж» (склейка всех превью по порядку).'
                : mode5ReviewData.mode5_sub_mode === 'outline'
                  ? 'Каждое превью — одна подглава плана, собранного из вашего краткого описания (обычно 10–18 частей); внутри блока — длинный текст, в духе истории на ночь. Можно править, переозвучить или перегенерировать кадры. Финальная склейка — кнопкой ниже.'
                  : mode5ReviewData.mode5_sub_mode === 'book_night'
                    ? 'Каждое превью — одна подглава по оглавлению выбранной книги. Спокойный ночной текст: чем меньше верхних глав в плане, тем длиннее озвучка на подглаву; при большем числе глав блоки короче (ближе к одному клипу «77 фактов»). Заголовок — глава и подраздел. Можно править, переозвучить или перегенерировать кадры. Финальная склейка — кнопкой ниже.'
                    : mode5ReviewData.mode5_sub_mode === 'unwritten_chapter'
                      ? 'Каждое превью — один блок расследования в стиле The Unwritten Chapter: спокойная подача, архивная логика, микровывод и переход. Можно править текст, переозвучить блок или перегенерировать отдельные кадры. Финальная склейка — кнопкой ниже.'
                    : 'Каждое превью — отдельный примерно 5-минутный фрагмент. Можно изменить текст чанка и заново озвучить только его, либо перегенерировать любой отдельный кадр внутри этого чанка. Финальная склейка — кнопкой ниже.'}
            </p>
            {Number.isFinite(mode5ReviewData?.mode5_ready_chunks) && Number.isFinite(mode5ReviewData?.mode5_total_chunks) && (
              <p className="px-4 text-xs text-[#71717a]">
                Готово фрагментов: {mode5ReviewData.mode5_ready_chunks} из {mode5ReviewData.mode5_total_chunks}
              </p>
            )}
            <div className="px-4 pb-2">
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={mode5AssemblyBusy}
                  onClick={async () => {
                    setMode5AssemblyBusy(true);
                    setError('');
                    try {
                      const res = await api.mode5Assemble(sid);
                      setDone({ ...res, session_id: res.session_id || sid });
                      setMode5Live(null);
                      setMode5WaitUi(null);
                    } catch (e) {
                      setError(e.message || 'Финальный монтаж не удался');
                    } finally {
                      setMode5AssemblyBusy(false);
                    }
                  }}
                  className="btn-primary flex items-center justify-center gap-2 text-sm font-semibold py-3 w-full"
                >
                  {mode5AssemblyBusy ? 'Монтаж…' : 'Финальный монтаж (склеить все части)'}
                </button>
                <button
                  type="button"
                  disabled={mode5LiveActionKey === 'rebuild-final'}
                  onClick={async () => {
                    setMode5LiveActionKey('rebuild-final');
                    setError('');
                    try {
                      const res = await api.mode5LiveRebuildFinal(sid);
                      setDone({ ...res, session_id: res.session_id || sid });
                      if (res?.policy_decision) setMode5PolicyNote(`Policy: ${res.policy_decision}`);
                    } catch (e) {
                      setError(e.message || 'Live пересборка финала не удалась');
                    } finally {
                      setMode5LiveActionKey('');
                    }
                  }}
                  className="btn-secondary text-sm py-3 px-3"
                >
                  Live Rebuild Final
                </button>
              </div>
              {mode5PolicyNote ? (
                <p className="mt-2 text-xs text-[#71717a]">{mode5PolicyNote}</p>
              ) : null}
            </div>
            {Array.isArray(mode5ReviewData?.mode5_live_events) && mode5ReviewData.mode5_live_events.length > 0 ? (
              <div className="px-4 pb-2">
                <p className="text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-2">Live events</p>
                <div className="max-h-28 overflow-auto text-xs text-[#a1a1aa] space-y-1">
                  {mode5ReviewData.mode5_live_events.slice(-8).reverse().map((ev, i) => (
                    <div key={`${ev?.at || i}-${i}`}>
                      {ev?.event || 'event'}{ev?.chunk_index != null ? ` · chunk ${ev.chunk_index + 1}` : ''}
                      {ev?.segment_index != null ? ` · seg ${ev.segment_index + 1}` : ''}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {Array.isArray(mode5ReviewData?.mode5_live_queue) && mode5ReviewData.mode5_live_queue.length > 0 ? (
              <div className="px-4 pb-2">
                <p className="text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-2">Live queue</p>
                <div className="max-h-32 overflow-auto text-xs text-[#a1a1aa] space-y-1">
                  {mode5ReviewData.mode5_live_queue.slice(-10).reverse().map((row, i) => (
                    <div key={`${row?.action_id || i}-${i}`} className="border border-[#27272f] rounded-md px-2 py-1">
                      <div className="text-[#d4d4d8]">
                        {row?.action || 'action'} · {row?.status || 'unknown'}
                        {row?.payload?.chunk_index != null ? ` · chunk ${Number(row.payload.chunk_index) + 1}` : ''}
                        {row?.payload?.segment_index != null ? ` · seg ${Number(row.payload.segment_index) + 1}` : ''}
                      </div>
                      <div className="text-[#71717a] font-mono">id: {row?.action_id || 'n/a'}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {Array.isArray(mode5ReviewData?.mode5_unfinished_actions) && mode5ReviewData.mode5_unfinished_actions.length > 0 ? (
              <div className="px-4 pb-2">
                <p className="text-xs font-semibold text-amber-400 uppercase tracking-wider mb-2">Needs attention</p>
                <div className="text-xs text-amber-200/90 space-y-1">
                  {mode5ReviewData.mode5_unfinished_actions.slice(0, 8).map((row, i) => (
                    <div key={`${row?.chunk_index ?? i}-${i}`}>
                      chunk {Number(row?.chunk_index ?? 0) + 1} · status {row?.status || 'unknown'}
                      {row?.locked ? ' · locked' : ''}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="p-4 flex flex-col gap-8">
              {mode5ReviewData.mode5_clip_filenames.map((rel, idx) => {
                const base = mode5ReviewData.session_id || sid;
                const prefix = import.meta.env.VITE_API_URL || '';
                const urlPath = publicVideoPath(rel);
                const url = `${prefix}/api/video/${base}/${urlPath}?v=${clipVersion}`;
                const meta = Array.isArray(mode5ReviewData.mode5_chunks_meta) ? mode5ReviewData.mode5_chunks_meta[idx] : null;
                const chunkIndex = meta?.index ?? idx;
                const segments = Array.isArray(meta?.segments) ? meta.segments : [];
                const draftValue = mode5ChunkDrafts[chunkIndex] ?? meta?.text ?? '';
                const queuedActionsForChunk = Array.isArray(mode5ReviewData?.mode5_live_queue)
                  ? mode5ReviewData.mode5_live_queue.filter((row) => Number(row?.payload?.chunk_index) === Number(chunkIndex))
                  : [];
                const lastChunkAction = queuedActionsForChunk.length > 0
                  ? queuedActionsForChunk[queuedActionsForChunk.length - 1]
                  : null;
                const readyForFinal =
                  (meta?.preview_status === 'ready' || !meta?.preview_status) &&
                  !(Array.isArray(mode5ReviewData?.mode5_pending_rebuilds)
                    ? mode5ReviewData.mode5_pending_rebuilds
                    : []).includes(chunkIndex);
                const statusCls =
                  meta?.status === 'ready'
                    ? 'text-emerald-400 border-emerald-500/40'
                    : meta?.status === 'regenerating'
                      ? 'text-amber-300 border-amber-500/40'
                      : meta?.status === 'dirty'
                        ? 'text-orange-300 border-orange-500/40'
                        : meta?.status === 'paused'
                          ? 'text-cyan-300 border-cyan-500/40'
                          : 'text-[#a1a1aa] border-[#3f3f46]';
                const partLabel = mode5ReviewData.mode5_sub_mode === 'facts50' ? 'Fact' : 'Часть';
                const outlineHead =
                  (mode5ReviewData.mode5_sub_mode === 'outline' || mode5ReviewData.mode5_sub_mode === 'book_night' || mode5ReviewData.mode5_sub_mode === 'unwritten_chapter') &&
                  (meta?.chapter_title || meta?.subchapter_title)
                    ? [meta?.chapter_title, meta?.subchapter_title].filter(Boolean).join(' — ')
                    : null;
                return (
                  <div key={idx} className="border border-[#27272f] rounded-xl p-4 bg-[#14141c]/80">
                    <p className="text-xs font-semibold text-brand-400/90 uppercase tracking-wider mb-2 line-clamp-3">
                      {outlineHead || `${partLabel} ${idx + 1}`}
                      {meta?.duration_sec != null ? ` · ~${Math.round(meta.duration_sec)} с` : ''}
                      {segments.length > 0 ? ` · ${segments.length} кадров` : ''}
                    </p>
                    <p className="text-[11px] text-[#71717a] mb-2 flex flex-wrap items-center gap-2">
                      <span className={`px-2 py-0.5 rounded border ${statusCls}`}>{meta?.status || 'pending'}</span>
                      <span>v{meta?.version ?? 1}</span>
                      <span>preview: {meta?.preview_status || 'pending'}</span>
                      <span>
                      {' '}ready_for_final: {readyForFinal ? 'yes' : 'no'} · queued_actions: {queuedActionsForChunk.length}
                      </span>
                    </p>
                    <div className="flex justify-center bg-black p-3 rounded-lg mb-4">
                      <video controls className="max-h-[52vh] rounded-lg shadow-xl" style={{ maxWidth: '300px' }} key={url}>
                        <source src={url} type="video/mp4" />
                      </video>
                    </div>
                    <div className="mb-4">
                      <label className="block text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-2">
                        {mode5ReviewData.mode5_sub_mode === 'facts50'
                          ? 'Текст озвучки этого факта'
                          : mode5ReviewData.mode5_sub_mode === 'outline'
                            ? 'Текст озвучки этой подглавы (развитие от вашего описания)'
                            : mode5ReviewData.mode5_sub_mode === 'book_night'
                              ? 'Текст озвучки этой подглавы (по книге)'
                            : mode5ReviewData.mode5_sub_mode === 'unwritten_chapter'
                              ? 'Текст озвучки этого расследовательского блока'
                              : 'Текст этого чанка'}
                      </label>
                      <textarea
                        className="input text-sm min-h-[140px] leading-relaxed"
                        value={draftValue}
                        onChange={(e) => setMode5ChunkDrafts((prev) => ({ ...prev, [chunkIndex]: e.target.value }))}
                      />
                      <div className="mt-3 flex gap-2">
                        <button
                          type="button"
                          disabled={mode5RegenChunkIdx === chunkIndex || mode5AssemblyBusy}
                          onClick={async () => {
                            setMode5RegenChunkIdx(chunkIndex);
                            setError('');
                            try {
                              const res = await api.mode5RegenerateChunk(sid, chunkIndex, mode5ChunkDrafts[chunkIndex] ?? draftValue);
                              setDone((prev) => {
                                if (!prev || !Array.isArray(prev.mode5_chunks_meta)) return prev;
                                const metas = [...prev.mode5_chunks_meta];
                                if (res?.chunk_meta && chunkIndex >= 0 && chunkIndex < metas.length) metas[chunkIndex] = res.chunk_meta;
                                return { ...prev, mode5_chunks_meta: metas };
                              });
                              setMode5Live((prev) => {
                                if (!prev || !Array.isArray(prev.mode5_chunks_meta)) return prev;
                                const metas = [...prev.mode5_chunks_meta];
                                if (res?.chunk_meta && chunkIndex >= 0 && chunkIndex < metas.length) metas[chunkIndex] = res.chunk_meta;
                                return { ...prev, mode5_chunks_meta: metas };
                              });
                              setClipVersion((v) => v + 1);
                            } catch (e) {
                              setError(e.message || 'Переозвучка чанка не удалась');
                            } finally {
                              setMode5RegenChunkIdx(null);
                            }
                          }}
                          className="btn-primary text-sm"
                        >
                          {mode5RegenChunkIdx === chunkIndex
                            ? 'Переозвучка…'
                            : mode5ReviewData.mode5_sub_mode === 'facts50'
                              ? 'Переозвучить этот факт'
                              : mode5ReviewData.mode5_sub_mode === 'unwritten_chapter'
                                ? 'Переозвучить этот блок'
                              : mode5ReviewData.mode5_sub_mode === 'outline' || mode5ReviewData.mode5_sub_mode === 'book_night'
                                ? 'Переозвучить эту подглаву'
                                : 'Переозвучить этот чанк'}
                        </button>
                        <button
                          type="button"
                          disabled={mode5LiveActionKey === `audio-${chunkIndex}`}
                          className="btn-secondary text-sm"
                          onClick={async () => {
                            setMode5LiveActionKey(`audio-${chunkIndex}`);
                            setError('');
                            try {
                              const res = await api.mode5LiveRegenerateAudio(sid, chunkIndex);
                              if (res?.policy_decision) setMode5PolicyNote(`Policy: ${res.policy_decision}`);
                              const snap = await api.mode5ReviewState(sid).catch(() => null);
                              if (snap) applyMode5Snapshot(snap);
                              setClipVersion((v) => v + 1);
                            } catch (e) {
                              setError(e.message || 'Live переозвучка не удалась');
                            } finally {
                              setMode5LiveActionKey('');
                            }
                          }}
                        >
                          Live Audio
                        </button>
                        <button
                          type="button"
                          disabled={mode5LiveActionKey === `preview-${chunkIndex}`}
                          className="btn-secondary text-sm"
                          onClick={async () => {
                            setMode5LiveActionKey(`preview-${chunkIndex}`);
                            setError('');
                            try {
                              const res = await api.mode5LiveRebuildChunkPreview(sid, chunkIndex);
                              if (res?.policy_decision) setMode5PolicyNote(`Policy: ${res.policy_decision}`);
                              const snap = await api.mode5ReviewState(sid).catch(() => null);
                              if (snap) applyMode5Snapshot(snap);
                              setClipVersion((v) => v + 1);
                            } catch (e) {
                              setError(e.message || 'Live rebuild clip не удался');
                            } finally {
                              setMode5LiveActionKey('');
                            }
                          }}
                        >
                          Rebuild Clip
                        </button>
                        <button
                          type="button"
                          className="btn-secondary text-sm"
                          onClick={async () => {
                            setError('');
                            try {
                              const isLocked = Boolean(meta?.locked);
                              const res = isLocked
                                ? await api.mode5LiveResumeChunk(sid, chunkIndex)
                                : await api.mode5LivePauseChunk(sid, chunkIndex);
                              setMode5PolicyNote(isLocked ? 'Chunk resumed for background pipeline' : 'Chunk paused for live editing');
                              const snap = await api.mode5ReviewState(sid).catch(() => null);
                              if (snap) applyMode5Snapshot(snap);
                              if (res?.chunk_meta) {
                                setMode5Live((prev) => {
                                  if (!prev || !Array.isArray(prev.mode5_chunks_meta)) return prev;
                                  const metas = [...prev.mode5_chunks_meta];
                                  if (chunkIndex >= 0 && chunkIndex < metas.length) metas[chunkIndex] = res.chunk_meta;
                                  return { ...prev, mode5_chunks_meta: metas };
                                });
                              }
                            } catch (e) {
                              setError(e.message || 'Pause/resume chunk failed');
                            }
                          }}
                        >
                          {meta?.locked ? 'Resume Chunk' : 'Pause Chunk'}
                        </button>
                        <button
                          type="button"
                          className="btn-secondary text-sm"
                          disabled={!lastChunkAction || mode5LiveActionKey === `retry-${chunkIndex}`}
                          onClick={async () => {
                            if (!lastChunkAction) return;
                            setMode5LiveActionKey(`retry-${chunkIndex}`);
                            setError('');
                            try {
                              const action = String(lastChunkAction.action || '');
                              if (action === 'regenerate-image') {
                                if (lastChunkAction?.payload?.segment_index == null) {
                                  setError('Retry image action недоступен: не найден segment_index');
                                  return;
                                }
                                await api.mode5LiveRegenerateImage(
                                  sid,
                                  chunkIndex,
                                  Number(lastChunkAction?.payload?.segment_index),
                                );
                              } else if (action === 'regenerate-audio' || action === 'regenerate-chunk') {
                                await api.mode5LiveRegenerateAudio(sid, chunkIndex);
                              } else if (action === 'rebuild-chunk-preview') {
                                await api.mode5LiveRebuildChunkPreview(sid, chunkIndex);
                              } else if (action === 'pause-chunk') {
                                await api.mode5LivePauseChunk(sid, chunkIndex);
                              } else if (action === 'resume-chunk') {
                                await api.mode5LiveResumeChunk(sid, chunkIndex);
                              } else {
                                setError('Для последнего действия retry пока не поддержан');
                                return;
                              }
                              const snap = await api.mode5ReviewState(sid).catch(() => null);
                              if (snap) applyMode5Snapshot(snap);
                              setClipVersion((v) => v + 1);
                            } catch (e) {
                              setError(e.message || 'Retry last action failed');
                            } finally {
                              setMode5LiveActionKey('');
                            }
                          }}
                        >
                          Retry last action
                        </button>
                      </div>
                    </div>
                    {segments.length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {segments.map((seg, si) => {
                          const rk = `${chunkIndex}-${si}`;
                          return (
                            <button
                              key={si}
                              type="button"
                              disabled={mode5RegenImageKey === rk || mode5AssemblyBusy}
                              onClick={async () => {
                                setMode5RegenImageKey(rk);
                                setError('');
                                try {
                                  const res = await api.mode5LiveRegenerateImage(sid, chunkIndex, si);
                                  if (res?.policy_decision) setMode5PolicyNote(`Policy: ${res.policy_decision}`);
                                  const snap = await api.mode5ReviewState(sid).catch(() => null);
                                  if (snap) applyMode5Snapshot(snap);
                                  setClipVersion((v) => v + 1);
                                } catch (e) {
                                  setError(e.message || 'Перегенерация кадра не удалась');
                                } finally {
                                  setMode5RegenImageKey(null);
                                }
                              }}
                              className="btn-secondary text-xs py-1.5 px-2"
                              title={seg?.text || ''}
                            >
                              <RiRestartLine className="inline mr-1" />
                              Кадр {si + 1}
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {done && done.mode13_review_ready && Array.isArray(done.mode13_clip_filenames) && done.mode13_clip_filenames.length > 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            className="card overflow-hidden mb-4"
          >
            <div className="p-4 border-b border-[#27272f] flex items-center gap-2">
              <RiCheckboxCircleLine className="text-cyan-400 text-xl" />
              <span className="text-sm font-semibold text-white">Проверка частей (~5 мин)</span>
            </div>
            <p className="px-4 pt-3 text-sm text-[#a1a1aa] leading-relaxed">
              Каждое видео — фрагмент аудио с картинками, меняющимися каждые ~30 с.
              «Слайд N» перегенерирует только этот 30-с кадр в данной части и обновляет её превью.
            </p>
            <div className="p-4 flex flex-col gap-8">
              {done.mode13_clip_filenames.map((rel, idx) => {
                const base = done.session_id || sid;
                const prefix = import.meta.env.VITE_API_URL || '';
                const urlPath = publicVideoPath(rel);
                const url = `${prefix}/api/video/${base}/${urlPath}?v=${clipVersion}`;
                const meta = Array.isArray(done.mode13_chunks_meta) ? done.mode13_chunks_meta[idx] : null;
                const chunkIndex = meta?.index ?? idx;
                const nSeg = meta?.num_segments ?? 0;
                return (
                  <div key={idx} className="border border-[#27272f] rounded-xl p-4 bg-[#14141c]/80">
                    <p className="text-xs font-semibold text-brand-400/90 uppercase tracking-wider mb-2">
                      Часть {idx + 1}
                      {meta?.duration_sec != null ? ` · ~${Math.round(meta.duration_sec)} с` : ''}
                    </p>
                    <div className="flex justify-center bg-black p-3 rounded-lg mb-3">
                      <video controls className="max-h-[52vh] rounded-lg shadow-xl" style={{ maxWidth: '300px' }} key={url}>
                        <source src={url} type="video/mp4" />
                      </video>
                    </div>
                    {nSeg > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {Array.from({ length: nSeg }, (_, si) => {
                          const rk = `${chunkIndex}-${si}`;
                          return (
                            <button
                              key={si}
                              type="button"
                              disabled={mode13RegenKey === rk || mode13AssemblyBusy}
                              onClick={async () => {
                                setMode13RegenKey(rk);
                                setError('');
                                try {
                                  await api.mode13RegenerateSegment(sid, chunkIndex, si);
                                  setClipVersion((v) => v + 1);
                                } catch (e) {
                                  setError(e.message || 'Перегенерация не удалась');
                                } finally {
                                  setMode13RegenKey(null);
                                }
                              }}
                              className="btn-secondary text-xs py-1.5 px-2"
                            >
                              <RiRestartLine className="inline mr-1" />
                              Слайд {si + 1}
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
            <div className="p-4 border-t border-[#27272f] flex flex-col gap-4">
              <label className="flex items-center gap-2 text-sm text-[#d4d4d8] cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="rounded border-[#3f3f46] bg-[#1a1a24] text-brand-600 focus:ring-brand-500"
                  checked={mode13AssemblySubs}
                  onChange={(e) => setMode13AssemblySubs(e.target.checked)}
                  disabled={mode13AssemblyBusy}
                />
                Субтитры на видео (текст сегмента на слайде)
              </label>
              <p className="text-xs text-[#71717a] -mt-2">
                Если выключить или включить с другим состоянием, чем при генерации, превью пересоберутся перед склейкой.
              </p>
              <button
                type="button"
                disabled={mode13AssemblyBusy}
                onClick={async () => {
                  setMode13AssemblyBusy(true);
                  setError('');
                  try {
                    const res = await api.mode13Assemble(sid, mode13AssemblySubs);
                    setDone({ ...res, session_id: res.session_id || sid });
                  } catch (e) {
                    setError(e.message || 'Монтаж не удался');
                  } finally {
                    setMode13AssemblyBusy(false);
                  }
                }}
                className="btn-primary flex items-center justify-center gap-2 text-sm font-semibold py-3"
              >
                {mode13AssemblyBusy ? 'Монтаж…' : 'Финальный монтаж'}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Mode 4 multiclip — review + assemble */}
      <AnimatePresence>
        {done && done.mode4_multiclip_ready && mode4ClipReview.length > 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            className="card overflow-hidden mb-4"
          >
            <div className="p-4 border-b border-[#27272f] flex items-center gap-2">
              <RiCheckboxCircleLine className="text-amber-400 text-xl" />
              <span className="text-sm font-semibold text-white">Цитата: проверка фрагментов</span>
            </div>
            <p className="px-4 pt-3 text-sm text-[#a1a1aa] leading-relaxed">
              Просмотрите клипы. Обрезку можно сохранить для монтажа, посмотреть в этом же плеере кнопкой «Просмотр как в монтаже» и при необходимости вернуть полный клип. Затем соберите финальный ролик.
            </p>
            <div className="p-4 flex flex-col gap-8">
              {mode4ClipReview.map((row) => (
                <div key={row.index} className="border border-[#27272f] rounded-xl p-4 bg-[#14141c]/80">
                  <p className="text-xs font-semibold text-brand-400/90 uppercase tracking-wider mb-2">
                    Фрагмент {row.index + 1}
                  </p>
                  {row.text ? (
                    <p className="text-sm text-[#d4d4d8] mb-3 whitespace-pre-wrap leading-relaxed">{row.text}</p>
                  ) : null}
                  {(() => {
                    const td0 = mode4TrimDrafts[row.index] || {};
                    const duration0 = Number(td0.durationSec || 0);
                    const start0 = Number.isFinite(td0.startSec) ? td0.startSec : 0;
                    const end0 = Number.isFinite(td0.endSec) ? td0.endSec : duration0;
                    const trimPreviewOn = mode4TrimPreviewIdx === row.index;
                    const savedTrim = mode4SavedTrimForIndex(done?.mode4_clip_trims, row.index);
                    const savedIsTight =
                      savedTrim &&
                      Number.isFinite(duration0) &&
                      duration0 > 0.2 &&
                      !mode4IsNearlyFullTrim(savedTrim.start, savedTrim.end, duration0);

                    return (
                      <>
                        <div className="flex justify-center bg-black p-3 rounded-lg mb-2">
                          <video
                            controls
                            className="max-h-[52vh] rounded-lg shadow-xl"
                            style={{ maxWidth: '300px' }}
                            key={row.url}
                            ref={(el) => {
                              if (el) mode4TrimVideoRefs.current[row.index] = el;
                              else delete mode4TrimVideoRefs.current[row.index];
                            }}
                            onLoadedMetadata={(e) => {
                              const dur = Number(e.currentTarget?.duration || 0);
                              if (!Number.isFinite(dur) || dur <= 0.2) return;
                              setMode4TrimDrafts((prev) => {
                                const cur = prev[row.index] || {};
                                const startSec = Number.isFinite(cur.startSec) ? Math.max(0, Math.min(cur.startSec, dur - 0.12)) : 0;
                                const endSec = Number.isFinite(cur.endSec) ? Math.max(startSec + 0.12, Math.min(cur.endSec, dur)) : dur;
                                return { ...prev, [row.index]: { ...cur, durationSec: dur, startSec, endSec } };
                              });
                            }}
                            onTimeUpdate={(e) => {
                              if (mode4TrimPreviewIdx !== row.index) return;
                              const v = e.currentTarget;
                              const t = mode4TrimDrafts[row.index] || {};
                              const d = Number(t.durationSec || 0);
                              if (!Number.isFinite(d) || d <= 0.2) return;
                              const s = Number.isFinite(t.startSec) ? t.startSec : 0;
                              const en = Number.isFinite(t.endSec) ? t.endSec : d;
                              if (v.currentTime < s) v.currentTime = s;
                              if (v.currentTime >= en - 0.04) v.currentTime = s;
                            }}
                            onSeeking={(e) => {
                              if (mode4TrimPreviewIdx !== row.index) return;
                              const v = e.currentTarget;
                              const t = mode4TrimDrafts[row.index] || {};
                              const d = Number(t.durationSec || 0);
                              if (!Number.isFinite(d) || d <= 0.2) return;
                              const s = Number.isFinite(t.startSec) ? t.startSec : 0;
                              const en = Number.isFinite(t.endSec) ? t.endSec : d;
                              if (v.currentTime < s) v.currentTime = s;
                              if (v.currentTime > en - 0.06) v.currentTime = Math.max(s, en - 0.06);
                            }}
                          >
                            <source src={row.url} type="video/mp4" />
                          </video>
                        </div>
                        {trimPreviewOn && Number.isFinite(duration0) && duration0 > 0.2 ? (
                          <p className="text-xs text-amber-300/95 mb-2">
                            Превью обрезки: зациклен участок {start0.toFixed(2)}–{end0.toFixed(2)} с. «Полный клип» — снова весь файл в плеере.
                          </p>
                        ) : null}
                        {savedIsTight ? (
                          <p className="text-xs text-emerald-400/90 mb-2">
                            В финальный монтаж сохранено: {savedTrim.start.toFixed(2)}–{savedTrim.end.toFixed(2)} с (файл клипа на диске полный; в ролике войдёт только этот кусок).
                          </p>
                        ) : null}
                        {!trimPreviewOn &&
                        Number.isFinite(duration0) &&
                        duration0 > 0.2 &&
                        end0 - start0 < duration0 - 0.06 ? (
                          <p className="text-xs text-[#71717a] mb-2">
                            «Просмотр как в монтаже» — в этом же плеере только выбранный диапазон; «Сохранить обрезку» — записать границы для финала.
                          </p>
                        ) : null}
                      </>
                    );
                  })()}
                  {(() => {
                    const td = mode4TrimDrafts[row.index] || {};
                    const duration = Number(td.durationSec || 0);
                    if (!Number.isFinite(duration) || duration <= 0.2) return null;
                    const startSec = Number.isFinite(td.startSec) ? td.startSec : 0;
                    const endSec = Number.isFinite(td.endSec) ? td.endSec : duration;
                    const minGap = 0.12;
                    const savedTrim = mode4SavedTrimForIndex(done?.mode4_clip_trims, row.index);
                    const savedIsTight =
                      savedTrim && !mode4IsNearlyFullTrim(savedTrim.start, savedTrim.end, duration);

                    return (
                      <div className="mb-3 border border-[#27272f] rounded-lg p-3 bg-[#0f0f16]">
                        <p className="text-xs text-[#a1a1aa] mb-2">Обрезка перед финальным монтажом</p>
                        <div className="grid grid-cols-1 gap-2">
                          <label className="text-xs text-[#a1a1aa]">
                            Старт: {startSec.toFixed(2)}s
                            <input
                              type="range"
                              min={0}
                              max={Math.max(0, duration - minGap)}
                              step={0.01}
                              value={Math.min(startSec, endSec - minGap)}
                              onChange={(e) => {
                                const v = Number(e.target.value);
                                setMode4TrimDrafts((prev) => {
                                  const cur = prev[row.index] || {};
                                  const ee = Number.isFinite(cur.endSec) ? cur.endSec : duration;
                                  return { ...prev, [row.index]: { ...cur, durationSec: duration, startSec: Math.min(v, ee - minGap), endSec: ee } };
                                });
                              }}
                              disabled={mode4AssemblyBusy}
                              className="w-full mt-1"
                            />
                          </label>
                          <label className="text-xs text-[#a1a1aa]">
                            Конец: {endSec.toFixed(2)}s
                            <input
                              type="range"
                              min={minGap}
                              max={duration}
                              step={0.01}
                              value={Math.max(endSec, startSec + minGap)}
                              onChange={(e) => {
                                const v = Number(e.target.value);
                                setMode4TrimDrafts((prev) => {
                                  const cur = prev[row.index] || {};
                                  const ss = Number.isFinite(cur.startSec) ? cur.startSec : 0;
                                  return { ...prev, [row.index]: { ...cur, durationSec: duration, startSec: ss, endSec: Math.max(v, ss + minGap) } };
                                });
                              }}
                              disabled={mode4AssemblyBusy}
                              className="w-full mt-1"
                            />
                          </label>
                        </div>
                        <div className="flex flex-wrap gap-2 mt-2">
                          <button
                            type="button"
                            className="btn-secondary text-xs"
                            disabled={mode4TrimSavingIdx === row.index || mode4AssemblyBusy}
                            onClick={async () => {
                              setMode4TrimSavingIdx(row.index);
                              setError('');
                              try {
                                const res = await api.mode4SetClipTrim(sid, row.index, startSec, endSec);
                                const trims = Array.isArray(res?.clip_trims) ? res.clip_trims : [];
                                setDone((prev) => (prev ? { ...prev, mode4_clip_trims: trims } : prev));
                              } catch (e) {
                                setError(e.message || 'Не удалось сохранить обрезку');
                              } finally {
                                setMode4TrimSavingIdx(null);
                              }
                            }}
                          >
                            {mode4TrimSavingIdx === row.index ? 'Сохраняю…' : 'Сохранить обрезку'}
                          </button>
                          <button
                            type="button"
                            className="btn-secondary text-xs"
                            disabled={mode4AssemblyBusy}
                            onClick={() => {
                              setMode4TrimDrafts((prev) => ({
                                ...prev,
                                [row.index]: { ...td, durationSec: duration, startSec: 0, endSec: duration },
                              }));
                            }}
                          >
                            Сбросить ползунки
                          </button>
                          <button
                            type="button"
                            className="btn-secondary text-xs"
                            disabled={mode4AssemblyBusy || endSec - startSec >= duration - 0.06}
                            onClick={() => {
                              setMode4TrimPreviewIdx(row.index);
                              const v = mode4TrimVideoRefs.current[row.index];
                              if (v && Number.isFinite(duration)) {
                                v.currentTime = Math.min(startSec, duration - 0.12);
                                void v.play().catch(() => {});
                              }
                            }}
                          >
                            Просмотр как в монтаже
                          </button>
                          {mode4TrimPreviewIdx === row.index ? (
                            <button
                              type="button"
                              className="btn-secondary text-xs"
                              disabled={mode4AssemblyBusy}
                              onClick={() => {
                                setMode4TrimPreviewIdx(null);
                                const v = mode4TrimVideoRefs.current[row.index];
                                if (v) {
                                  v.pause();
                                  v.currentTime = 0;
                                }
                              }}
                            >
                              Полный клип
                            </button>
                          ) : null}
                        </div>
                        {savedIsTight ? (
                          <button
                            type="button"
                            className="btn-secondary text-xs mt-2 w-full sm:w-auto"
                            disabled={mode4TrimSavingIdx === row.index || mode4AssemblyBusy}
                            onClick={async () => {
                              setMode4TrimSavingIdx(row.index);
                              setError('');
                              try {
                                const res = await api.mode4ClearClipTrim(sid, row.index);
                                const trims = Array.isArray(res?.clip_trims) ? res.clip_trims : [];
                                setDone((prev) => (prev ? { ...prev, mode4_clip_trims: trims } : prev));
                                setMode4TrimDrafts((prev) => ({
                                  ...prev,
                                  [row.index]: {
                                    ...(prev[row.index] || {}),
                                    durationSec: duration,
                                    startSec: 0,
                                    endSec: duration,
                                  },
                                }));
                                setMode4TrimPreviewIdx((cur) => (cur === row.index ? null : cur));
                              } catch (e) {
                                setError(e.message || 'Не удалось убрать обрезку');
                              } finally {
                                setMode4TrimSavingIdx(null);
                              }
                            }}
                          >
                            Вернуть в монтаж полный клип
                          </button>
                        ) : null}
                      </div>
                    );
                  })()}
                  <button
                    type="button"
                    disabled={mode4RegenIdx === row.index || mode4AssemblyBusy || mode4TrimSavingIdx === row.index}
                    onClick={async () => {
                      setMode4RegenIdx(row.index);
                      setMode4TrimPreviewIdx((cur) => (cur === row.index ? null : cur));
                      setError('');
                      try {
                        await api.mode4RegenerateClip(sid, row.index);
                        setClipVersion((v) => v + 1);
                      } catch (e) {
                        setError(e.message || 'Перегенерация не удалась');
                      } finally {
                        setMode4RegenIdx(null);
                      }
                    }}
                    className="btn-secondary flex items-center gap-2 text-sm"
                  >
                    <RiRestartLine /> Перегенерировать этот фрагмент
                  </button>
                </div>
              ))}
            </div>
            <div className="p-4 border-t border-[#27272f] flex flex-col gap-4">
              <label className="flex items-center gap-2 text-sm text-[#d4d4d8] cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="rounded border-[#3f3f46] bg-[#1a1a24] text-brand-600 focus:ring-brand-500"
                  checked={mode4AssemblySubs}
                  onChange={(e) => setMode4AssemblySubs(e.target.checked)}
                  disabled={mode4AssemblyBusy}
                />
                Субтитры в финальном ролике
              </label>
              <button
                type="button"
                disabled={mode4AssemblyBusy || mode4TrimSavingIdx != null}
                onClick={async () => {
                  setMode4AssemblyBusy(true);
                  setError('');
                  try {
                    const res = await api.mode4Assemble(sid, mode4AssemblySubs);
                    setDone({ ...res, session_id: res.session_id || sid });
                  } catch (e) {
                    setError(e.message || 'Монтаж не удался');
                  } finally {
                    setMode4AssemblyBusy(false);
                  }
                }}
                className="btn-primary flex items-center justify-center gap-2 text-sm font-semibold py-3"
              >
                {mode4AssemblyBusy ? 'Монтаж…' : 'Финальный монтаж'}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Done — video player(s) */}
      <AnimatePresence>
        {done && !done.mode4_multiclip_ready && !done.mode13_review_ready && !done.mode5_review_ready && videoUrls.length > 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            className="card overflow-hidden mb-4"
          >
            <div className="p-4 border-b border-[#27272f] flex items-center gap-2">
              <RiCheckboxCircleLine className="text-emerald-400 text-xl" />
              <span className="text-sm font-semibold text-white">Видео создано</span>
            </div>
            <div className="flex flex-col gap-6 p-4">
              {videoUrls.map(({ url, label }, idx) => (
                <div key={idx} className="flex flex-col gap-2">
                  {label && (
                    <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">{label}</span>
                  )}
                  <div className="flex justify-center bg-black p-4 rounded-lg">
                    <video
                      controls
                      autoPlay={idx === 0}
                      className="max-h-[60vh] rounded-lg shadow-2xl"
                      style={{ maxWidth: '300px' }}
                    >
                      <source src={url} type="video/mp4" />
                    </video>
                  </div>
                  {(() => {
                    const cap =
                      label === 'RU'
                        ? done?.quote_caption_ru
                        : label === 'EN'
                          ? done?.quote_caption_en
                          : done?.quote_caption || done?.quote_caption_ru || done?.topic;
                    if (!cap) return null;
                    const copyKey = label === 'RU' ? 'quote_ru' : label === 'EN' ? 'quote_en' : `quote_${idx}`;
                    return (
                      <div className="flex flex-col items-center gap-2 w-full px-1">
                        <p className="text-[#d4d4d8] text-sm leading-relaxed text-center">{cap}</p>
                        <button
                          type="button"
                          onClick={() => copyToClipboard(cap, copyKey)}
                          className="btn-secondary flex items-center gap-2 text-sm"
                        >
                          {copied === copyKey ? (
                            <RiCheckLine className="text-emerald-400" />
                          ) : (
                            <RiFileCopyLine />
                          )}
                          Копировать цитату
                        </button>
                      </div>
                    );
                  })()}
                  <a
                    href={url}
                    download={`video_${label || idx}.mp4`}
                    className="btn-secondary flex items-center gap-2 text-sm self-start"
                  >
                    <RiDownloadLine /> Скачать {label ? `${label} ` : ''}MP4
                  </a>
                  {label === 'RU' && done?.quote_caption_ru && (
                    <button
                      type="button"
                      onClick={() => downloadTextFile(`quote_caption_ru_${sid?.slice(-8) || 'video'}.txt`, done.quote_caption_ru)}
                      className="btn-secondary flex items-center gap-2 text-sm self-start"
                    >
                      <RiFileTextLine /> Скачать подпись RU (.txt)
                    </button>
                  )}
                  {label === 'EN' && done?.quote_caption_en && (
                    <button
                      type="button"
                      onClick={() => downloadTextFile(`quote_caption_en_${sid?.slice(-8) || 'video'}.txt`, done.quote_caption_en)}
                      className="btn-secondary flex items-center gap-2 text-sm self-start"
                    >
                      <RiFileTextLine /> Скачать подпись EN (.txt)
                    </button>
                  )}
                </div>
              ))}
            </div>
            <div className="p-4 flex flex-wrap gap-3 border-t border-[#27272f]">
              <button
                onClick={async () => {
                  setBusy(true);
                  try {
                    const res = await api.restartPipeline(sid);
                    navigate(`/run/${res.session_id}`, { replace: true });
                  } catch (e) {
                    setError(e.message || 'Не удалось перезапустить');
                  } finally {
                    setBusy(false);
                  }
                }}
                disabled={busy}
                className="btn-secondary flex items-center gap-2 text-sm"
              >
                <RiRestartLine /> Перезапустить
              </button>
              <button
                onClick={() => navigate('/history')}
                className="btn-secondary flex items-center gap-2 text-sm"
              >
                <RiVideoLine /> История
              </button>
              <button
                onClick={() => navigate('/')}
                className="btn-secondary flex items-center gap-2 text-sm"
              >
                + Создать ещё
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Publishing Metadata */}
      <AnimatePresence>
        {showPublishingMetadata && (() => {
          const p = done.publishing;
          const nested = p.ru || p.en;
          const renderBlock = (block, label, prefix) => {
            if (!block) return null;
            return (
              <div key={prefix} className="space-y-4 pt-4 first:pt-0 first:border-0 border-t border-[#27272f]">
                <p className="text-xs font-semibold text-brand-300 uppercase tracking-wider">{label}</p>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Название</span>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(block.title, `${prefix}-title`)}
                      className="text-[#71717a] hover:text-white transition-colors"
                    >
                      {copied === `${prefix}-title` ? <RiCheckLine className="text-emerald-400" /> : <RiFileCopyLine />}
                    </button>
                  </div>
                  <p className="text-white text-sm font-medium">{block.title}</p>
                </div>
                {Array.isArray(block.title_variants) && block.title_variants.length > 0 && (
                  <div className="space-y-2">
                    <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Варианты A/B/C</span>
                    {block.title_variants.map((t, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <span className="text-[10px] text-[#52525b] font-mono w-4 shrink-0 pt-0.5">{String.fromCharCode(65 + i)}</span>
                        <p className="text-[#a1a1aa] text-sm flex-1 min-w-0">{t}</p>
                        <button
                          type="button"
                          onClick={() => copyToClipboard(t, `${prefix}-v${i}`)}
                          className="text-[#71717a] hover:text-white shrink-0"
                        >
                          {copied === `${prefix}-v${i}` ? <RiCheckLine className="text-emerald-400 text-sm" /> : <RiFileCopyLine className="text-sm" />}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Описание</span>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(block.description, `${prefix}-desc`)}
                      className="text-[#71717a] hover:text-white transition-colors"
                    >
                      {copied === `${prefix}-desc` ? <RiCheckLine className="text-emerald-400" /> : <RiFileCopyLine />}
                    </button>
                  </div>
                  <p className="text-[#a1a1aa] text-sm whitespace-pre-wrap">{block.description}</p>
                </div>
                {block.hashtags?.length > 0 && (
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Хештеги</span>
                      <button
                        type="button"
                        onClick={() => copyToClipboard(block.hashtags.join(' '), `${prefix}-hash`)}
                        className="text-[#71717a] hover:text-white transition-colors"
                      >
                        {copied === `${prefix}-hash` ? <RiCheckLine className="text-emerald-400" /> : <RiFileCopyLine />}
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {block.hashtags.map((tag, i) => (
                        <span key={i} className="px-2 py-1 bg-[#27272f] rounded text-xs text-[#a1a1aa]">{tag}</span>
                      ))}
                    </div>
                  </div>
                )}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Теги</span>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(block.tags?.join(', '), `${prefix}-tags`)}
                      className="text-[#71717a] hover:text-white transition-colors"
                    >
                      {copied === `${prefix}-tags` ? <RiCheckLine className="text-emerald-400" /> : <RiFileCopyLine />}
                    </button>
                  </div>
                  <p className="text-[#71717a] text-xs font-mono">{block.tags?.join(', ')}</p>
                </div>
                {block.first_comment ? (
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Первый комментарий</span>
                      <button
                        type="button"
                        onClick={() => copyToClipboard(block.first_comment, `${prefix}-fc`)}
                        className="text-[#71717a] hover:text-white transition-colors"
                      >
                        {copied === `${prefix}-fc` ? <RiCheckLine className="text-emerald-400" /> : <RiFileCopyLine />}
                      </button>
                    </div>
                    <p className="text-[#a1a1aa] text-sm whitespace-pre-wrap">{block.first_comment}</p>
                  </div>
                ) : null}
              </div>
            );
          };
          return (
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              className="card overflow-hidden mb-4"
            >
              <div className="p-4 border-b border-[#27272f] flex items-center gap-2">
                <span className="text-lg">📝</span>
                <span className="text-sm font-semibold text-white">Данные для публикации</span>
              </div>
              <div className="p-4 space-y-2">
                {nested ? (
                  <>
                    {renderBlock(p.ru, '🇷🇺 Русская версия', 'ru')}
                    {renderBlock(p.en, '🇬🇧 English', 'en')}
                  </>
                ) : (
                  <div className="space-y-4">
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Название</span>
                        <button
                          type="button"
                          onClick={() => copyToClipboard(p.title, 'title')}
                          className="text-[#71717a] hover:text-white transition-colors"
                        >
                          {copied === 'title' ? <RiCheckLine className="text-emerald-400" /> : <RiFileCopyLine />}
                        </button>
                      </div>
                      <p className="text-white text-sm font-medium">{p.title}</p>
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Описание</span>
                        <button
                          type="button"
                          onClick={() => copyToClipboard(p.description, 'description')}
                          className="text-[#71717a] hover:text-white transition-colors"
                        >
                          {copied === 'description' ? <RiCheckLine className="text-emerald-400" /> : <RiFileCopyLine />}
                        </button>
                      </div>
                      <p className="text-[#a1a1aa] text-sm">{p.description}</p>
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Хештеги</span>
                        <button
                          type="button"
                          onClick={() => copyToClipboard(p.hashtags?.join(' '), 'hashtags')}
                          className="text-[#71717a] hover:text-white transition-colors"
                        >
                          {copied === 'hashtags' ? <RiCheckLine className="text-emerald-400" /> : <RiFileCopyLine />}
                        </button>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {p.hashtags?.map((tag, i) => (
                          <span key={i} className="px-2 py-1 bg-[#27272f] rounded text-xs text-[#a1a1aa]">{tag}</span>
                        ))}
                      </div>
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Теги (YouTube Studio)</span>
                        <button
                          type="button"
                          onClick={() => copyToClipboard(p.tags?.join(', '), 'tags')}
                          className="text-[#71717a] hover:text-white transition-colors"
                        >
                          {copied === 'tags' ? <RiCheckLine className="text-emerald-400" /> : <RiFileCopyLine />}
                        </button>
                      </div>
                      <p className="text-[#71717a] text-xs font-mono">{p.tags?.join(', ')}</p>
                    </div>
                    {p.first_comment ? (
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-medium text-[#71717a] uppercase tracking-wider">Первый комментарий</span>
                          <button
                            type="button"
                            onClick={() => copyToClipboard(p.first_comment, 'fc')}
                            className="text-[#71717a] hover:text-white transition-colors"
                          >
                            {copied === 'fc' ? <RiCheckLine className="text-emerald-400" /> : <RiFileCopyLine />}
                          </button>
                        </div>
                        <p className="text-[#a1a1aa] text-sm whitespace-pre-wrap">{p.first_comment}</p>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            </motion.div>
          );
        })()}
      </AnimatePresence>

      {/* Log console */}
      <LogConsole logs={logs} className="mb-4" sessionId={sid} />
    </div>
  );
}
