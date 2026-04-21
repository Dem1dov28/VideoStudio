import { useCallback, useEffect, useMemo, useState } from 'react';
import { api, socialVideoFileUrl } from '../services/api';

const DEFAULT_YT_TITLE = '🤑ССЫЛКА В ШАПКЕ ПРОФИЛЯ🤑';
const DEFAULT_YT_DESCRIPTION = `🎰 Очередная нарезка казино – смотри до конца, будет жарко!

💎 Все ссылки на бонусы и лучшие казино – в шапке профиля (клик на аватарку).

📢 Подпишись, чтобы не пропустить новые моменты: #нарезкиказино #игравпрофиле #джекпот #Shorts`;
const DEFAULT_KEYWORDS =
  'нарезки казино, крупные выигрыши, слот 777, джекпот срыв, игра в профиле, эмоции игроков, лучшие моменты казино.';
const DEFAULT_TAGS =
  'Shorts, нарезки казино, крупные выигрыши, слот 777, джекпот, казино онлайн, casino highlights, big win, slot machine, jackpot';

function socialRowSid(channelId, videoKey) {
  return `${channelId}\u001f${videoKey}`;
}

function platformLabel(p) {
  if (p === 'tiktok') return 'TikTok';
  return 'Другое';
}

function statusPill(status) {
  switch (status) {
    case 'running':
      return { className: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30', label: 'загрузка' };
    case 'queued':
      return { className: 'bg-amber-500/20 text-amber-400 border border-amber-500/30', label: 'очередь' };
    case 'done':
      return { className: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30', label: 'готово' };
    case 'error':
      return { className: 'bg-red-500/20 text-red-400 border border-red-500/30', label: 'ошибка' };
    case 'cancelled':
      return { className: 'bg-amber-500/20 text-amber-400 border border-amber-500/30', label: 'остановлено' };
    default:
      return { className: 'bg-[#27272f] text-[#a1a1aa]', label: status };
  }
}

function VideoRow({
  channelId,
  v,
  health,
  youtubeForm,
  uploadBusySid,
  uploadErr,
  onYoutubeUpload,
}) {
  const src = v.file_ready ? socialVideoFileUrl(channelId, v.key) : null;
  const sid = socialRowSid(channelId, v.key);
  const [brandingCorner, setBrandingCorner] = useState('tr');

  useEffect(() => {
    setBrandingCorner('tr');
  }, [channelId, v.key]);

  const accounts = health?.youtube_accounts ?? [];
  const selected = accounts.find((a) => a.id === youtubeForm.channelProfile);
  const brandingKnownMissing = health?.social_youtube_branding_exists === false;
  const clientOk = health?.client_secret_exists;
  const canUploadYt =
    Boolean(clientOk) &&
    Boolean(selected?.token_ok) &&
    Boolean(youtubeForm.channelProfile) &&
    v.status === 'ok' &&
    Boolean(v.file_ready) &&
    !v.youtube_id &&
    uploadBusySid !== sid;

  const showYoutubeForm = v.status === 'ok' && v.file_ready && !v.youtube_id && accounts.length > 0;

  return (
    <li className="rounded-xl border border-[#27272f] bg-[#0d0d14] p-4 space-y-2">
      <div className="text-sm font-medium text-[#e4e4f0]">{v.title || v.key}</div>
      <div className="text-xs text-[#71717a] flex flex-wrap gap-2 items-center">
        <span
          className={`px-2 py-0.5 rounded-md text-[10px] uppercase ${
            v.status === 'ok'
              ? 'bg-emerald-500/15 text-emerald-400'
              : v.status === 'failed'
                ? 'bg-red-500/15 text-red-400'
                : 'bg-[#27272f] text-[#a1a1aa]'
          }`}
        >
          {v.status}
        </span>
        <a href={v.page_url} target="_blank" rel="noreferrer" className="text-brand-400 hover:underline">
          источник
        </a>
        {v.downloaded_at ? <span>· {new Date(v.downloaded_at).toLocaleString()}</span> : null}
      </div>
      {v.error ? <div className="text-xs text-red-400">{v.error}</div> : null}
      {v.youtube_id ? (
        <p className="text-sm text-[#a1a1aa]">
          На YouTube:{' '}
          <a
            href={`https://www.youtube.com/watch?v=${v.youtube_id}`}
            target="_blank"
            rel="noreferrer"
            className="text-brand-400 hover:underline"
          >
            открыть
          </a>
        </p>
      ) : null}
      {src ? (
        <video className="w-full max-w-md rounded-lg mt-2 bg-black" src={src} controls playsInline preload="metadata" />
      ) : null}

      {showYoutubeForm ? (
        <div className="mt-3 space-y-3 rounded-lg border border-[#27272f] bg-[#09090b] p-3">
          <div>
            <label className="block text-xs text-[#71717a] mb-1">Куда поставить 0408.mp4 на кадре</label>
            <select
              value={brandingCorner}
              onChange={(e) => setBrandingCorner(e.target.value)}
              disabled={brandingKnownMissing}
              className="w-full max-w-xs rounded-lg border border-[#27272f] bg-[#0d0d14] px-3 py-2 text-sm text-[#e4e4f0]"
            >
              <option value="tr">правый верхний угол</option>
              <option value="tl">левый верхний угол</option>
              <option value="br">правый нижний угол</option>
              <option value="bl">левый нижний угол</option>
              <option value="mr">справа по центру (вертикально)</option>
              <option value="ml">слева по центру (вертикально)</option>
            </select>
            {brandingKnownMissing ? (
              <p className="text-xs text-amber-400 mt-2">
                Файл <code className="text-[#e4e4f0]">0408.mp4</code> не найден в корне проекта — заливка без оверлея.
                Положи рядом с client secret JSON.
              </p>
            ) : null}
            <p className="text-xs text-[#52525b] mt-2">
              Канал и текст карточки — в колонке слева. Здесь только угол бренд-оверлея для этого файла.
            </p>
          </div>
          {uploadErr ? <div className="text-xs text-red-400">{uploadErr}</div> : null}
          <button
            type="button"
            disabled={!canUploadYt}
            onClick={() => onYoutubeUpload(brandingCorner)}
            className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-40 disabled:pointer-events-none text-white text-sm font-medium"
          >
            {uploadBusySid === sid ? 'Монтаж и заливка…' : 'Залить на YouTube'}
          </button>
        </div>
      ) : null}
    </li>
  );
}

export default function Casino() {
  const [health, setHealth] = useState(null);
  const [list, setList] = useState([]);
  const [detailById, setDetailById] = useState({});
  const [expanded, setExpanded] = useState(() => new Set());
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [url, setUrl] = useState('');
  const [submitBusy, setSubmitBusy] = useState(false);
  const [uploadBusySocial, setUploadBusySocial] = useState(null);
  const [uploadErrSocial, setUploadErrSocial] = useState({});
  const [channelsHint, setChannelsHint] = useState(null);
  const [channelsBusy, setChannelsBusy] = useState(false);

  const [youtubeForm, setYoutubeForm] = useState({
    titleMode: 'tiktok',
    title: DEFAULT_YT_TITLE,
    description: DEFAULT_YT_DESCRIPTION,
    keywords: DEFAULT_KEYWORDS,
    tags: DEFAULT_TAGS,
    privacy: 'public',
    categoryId: '22',
    channelProfile: 'primary',
  });

  const patchYoutube = useCallback((patch) => {
    setYoutubeForm((s) => ({ ...s, ...patch }));
  }, []);

  const accounts = health?.youtube_accounts ?? [];

  useEffect(() => {
    if (!accounts.length) return;
    const ids = new Set(accounts.map((a) => a.id));
    if (!youtubeForm.channelProfile || !ids.has(youtubeForm.channelProfile)) {
      const ok = accounts.find((a) => a.token_ok);
      patchYoutube({ channelProfile: (ok ?? accounts[0]).id });
    }
  }, [accounts, youtubeForm.channelProfile, patchYoutube]);

  const needsPoll = useMemo(
    () => list.some((c) => c.status === 'running' || c.status === 'queued'),
    [list],
  );

  const loadHealth = useCallback(async () => {
    try {
      const h = await api.fetchCasinoHealth();
      setHealth(h);
    } catch (e) {
      setHealth(null);
    }
  }, []);

  const loadList = useCallback(async () => {
    try {
      const rows = await api.fetchSocialChannels();
      setList(rows);
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (id) => {
    try {
      const d = await api.fetchSocialChannel(id);
      setDetailById((prev) => ({ ...prev, [id]: d }));
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void loadHealth();
  }, [loadHealth]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (!needsPoll) return;
    const id = window.setInterval(() => void loadList(), 2000);
    return () => window.clearInterval(id);
  }, [needsPoll, loadList]);

  useEffect(() => {
    for (const id of expanded) {
      void loadDetail(id);
    }
  }, [list, expanded, loadDetail]);

  async function onSubmit(e) {
    e.preventDefault();
    setSubmitBusy(true);
    setErr(null);
    try {
      await api.createSocialChannel({ profile_url: url.trim() });
      setUrl('');
      await loadList();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitBusy(false);
    }
  }

  function toggleExpand(id) {
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else {
        n.add(id);
        void loadDetail(id);
      }
      return n;
    });
  }

  async function onCancel(id) {
    setErr(null);
    try {
      await api.cancelSocialChannel(id);
      await loadList();
      void loadDetail(id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function onStart(id) {
    setErr(null);
    try {
      await api.startSocialChannel(id);
      await loadList();
      void loadDetail(id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function onDelete(id, wipe) {
    setErr(null);
    try {
      await api.deleteSocialChannel(id, wipe);
      setExpanded((e) => {
        const n = new Set(e);
        n.delete(id);
        return n;
      });
      setDetailById((d) => {
        const x = { ...d };
        delete x[id];
        return x;
      });
      await loadList();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function onSocialYoutubeUpload(channelId, videoKey, sourceTitle, brandingCorner) {
    const sid = socialRowSid(channelId, videoKey);
    setUploadErrSocial((prev) => {
      const n = { ...prev };
      delete n[sid];
      return n;
    });
    setUploadBusySocial(sid);
    const manualTitle = youtubeForm.title.trim();
    const tiktokTitle = (sourceTitle || '').trim();
    const uploadTitle =
      youtubeForm.titleMode === 'tiktok' ? tiktokTitle || manualTitle : manualTitle || tiktokTitle;
    try {
      await api.youtubeUpload({
        channel_profile: youtubeForm.channelProfile,
        privacy_status: youtubeForm.privacy,
        social_channel_id: channelId,
        social_video_key: videoKey,
        branding_corner: brandingCorner,
        title: uploadTitle,
        description: youtubeForm.description,
        keywords: youtubeForm.keywords,
        tags: youtubeForm.tags,
        category_id: youtubeForm.categoryId,
      });
      await loadHealth();
      await loadDetail(channelId);
      await loadList();
    } catch (e) {
      setUploadErrSocial((prev) => ({
        ...prev,
        [sid]: e instanceof Error ? e.message : String(e),
      }));
    } finally {
      setUploadBusySocial(null);
    }
  }

  const canSubmit = url.trim().length > 8 && !submitBusy;
  const selected = accounts.find((a) => a.id === youtubeForm.channelProfile);
  const titleMode = youtubeForm.titleMode ?? 'tiktok';

  return (
    <div className="min-h-full p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto">
      <h1 className="text-xl font-bold text-white mb-2">Казино · каналы TikTok</h1>
      <p className="text-sm text-[#71717a] mb-6">
        Вставь URL профиля TikTok — скачаются все доступные ролики. «Докачать» продолжит с{' '}
        <code className="text-brand-400">archive.txt</code> (уже загруженное не дублируется). Заливка на YouTube — колонка{' '}
        <strong className="text-[#e4e4f0]">слева</strong>. OAuth для YouTube — в разделе «Видео», если токен ещё не привязан.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(280px,360px)_1fr] gap-6 items-start">
        {/* Left: YouTube */}
        <aside className="rounded-2xl border border-[#27272f] bg-[#0d0d14] p-5 space-y-4 lg:sticky lg:top-4">
          <h2 className="text-lg font-semibold text-white mt-0">Заливка на YouTube</h2>
          <p className="text-xs text-[#71717a]">
            Эти поля одни на все ролики: у каждого видео своя кнопка «Залить».
          </p>

          {!health?.client_secret_exists ? (
            <div className="text-xs text-amber-400 border border-amber-500/30 rounded-lg p-3 bg-amber-500/5">
              {health?.youtube_uses_registry
                ? 'Проверь пути client_secrets в реестре YOUTUBE_PROFILES_CONFIG (JSON) — каждый слот должен указывать на существующий OAuth client JSON.'
                : 'Укажи YOUTUBE_OAUTH_CLIENT_SECRETS в .env — иначе заливка не сработает.'}
            </div>
          ) : null}

          {accounts.length > 0 ? (
            <div>
              <label className="block text-xs text-[#71717a] mb-1">Канал YouTube (токен)</label>
              <div className="flex flex-wrap gap-2 items-center">
                <select
                  value={youtubeForm.channelProfile}
                  onChange={(e) => patchYoutube({ channelProfile: e.target.value })}
                  className="flex-1 min-w-[10rem] rounded-lg border border-[#27272f] bg-[#09090b] px-3 py-2 text-sm text-[#e4e4f0]"
                >
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.label}
                      {a.gcp_project ? ` — ${a.gcp_project}` : ''}
                      {!a.token_ok ? ' (нет token)' : ''}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  disabled={!youtubeForm.channelProfile || !selected?.token_ok || channelsBusy}
                  onClick={() => {
                    setChannelsBusy(true);
                    setChannelsHint(null);
                    void (async () => {
                      try {
                        const ch = await api.fetchYoutubeChannelsList(youtubeForm.channelProfile);
                        setChannelsHint(
                          ch.length
                            ? ch.map((c) => `${c.title} (${c.id})${c.custom_url ? ` ${c.custom_url}` : ''}`).join('; ')
                            : 'Список пуст — проверь scopes / перелогинь youtube-auth',
                        );
                      } catch (e) {
                        setChannelsHint(e instanceof Error ? e.message : String(e));
                      } finally {
                        setChannelsBusy(false);
                      }
                    })();
                  }}
                  className="px-3 py-2 rounded-lg border border-[#27272f] text-sm text-[#e4e4f0] hover:bg-[#1a1a24] disabled:opacity-40"
                >
                  {channelsBusy ? '…' : 'Каналы по API'}
                </button>
              </div>
              {channelsHint ? <p className="text-xs text-[#71717a] mt-2 break-words">{channelsHint}</p> : null}
              <p className="text-xs text-[#52525b] mt-2">
                Ролик уйдёт на канал токена этой строки (<strong>{selected?.label || youtubeForm.channelProfile}</strong>
                ). Shorts: вертикаль/квадрат, ≤60 с.
              </p>
            </div>
          ) : (
            <p className="text-xs text-[#71717a]">Нет слотов токена в конфиге.</p>
          )}

          <div>
            <label className="block text-xs text-[#71717a] mb-1">Откуда брать заголовок</label>
            <select
              value={titleMode}
              onChange={(e) => patchYoutube({ titleMode: e.target.value })}
              className="w-full rounded-lg border border-[#27272f] bg-[#09090b] px-3 py-2 text-sm text-[#e4e4f0]"
            >
              <option value="tiktok">Как в TikTok — оригинальное название ролика</option>
              <option value="manual">Текст из поля ниже</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-[#71717a] mb-1">Текст заголовка (ручной)</label>
            <input
              type="text"
              value={youtubeForm.title}
              onChange={(e) => patchYoutube({ title: e.target.value })}
              disabled={titleMode === 'tiktok'}
              className="w-full rounded-lg border border-[#27272f] bg-[#09090b] px-3 py-2 text-sm text-[#e4e4f0] disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-xs text-[#71717a] mb-1">Приватность</label>
            <select
              value={youtubeForm.privacy}
              onChange={(e) => patchYoutube({ privacy: e.target.value })}
              className="w-full rounded-lg border border-[#27272f] bg-[#09090b] px-3 py-2 text-sm text-[#e4e4f0]"
            >
              <option value="private">private</option>
              <option value="unlisted">unlisted</option>
              <option value="public">public</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-[#71717a] mb-1">Описание</label>
            <textarea
              value={youtubeForm.description}
              onChange={(e) => patchYoutube({ description: e.target.value })}
              rows={5}
              className="w-full rounded-lg border border-[#27272f] bg-[#09090b] px-3 py-2 text-sm text-[#e4e4f0]"
            />
          </div>
          <div className="grid grid-cols-1 gap-3">
            <div>
              <label className="block text-xs text-[#71717a] mb-1">Ключевые слова (через запятую)</label>
              <input
                type="text"
                value={youtubeForm.keywords}
                onChange={(e) => patchYoutube({ keywords: e.target.value })}
                className="w-full rounded-lg border border-[#27272f] bg-[#09090b] px-3 py-2 text-sm text-[#e4e4f0]"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-[#71717a] mb-1">Теги</label>
                <input
                  type="text"
                  value={youtubeForm.tags}
                  onChange={(e) => patchYoutube({ tags: e.target.value })}
                  className="w-full rounded-lg border border-[#27272f] bg-[#09090b] px-3 py-2 text-sm text-[#e4e4f0]"
                />
              </div>
              <div>
                <label className="block text-xs text-[#71717a] mb-1">Category ID</label>
                <input
                  type="text"
                  value={youtubeForm.categoryId}
                  onChange={(e) => patchYoutube({ categoryId: e.target.value })}
                  className="w-full rounded-lg border border-[#27272f] bg-[#09090b] px-3 py-2 text-sm text-[#e4e4f0]"
                />
              </div>
            </div>
          </div>
        </aside>

        {/* Right: channels */}
        <div className="rounded-2xl border border-[#27272f] bg-[#0d0d14] p-5">
          <h2 className="text-lg font-semibold text-white mt-0 mb-2">Каналы TikTok</h2>

          {err ? <div className="text-sm text-red-400 mb-3">{err}</div> : null}

          <form onSubmit={(e) => void onSubmit(e)} className="space-y-3 mb-6">
            <div>
              <label htmlFor="social-channel-url" className="block text-xs text-[#71717a] mb-1">
                URL канала TikTok
              </label>
              <input
                id="social-channel-url"
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.tiktok.com/@…"
                autoComplete="off"
                className="w-full rounded-lg border border-[#27272f] bg-[#09090b] px-3 py-2 text-sm text-[#e4e4f0]"
              />
            </div>
            <button
              type="submit"
              disabled={!canSubmit}
              className="px-4 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-40 text-white text-sm font-medium"
            >
              {submitBusy ? 'Отправка…' : 'Скачать канал'}
            </button>
          </form>

          <div className="flex flex-wrap gap-2 items-center mb-4">
            <button
              type="button"
              disabled={loading}
              onClick={() => void loadList()}
              className="px-3 py-2 rounded-lg border border-[#27272f] text-sm text-[#e4e4f0] hover:bg-[#1a1a24]"
            >
              Обновить список
            </button>
            {needsPoll ? <span className="text-xs text-[#52525b]">Авто-обновление каждые 2 с…</span> : null}
          </div>

          {loading && list.length === 0 ? <p className="text-sm text-[#52525b]">Загрузка…</p> : null}
          {!loading && list.length === 0 ? (
            <p className="text-sm text-[#52525b]">Пока нет каналов. Выше — URL и «Скачать канал».</p>
          ) : null}

          {list.length > 0 ? (
            <ul className="space-y-4">
              {list.map((ch) => {
                const sp = statusPill(ch.status);
                const isOpen = expanded.has(ch.id);
                const detail = detailById[ch.id];
                const active = ch.status === 'running' || ch.status === 'queued';

                return (
                  <li key={ch.id} className="rounded-xl border border-[#27272f] bg-[#09090b] p-4">
                    <div className="flex flex-wrap gap-2 justify-between items-start">
                      <div className="flex flex-wrap gap-2 items-center text-xs">
                        <span
                          className={`px-2 py-0.5 rounded-md ${
                            ch.platform === 'tiktok'
                              ? 'bg-emerald-500/15 text-emerald-400'
                              : 'bg-red-500/15 text-red-400'
                          }`}
                        >
                          {platformLabel(ch.platform)}
                        </span>
                        <span className={`px-2 py-0.5 rounded-md ${sp.className}`}>{sp.label}</span>
                        <span className="text-[#52525b]">{new Date(ch.updated_at).toLocaleString()}</span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {active ? (
                          <button
                            type="button"
                            onClick={() => void onCancel(ch.id)}
                            className="px-2 py-1 rounded-lg border border-red-500/40 text-xs text-red-400 hover:bg-red-500/10"
                          >
                            Стоп
                          </button>
                        ) : null}
                        {!active ? (
                          <button
                            type="button"
                            onClick={() => void onStart(ch.id)}
                            className="px-2 py-1 rounded-lg border border-[#27272f] text-xs text-[#e4e4f0] hover:bg-[#1a1a24]"
                          >
                            Докачать
                          </button>
                        ) : null}
                        {!active ? (
                          <>
                            <button
                              type="button"
                              onClick={() => void onDelete(ch.id, false)}
                              className="px-2 py-1 rounded-lg border border-[#27272f] text-xs text-[#e4e4f0] hover:bg-[#1a1a24]"
                            >
                              Удалить запись
                            </button>
                            <button
                              type="button"
                              onClick={() => void onDelete(ch.id, true)}
                              className="px-2 py-1 rounded-lg border border-red-500/40 text-xs text-red-400 hover:bg-red-500/10"
                            >
                              Удалить + файлы
                            </button>
                          </>
                        ) : null}
                      </div>
                    </div>
                    <div className="text-xs text-[#71717a] mt-2 break-all">
                      <a href={ch.profile_url} target="_blank" rel="noreferrer" className="text-brand-400 hover:underline">
                        {ch.normalized_url}
                      </a>
                      <span>
                        {' '}
                        · ок: {ch.stats_completed} · ошибок: {ch.stats_failed} · в списке: {ch.video_count}
                      </span>
                    </div>
                    {(ch.detail || ch.error) && (
                      <p className="text-xs text-[#52525b] mt-2">
                        {ch.error ? <span className="text-red-400 mr-1">err</span> : null}
                        {ch.detail ?? ch.error}
                      </p>
                    )}
                    <button
                      type="button"
                      onClick={() => toggleExpand(ch.id)}
                      className="mt-3 text-xs text-brand-400 hover:underline"
                    >
                      {isOpen ? 'Скрыть ролики' : 'Показать ролики'}
                    </button>
                    {isOpen && detail && (
                      <div className="mt-4">
                        <div className="text-xs font-semibold text-[#71717a] uppercase tracking-wider mb-2">Ролики</div>
                        {detail.videos.length === 0 ? (
                          <p className="text-sm text-[#52525b]">Пока нет записей (идёт загрузка или плейлист пуст).</p>
                        ) : (
                          <ul className="space-y-3">
                            {detail.videos.map((v) => (
                              <VideoRow
                                key={v.key}
                                channelId={ch.id}
                                v={v}
                                health={health}
                                youtubeForm={youtubeForm}
                                uploadBusySid={uploadBusySocial}
                                uploadErr={uploadErrSocial[socialRowSid(ch.id, v.key)]}
                                onYoutubeUpload={(corner) =>
                                  void onSocialYoutubeUpload(ch.id, v.key, v.title || '', corner)
                                }
                              />
                            ))}
                          </ul>
                        )}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : null}
        </div>
      </div>
    </div>
  );
}
