import { useState } from 'react';
import { createPortal } from 'react-dom';
import { RiPlayCircleLine, RiDownloadLine, RiDeleteBinLine, RiFileCopyLine } from 'react-icons/ri';
import { motion } from 'framer-motion';
import { api } from '../services/api';

function formatDate(ts) {
  if (ts == null) return '—';
  const d = new Date(typeof ts === 'number' ? ts * 1000 : ts);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

function quoteCaptionForVideo(v) {
  if (!v) return '';
  const ru = typeof v.quote_caption_ru === 'string' ? v.quote_caption_ru.trim() : '';
  const en = typeof v.quote_caption_en === 'string' ? v.quote_caption_en.trim() : '';
  if (v.video_lang === 'en') return en || ru;
  if (v.video_lang === 'ru') return ru || en;
  return ru || en;
}

export default function VideoCard({ video, onClick, onDelete, youtubeStatus = null, youtubeLoading = false }) {
  const [hovered, setHovered] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showPublishing, setShowPublishing] = useState(false);
  const [ytPrivacy, setYtPrivacy] = useState('public');
  const [ytLang, setYtLang] = useState(() =>
    video?.video_lang === 'ru' ? 'ru' : 'en',
  );
  const [ytBusy, setYtBusy] = useState(false);
  const [ytChannelModal, setYtChannelModal] = useState(false);

  const primaryAuth = Boolean(youtubeStatus?.profiles?.primary?.authorized);
  const secondaryAuth = Boolean(
    youtubeStatus?.has_secondary && youtubeStatus?.profiles?.secondary?.authorized,
  );
  const showYoutubePanel = Boolean(
    youtubeLoading || youtubeStatus?.client_configured,
  );
  const youtubeAnyReady = Boolean(
    !youtubeLoading &&
      youtubeStatus?.client_configured &&
      (primaryAuth || secondaryAuth),
  );
  // Совместимость со старыми чанками / HMR
  const youtubeReady = youtubeAnyReady;

  const base = import.meta.env.VITE_API_URL || '';
  const thumbUrl = video?.thumbnail_url ? base + video.thumbnail_url : null;

  if (!video?.session_id) return null;

  async function runYoutubeUpload(channelProfile) {
    const hasRu = Boolean(video.publishing?.ru);
    const hasEn = Boolean(video.publishing?.en);
    const bilingual = hasRu && hasEn;
    let lang = 'en';
    if (bilingual) lang = ytLang;
    else if (hasEn && !hasRu) lang = 'en';
    else if (hasRu && !hasEn) lang = 'ru';
    else if (video.video_lang === 'ru') lang = 'ru';
    const fn = video.filename || `video_${video.session_id}.mp4`;
    setYtBusy(true);
    try {
      const r = await api.youtubeUpload({
        session_id: video.session_id,
        filename: fn,
        lang,
        privacy_status: ytPrivacy,
        channel_profile: channelProfile,
      });
      const msg = r?.url ? `Залито: ${r.url}` : `video_id: ${r?.video_id || '?'}`;
      alert(msg);
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      setYtBusy(false);
    }
  }

  function handleYoutubeButtonClick(e) {
    e.stopPropagation();
    if (ytBusy || youtubeLoading || !youtubeReady) return;
    if (!youtubeStatus?.has_secondary) {
      runYoutubeUpload('primary');
      return;
    }
    const nAuth = (primaryAuth ? 1 : 0) + (secondaryAuth ? 1 : 0);
    if (nAuth === 1) {
      runYoutubeUpload(primaryAuth ? 'primary' : 'secondary');
      return;
    }
    setYtChannelModal(true);
  }

  async function pickChannelAndUpload(profile) {
    setYtChannelModal(false);
    if (profile === 'primary' && !primaryAuth) return;
    if (profile === 'secondary' && !secondaryAuth) return;
    await runYoutubeUpload(profile);
  }

  async function handleDelete(e) {
    e.stopPropagation();
    if (deleting) return;
    if (!confirm('Удалить видео с компьютера?')) return;
    setDeleting(true);
    try {
      await api.deleteVideo(video.session_id, video.filename);
      onDelete?.(video.session_id, video.filename);
    } catch (err) {
      alert(err.message);
    } finally {
      setDeleting(false);
    }
  }

  // Copy to clipboard helper
  async function copyToClipboard(text, label) {
    try {
      await navigator.clipboard.writeText(text);
      alert(`${label} скопирован в буфер обмена!`);
    } catch (err) {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      alert(`${label} скопирован в буфер обмена!`);
    }
  }

  const channelPickerModal =
    typeof document !== 'undefined' &&
    ytChannelModal &&
    youtubeStatus?.has_secondary &&
    createPortal(
      <div
        className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 p-4"
        role="dialog"
        aria-modal="true"
        aria-label="Выбор канала YouTube"
        onClick={() => setYtChannelModal(false)}
      >
        <div
          className="card max-w-sm w-full p-4 space-y-3 border border-[#27272f] shadow-xl bg-[#0d0d14]"
          onClick={(e) => e.stopPropagation()}
        >
          <p className="text-sm font-medium text-white text-center">Куда залить видео?</p>
          <div className="flex flex-col gap-2">
            <button
              type="button"
              disabled={!primaryAuth || ytBusy}
              onClick={() => pickChannelAndUpload('primary')}
              className="w-full py-2.5 rounded-lg text-sm font-medium bg-[#27272f] hover:bg-[#3f3f46] text-white disabled:opacity-40 disabled:cursor-not-allowed text-left px-3"
            >
              <span className="block">
                {youtubeStatus?.profiles?.primary?.label || 'Канал 1'}
                {!primaryAuth ? ' (не подключён)' : ''}
              </span>
              {primaryAuth && youtubeStatus?.profiles?.primary?.channel_hint ? (
                <span className="block text-[11px] font-normal text-[#a1a1aa] mt-0.5 truncate" title={youtubeStatus.profiles.primary.channel_hint}>
                  {youtubeStatus.profiles.primary.channel_hint}
                </span>
              ) : null}
            </button>
            <button
              type="button"
              disabled={!secondaryAuth || ytBusy}
              onClick={() => pickChannelAndUpload('secondary')}
              className="w-full py-2.5 rounded-lg text-sm font-medium bg-[#27272f] hover:bg-[#3f3f46] text-white disabled:opacity-40 disabled:cursor-not-allowed text-left px-3"
            >
              <span className="block">
                {youtubeStatus?.profiles?.secondary?.label || 'Канал 2'}
                {!secondaryAuth ? ' (не подключён)' : ''}
              </span>
              {secondaryAuth && youtubeStatus?.profiles?.secondary?.channel_hint ? (
                <span className="block text-[11px] font-normal text-[#a1a1aa] mt-0.5 truncate" title={youtubeStatus.profiles.secondary.channel_hint}>
                  {youtubeStatus.profiles.secondary.channel_hint}
                </span>
              ) : null}
            </button>
          </div>
          <button
            type="button"
            onClick={() => setYtChannelModal(false)}
            className="w-full py-2 text-xs text-[#71717a] hover:text-white"
          >
            Отмена
          </button>
        </div>
      </div>,
      document.body,
    );

  return (
    <>
    <motion.div
      whileHover={{ y: -2 }}
      transition={{ duration: 0.15 }}
      className="card overflow-hidden cursor-pointer group h-fit max-w-full min-w-0 flex flex-col"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => onClick(video)}
    >
      {/* Thumbnail / avatar */}
      <div className="relative h-[7rem] min-[400px]:h-28 sm:h-32 md:h-36 w-full shrink-0 bg-[#0d0d14] overflow-hidden">
        {thumbUrl ? (
          <img
            src={thumbUrl}
            alt=""
            loading="lazy"
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-5xl opacity-20">🎬</div>
          </div>
        )}
        <motion.div
          animate={{ opacity: hovered ? 1 : 0 }}
          className="absolute inset-0 bg-brand-600/20 flex items-center justify-center"
        >
          <RiPlayCircleLine className="text-white text-4xl drop-shadow-lg" />
        </motion.div>
      </div>

      {/* Info */}
      <div className="p-2.5 sm:p-3 space-y-1.5 sm:space-y-2">
        <div className="flex items-start gap-2 min-w-0">
          {(video.video_lang === 'ru' || video.video_lang === 'en') && (
            <span
              className="shrink-0 text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-[#27272f] text-[#a1a1aa]"
              title={video.video_lang === 'en' ? 'English' : 'Русский'}
            >
              {video.video_lang}
            </span>
          )}
          <div className="font-medium text-sm text-[#e4e4f0] line-clamp-2 min-w-0 flex-1" title={video.title}>
            {video.title || `Видео #${video.session_id.slice(-8)}`}
          </div>
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-[#71717a]">{video.size_mb ?? '—'} MB</span>
          <span className="text-[10px] text-[#52525b]">{formatDate(video.created_at)}</span>
        </div>
        
        {/* Publishing metadata button */}
        {video.publishing && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setShowPublishing(!showPublishing);
            }}
            className="w-full flex items-center justify-center gap-1.5 text-brand-400 hover:text-brand-300 text-xs font-medium transition-colors py-1.5 px-2 rounded border border-brand-400/30 hover:border-brand-300 bg-brand-400/10"
          >
            📝 {showPublishing ? 'Скрыть' : 'Для YouTube'}
          </button>
        )}
        
        {/* Publishing metadata panel */}
        {showPublishing && video.publishing && (
          <div className="space-y-3 pt-2 border-t border-[#27272f] max-h-[40vh] sm:max-h-44 md:max-h-48 overflow-y-auto overscroll-contain pr-0.5 -mr-0.5">
            {/* Russian Version */}
            {video.publishing.ru && (
              <div className="space-y-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs">🇷🇺</span>
                  <span className="text-[10px] font-semibold text-brand-300 uppercase tracking-wider">Русская</span>
                </div>
                
                {/* Title RU */}
                <div>
                  <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1">
                    Название
                  </label>
                  <div className="flex gap-1.5">
                    <input
                      type="text"
                      value={video.publishing.ru.title || ''}
                      readOnly
                      className="flex-1 bg-[#0d0d14] border border-[#27272f] rounded px-2 py-1 text-xs text-white"
                    />
                    <button
                      type="button"
                      onClick={() => copyToClipboard(video.publishing.ru.title || '', 'Название')}
                      className="text-[10px] bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-2 py-1 rounded transition-colors"
                    >
                      Копия
                    </button>
                  </div>
                </div>
                
                {/* Description RU */}
                <div>
                  <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1">
                    Описание
                  </label>
                  <div className="flex gap-1.5">
                    <textarea
                      value={video.publishing.ru.description || ''}
                      readOnly
                      rows={2}
                      className="flex-1 bg-[#0d0d14] border border-[#27272f] rounded px-2 py-1 text-xs text-white resize-none"
                    />
                    <button
                      type="button"
                      onClick={() => copyToClipboard(video.publishing.ru.description || '', 'Описание')}
                      className="text-[10px] bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-2 py-1 rounded transition-colors self-start mt-0.5"
                    >
                      Копия
                    </button>
                  </div>
                </div>
                
                {/* Tags RU */}
                <div>
                  <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1">
                    Теги
                  </label>
                  <div className="flex gap-1.5">
                    <input
                      type="text"
                      value={(video.publishing.ru.tags || []).join(', ')}
                      readOnly
                      className="flex-1 bg-[#0d0d14] border border-[#27272f] rounded px-2 py-1 text-xs text-white"
                    />
                    <button
                      type="button"
                      onClick={() => copyToClipboard((video.publishing.ru.tags || []).join(', '), 'Теги')}
                      className="text-[10px] bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-2 py-1 rounded transition-colors"
                    >
                      Копия
                    </button>
                  </div>
                </div>
              </div>
            )}
            
            {/* English Version */}
            {video.publishing.en && (
              <div className="space-y-3 pt-3 border-t border-[#27272f]">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs">🇬🇧</span>
                  <span className="text-[10px] font-semibold text-brand-300 uppercase tracking-wider">English</span>
                </div>
                
                {/* Title EN */}
                <div>
                  <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1">
                    Title
                  </label>
                  <div className="flex gap-1.5">
                    <input
                      type="text"
                      value={video.publishing.en.title || ''}
                      readOnly
                      className="flex-1 bg-[#0d0d14] border border-[#27272f] rounded px-2 py-1 text-xs text-white"
                    />
                    <button
                      type="button"
                      onClick={() => copyToClipboard(video.publishing.en.title || '', 'Title')}
                      className="text-[10px] bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-2 py-1 rounded transition-colors"
                    >
                      Copy
                    </button>
                  </div>
                </div>
                
                {/* Description EN */}
                <div>
                  <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1">
                    Description
                  </label>
                  <div className="flex gap-1.5">
                    <textarea
                      value={video.publishing.en.description || ''}
                      readOnly
                      rows={2}
                      className="flex-1 bg-[#0d0d14] border border-[#27272f] rounded px-2 py-1 text-xs text-white resize-none"
                    />
                    <button
                      type="button"
                      onClick={() => copyToClipboard(video.publishing.en.description || '', 'Description')}
                      className="text-[10px] bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-2 py-1 rounded transition-colors self-start mt-0.5"
                    >
                      Copy
                    </button>
                  </div>
                </div>
                
                {/* Tags EN */}
                <div>
                  <label className="block text-[10px] font-semibold text-[#71717a] uppercase tracking-wider mb-1">
                    Tags
                  </label>
                  <div className="flex gap-1.5">
                    <input
                      type="text"
                      value={(video.publishing.en.tags || []).join(', ')}
                      readOnly
                      className="flex-1 bg-[#0d0d14] border border-[#27272f] rounded px-2 py-1 text-xs text-white"
                    />
                    <button
                      type="button"
                      onClick={() => copyToClipboard((video.publishing.en.tags || []).join(', '), 'Tags')}
                      className="text-[10px] bg-brand-400/20 hover:bg-brand-400/30 text-brand-300 px-2 py-1 rounded transition-colors"
                    >
                      Copy
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {showYoutubePanel && (
          <div
            className="space-y-2 pt-2 border-t border-[#27272f]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex flex-col gap-1.5">
              <label className="text-[10px] font-semibold text-[#71717a] uppercase tracking-wider">
                YouTube Shorts
              </label>
              {youtubeLoading && (
                <p className="text-[10px] text-[#71717a]">
                  Загрузка статуса аккаунтов…
                </p>
              )}
              {!youtubeLoading && !youtubeReady && (
                <p className="text-[10px] text-amber-400/90">
                  Войди в Google (кнопки «Канал 1/2» вверху страницы).
                </p>
              )}
              <div className="flex flex-wrap gap-1.5">
                <select
                  value={ytPrivacy}
                  onChange={(e) => setYtPrivacy(e.target.value)}
                  className="flex-1 min-w-[7rem] bg-[#0d0d14] border border-[#27272f] rounded px-2 py-1 text-[11px] text-white"
                >
                  <option value="public">Публично</option>
                  <option value="unlisted">По ссылке</option>
                  <option value="private">Приватно</option>
                </select>
                {video.publishing?.ru && video.publishing?.en ? (
                  <select
                    value={ytLang}
                    onChange={(e) => setYtLang(e.target.value)}
                    className="flex-1 min-w-[5rem] bg-[#0d0d14] border border-[#27272f] rounded px-2 py-1 text-[11px] text-white"
                  >
                    <option value="en">EN мета</option>
                    <option value="ru">RU мета</option>
                  </select>
                ) : null}
              </div>
              <button
                type="button"
                onClick={handleYoutubeButtonClick}
                disabled={ytBusy || youtubeLoading || !youtubeReady}
                className="w-full flex items-center justify-center gap-1.5 text-red-400 hover:text-red-300 text-xs font-medium transition-colors py-1.5 px-2 rounded border border-red-400/40 hover:border-red-300 bg-red-500/10 disabled:opacity-50"
              >
                {youtubeLoading
                  ? 'Проверка YouTube…'
                  : ytBusy
                    ? 'Загрузка…'
                    : '▶ Залить на YouTube'}
              </button>
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <a
            href={video?.url ? base + video.url : '#'}
            download
            onClick={(e) => e.stopPropagation()}
            className="flex items-center gap-1.5 text-brand-400 hover:text-brand-300 text-xs font-medium transition-colors"
          >
            <RiDownloadLine className="text-sm" />
            Скачать
          </a>
          {quoteCaptionForVideo(video) ? (
            <button
              type="button"
              onClick={async (e) => {
                e.stopPropagation();
                const text = quoteCaptionForVideo(video);
                try {
                  await navigator.clipboard.writeText(text);
                } catch {
                  const textarea = document.createElement('textarea');
                  textarea.value = text;
                  document.body.appendChild(textarea);
                  textarea.select();
                  document.execCommand('copy');
                  document.body.removeChild(textarea);
                }
              }}
              className="flex items-center gap-1.5 text-[#71717a] hover:text-brand-300 text-xs transition-colors"
            >
              <RiFileCopyLine className="text-sm" />
              Копировать цитату
            </button>
          ) : null}
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleting}
            className="flex items-center gap-1.5 text-[#71717a] hover:text-red-400 text-xs transition-colors disabled:opacity-50"
          >
            <RiDeleteBinLine className="text-sm" />
            Удалить
          </button>
        </div>
      </div>
    </motion.div>
    {channelPickerModal}
    </>
  );
}
