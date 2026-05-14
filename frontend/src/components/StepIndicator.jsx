import { motion } from 'framer-motion';
import { clsx } from 'clsx';
import { RiCheckLine, RiLoader4Line } from 'react-icons/ri';

const STEPS = [
  { id: 'factminer', label: 'Факты',   emoji: '🔎' },
  { id: 'scenario', label: 'Сценарий', emoji: '✍️' },
  { id: 'factcheck', label: 'Проверка', emoji: '🧪' },
  { id: 'images',   label: 'Картинки', emoji: '🖼️' },
  { id: 'voice',    label: 'Озвучка',  emoji: '🎙️' },
  { id: 'video',    label: 'Видео',    emoji: '🎬' },
  { id: 'done',     label: 'Готово',   emoji: '✅' },
];

/** Соответствует чекпоинтам mode5 (stub → after_tts → …) в modes/mode5/pipeline.py */
const MODE5_STEPS_TEMPLATE = [
  { id: 'm5_boot', label: 'Старт', emoji: '⚡' },
  { id: 'm5_plan', label: 'Текст и структура', emoji: '📝' },
  { id: 'm5_tts', label: 'Озвучка чанков', emoji: '🎙️' },
  { id: 'm5_img', label: 'Иллюстрации', emoji: '🖼️' },
  { id: 'm5_slice', label: 'Нарезка и сегменты', emoji: '✂️' },
  { id: 'm5_preview', label: 'Превью частей', emoji: '👁️' },
  { id: 'm5_final', label: 'Финальная склейка', emoji: '🎬' },
];

/** Короткие пояснения к шагам (длинное видео, mode 5) */
const MODE5_PHASE_EXPLAIN = [
  'Создаётся план сессии и появляется первый сохранённый черновик на диске.',
  'Готовится текст частей, оглавление или факты — от подрежима.',
  'Голос читает текст по частям; длительность задаёт реальная озвучка.',
  'К каждому короткому окну текста генерируется картинка в одном стиле.',
  'Аудио режется по сегментам, при необходимости — зацикленные блоки.',
  'Собираются короткие mp4 по каждой части для проверки в интерфейсе.',
  'Превью склеиваются в итоговый ролик, добавляются метаданные для публикации.',
];

const MODE5_CHECKPOINT_LABEL = {
  stub: 'Чекпоинт: черновик плана (stub) — технический маркер, не только «озвучка»',
  after_tts: 'Чекпоинт: после озвучки чанков',
  after_images: 'Чекпоинт: после картинок',
  after_slices: 'Чекпоинт: после нарезки',
  after_previews: 'Чекпоинт: после превью частей',
  completed: 'Чекпоинт: финал записан',
};

/** Совпадает с mode5_ui_phase в modes/mode5/pipeline.py */
const MODE5_UI_PHASE_RU = {
  plan_file_pending: {
    title: 'Ожидание первого плана',
    detail: 'Конвейер стартовал, файл mode5_plan.json ещё не создан.',
  },
  intro_preflight_generating: {
    title: 'Анимированные превью стиля',
    detail: 'Генерируются короткие вступительные клипы; полный TTS длинного ролика после подтверждения.',
  },
  intro_await_confirm: {
    title: 'Подтвердите превью вступления',
    detail: 'Озвучка и монтаж основного видео до вашего «Продолжить» не выполняются.',
  },
  tts_chunks_parallel: {
    title: 'Озвучка чанков',
    detail: 'Параллельный синтез голоса по частям (реальная длительность из WAV).',
  },
  post_tts_segmentation: {
    title: 'Сегменты и разметка',
    detail: 'Озвучка на диске, строятся окна текста под картинки.',
  },
  structure_and_segments: {
    title: 'Структура и сегменты',
    detail: 'Подготовка разметки по частям при отсутствии готовых сегментов на диске.',
  },
  segment_images: {
    title: 'Иллюстрации по сегментам',
    detail: 'Генерация кадров под каждое текстовое окно.',
  },
  checkpoint_after_images: {
    title: 'После картинок',
    detail: 'Все кадры сгенерированы, дальше нарезка и движение к превью.',
  },
  checkpoint_after_slices: {
    title: 'После нарезки аудио',
    detail: 'Сегменты с аудио готовы, собираются превью по частям или финал.',
  },
  chunk_mp4_previews: {
    title: 'Превью частей',
    detail: 'Короткие mp4 по каждой части для проверки в интерфейсе.',
  },
  final_assembly_no_chunk_previews: {
    title: 'Финальная сборка',
    detail: 'Режим без превью по частям — сразу длинный ролик.',
  },
  checkpoint_after_previews: {
    title: 'Превью готовы',
    detail: 'Части собраны, остаётся финальная склейка или публикация.',
  },
  checkpoint_completed: {
    title: 'Чекпоинт completed',
    detail: 'Пайплайн отметил завершение записи плана.',
  },
  final_mp4_on_disk: {
    title: 'Финальный файл на диске',
    detail: 'video_mode5.mp4 найден в папке сессии.',
  },
  running: {
    title: 'В работе',
    detail: 'Промежуточное состояние; смотрите подсказку и чекпоинт ниже.',
  },
};

const MODE5_PHASE_TO_STEP = {
  plan_file_pending: 0,
  intro_preflight_generating: 0,
  intro_await_confirm: 1,
  tts_chunks_parallel: 2,
  post_tts_segmentation: 3,
  structure_and_segments: 3,
  segment_images: 3,
  checkpoint_after_images: 4,
  checkpoint_after_slices: 5,
  chunk_mp4_previews: 5,
  final_assembly_no_chunk_previews: 6,
  checkpoint_after_previews: 6,
  checkpoint_completed: 6,
  final_mp4_on_disk: 6,
  running: 0,
};

function mode5IntroWaitFromHint(progress) {
  if (String(progress?.uiPhase || '').trim() === 'intro_await_confirm') return true;
  if (!progress || typeof progress !== 'object') return false;
  const h = String(progress.hint || '').toLowerCase();
  return (
    (h.includes('проверьте анимированные') && h.includes('подтвердите')) ||
    (h.includes('подтвердите продолжение') && h.includes('озвучк') && h.includes('не запуск')) ||
    h.includes('сначала проверьте')
  );
}

function Mode5ProgressDetail({ stepIndex, progress, awaitIntro, pipelineStatus }) {
  const hint = typeof progress?.hint === 'string' ? progress.hint.trim() : '';
  const hintLc = hint.toLowerCase();
  const ck = String(progress?.checkpoint || '').trim().toLowerCase();
  const ckLabel = MODE5_CHECKPOINT_LABEL[ck] || (ck ? `Чекпоинт: ${ck}` : null);
  const uiPhase = String(progress?.uiPhase || '').trim();
  const phaseMeta = uiPhase && MODE5_UI_PHASE_RU[uiPhase] ? MODE5_UI_PHASE_RU[uiPhase] : null;

  const introGenFromHint =
    !phaseMeta &&
    hintLc.includes('генерир') &&
    hintLc.includes('анимированн') &&
    hintLc.includes('превью');
  const introWaitFromHint =
    !phaseMeta &&
    ((hintLc.includes('проверьте анимированные') && hintLc.includes('подтвердите')) ||
      (hintLc.includes('подтвердите продолжение') &&
        hintLc.includes('озвучк') &&
        hintLc.includes('не запуск')));

  const title = awaitIntro
    ? 'Подтвердите анимированное вступление'
    : phaseMeta
      ? phaseMeta.title
      : introGenFromHint
        ? 'Анимированные превью стиля'
        : introWaitFromHint
          ? 'Подтвердите превью вступления'
          : MODE5_STEPS_TEMPLATE[stepIndex]?.label || 'Прогресс';
  const explain = awaitIntro
    ? 'После «Продолжить» запустятся полный текст, озвучка, картинки и монтаж по выбранному стилю.'
    : phaseMeta
      ? phaseMeta.detail
      : introGenFromHint
        ? 'Рендерятся короткие анимированные клипы; полная озвучка длинного ролика начнётся только после вашего подтверждения.'
        : introWaitFromHint
          ? 'Озвучка и монтаж основного видео на этом шаге ещё не запущены — сначала подтвердите превью.'
          : MODE5_PHASE_EXPLAIN[stepIndex] || '';

  const segDone = Number(progress?.segmentsImaged);
  const segTotal = Number(progress?.segmentsTotal);
  const showSegBar =
    Number.isFinite(segTotal) && segTotal > 0 && Number.isFinite(segDone) && segDone >= 0;
  const segPct = showSegBar ? Math.min(100, Math.round((segDone / segTotal) * 100)) : null;

  const prevDone = Number(progress?.previewsOnDisk);
  const totalCh = Number(progress?.totalChunks);
  const showPrevBar =
    Number.isFinite(totalCh) && totalCh > 0 && Number.isFinite(prevDone) && prevDone >= 0;
  const prevPct = showPrevBar ? Math.min(100, Math.round((prevDone / totalCh) * 100)) : null;

  const introOn = Number(progress?.introOnDisk);
  const introExp = Number(progress?.introExpected);
  const showIntroBar =
    Number.isFinite(introExp) && introExp > 0 && Number.isFinite(introOn) && introOn >= 0;
  const introPct = showIntroBar ? Math.min(100, Math.round((introOn / introExp) * 100)) : null;

  const voiceR = Number(progress?.voiceReady);
  const voiceT = Number(progress?.voiceTotal);
  const showVoiceBar =
    Number.isFinite(voiceT) && voiceT > 0 && Number.isFinite(voiceR) && voiceR >= 0;
  const voicePct = showVoiceBar ? Math.min(100, Math.round((voiceR / voiceT) * 100)) : null;

  const readyChunks = Number(progress?.readyChunks);
  const showChunkLine =
    Number.isFinite(totalCh) && totalCh > 0 && Number.isFinite(readyChunks) && readyChunks >= 0;

  const subMode = progress?.subMode != null ? String(progress.subMode).trim() : '';
  const showTech =
    uiPhase ||
    subMode ||
    progress?.preflightOnly != null ||
    progress?.awaitIntroFromPlan != null;

  return (
    <div className="mt-5 pt-4 border-t border-white/[0.08] space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-400/90 mb-1">
            Сейчас
          </p>
          <p className="text-sm font-semibold text-white leading-snug">{title}</p>
          {explain ? (
            <p className="text-xs text-[#a1a1aa] mt-1.5 leading-relaxed">{explain}</p>
          ) : null}
        </div>
        {pipelineStatus === 'paused' ? (
          <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide px-2 py-1 rounded-md bg-amber-500/15 text-amber-200/95 border border-amber-500/30">
            Пауза
          </span>
        ) : null}
      </div>

      {showTech ? (
        <div className="rounded-lg bg-[#0c0c10] border border-[#2a2a34] px-3 py-2.5 space-y-1.5">
          <p className="text-[10px] font-semibold text-[#71717a] uppercase tracking-wide">
            Технические поля (с сервера)
          </p>
          {uiPhase ? (
            <p className="text-[11px] text-[#a1a1aa]">
              Фаза UI:{' '}
              <span className="font-mono text-emerald-300/95">{uiPhase}</span>
            </p>
          ) : null}
          {subMode ? (
            <p className="text-[11px] text-[#a1a1aa]">
              Подрежим: <span className="text-[#e4e4e0]">{subMode}</span>
            </p>
          ) : null}
          {progress?.preflightOnly === true ? (
            <p className="text-[11px] text-amber-200/90">preflight_only: да (только превью вступления до подтверждения)</p>
          ) : null}
          {progress?.awaitIntroFromPlan === true ? (
            <p className="text-[11px] text-amber-200/90">await_intro_confirmation в плане: да</p>
          ) : null}
        </div>
      ) : null}

      {hint ? (
        <div className="rounded-lg bg-[#14141c] border border-[#27272f] px-3 py-2.5">
          <p className="text-[10px] font-semibold text-[#71717a] uppercase tracking-wide mb-1">
            Статус с сервера (текст)
          </p>
          <p className="text-sm text-[#e4e4e0] leading-relaxed">{hint}</p>
        </div>
      ) : null}

      {(showIntroBar || showVoiceBar || showSegBar || showPrevBar) && (
        <div className="space-y-3">
          {showIntroBar ? (
            <div>
              <div className="flex justify-between text-[11px] text-[#a1a1aa] mb-1">
                <span>Превью вступления на диске</span>
                <span className="font-mono text-[#d4d4d8]">
                  {introOn} / {introExp}
                  {introPct != null ? ` · ${introPct}%` : ''}
                </span>
              </div>
              <div className="h-2 rounded-full bg-white/[0.06] overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-cyan-600 to-brand-400 transition-all duration-500"
                  style={{ width: `${introPct ?? 0}%` }}
                />
              </div>
            </div>
          ) : null}
          {showVoiceBar ? (
            <div>
              <div className="flex justify-between text-[11px] text-[#a1a1aa] mb-1">
                <span>Чанки с готовым WAV (озвучка части)</span>
                <span className="font-mono text-[#d4d4d8]">
                  {voiceR} / {voiceT}
                  {voicePct != null ? ` · ${voicePct}%` : ''}
                </span>
              </div>
              <div className="h-2 rounded-full bg-white/[0.06] overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-brand-400 transition-all duration-500"
                  style={{ width: `${voicePct ?? 0}%` }}
                />
              </div>
            </div>
          ) : null}
          {showSegBar ? (
            <div>
              <div className="flex justify-between text-[11px] text-[#a1a1aa] mb-1">
                <span>Кадры (сегменты)</span>
                <span className="font-mono text-[#d4d4d8]">
                  {segDone} / {segTotal}
                  {segPct != null ? ` · ${segPct}%` : ''}
                </span>
              </div>
              <div className="h-2 rounded-full bg-white/[0.06] overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-400 transition-all duration-500"
                  style={{ width: `${segPct ?? 0}%` }}
                />
              </div>
            </div>
          ) : null}
          {showPrevBar ? (
            <div>
              <div className="flex justify-between text-[11px] text-[#a1a1aa] mb-1">
                <span>Превью частей на диске</span>
                <span className="font-mono text-[#d4d4d8]">
                  {prevDone} / {totalCh}
                  {prevPct != null ? ` · ${prevPct}%` : ''}
                </span>
              </div>
              <div className="h-2 rounded-full bg-white/[0.06] overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-violet-500 to-brand-400 transition-all duration-500"
                  style={{ width: `${prevPct ?? 0}%` }}
                />
              </div>
            </div>
          ) : null}
        </div>
      )}

      {showChunkLine ? (
        <p className="text-[11px] text-[#71717a]">
          Частей с готовым превью для просмотра:{' '}
          <span className="text-[#d4d4d8] font-mono">
            {readyChunks} / {totalCh}
          </span>
        </p>
      ) : null}

      {ckLabel ? (
        <p className="text-[10px] text-[#52525b] font-mono leading-relaxed">{ckLabel}</p>
      ) : null}
    </div>
  );
}

function NonMode5ProgressDetail({ done, error, logBased, steps, logs }) {
  if (done || error) return null;
  const last = Array.isArray(logs) && logs.length > 0 ? logs[logs.length - 1] : null;
  const lastText = last?.text != null ? String(last.text).trim() : '';
  const shortLog =
    lastText.length > 220 ? `${lastText.slice(0, 217)}…` : lastText;

  if (logBased < 0) {
    return (
      <div className="mt-5 pt-4 border-t border-white/[0.08]">
        <p className="text-xs text-[#a1a1aa] leading-relaxed">
          Шкала обновится по мере появления записей в логе пайплайна ниже.
        </p>
      </div>
    );
  }

  const idx = Math.min(Math.max(0, logBased), steps.length - 1);
  const label = steps[idx]?.label || 'Этап';

  return (
    <div className="mt-5 pt-4 border-t border-white/[0.08] space-y-2">
      <p className="text-xs text-[#a1a1aa]">
        Ориентир по логу: <span className="text-white font-medium">{label}</span>
      </p>
      {shortLog ? (
        <div className="rounded-lg bg-[#14141c] border border-[#27272f] px-3 py-2">
          <p className="text-[10px] font-semibold text-[#71717a] uppercase tracking-wide mb-1">
            Последняя строка лога
          </p>
          <p className="text-xs text-[#d4d4d8] font-mono leading-relaxed break-words">{shortLog}</p>
        </div>
      ) : null}
    </div>
  );
}

function detectStep(logs, sessionMode) {
  if (sessionMode === 5) return -1;
  if (!logs.length) return -1;
  const joined = logs.map(l => l.text).join('\n');

  // Done - all modes support (3-10)
  if (joined.includes('LOCAL ONLY mode') || joined.includes('Pipeline DONE') || joined.includes('Mode 3 Pipeline DONE') || joined.includes('Mode 5 Pipeline DONE') || joined.includes('Mode 6 Pipeline DONE') || joined.includes('Mode 7 Pipeline DONE') || joined.includes('Mode 8 Pipeline DONE') || joined.includes('Mode 9 Pipeline DONE') || joined.includes('Mode 10 Pipeline DONE') || joined.includes('Mode12 DONE') || joined.includes('Mode12 CLIPS READY')) return STEPS.length - 1;
  
  // Video assembly (Mode 2 + Mode 3)
  if (
    joined.includes('Video Editor Agent') ||
    joined.includes('Assembling') ||
    joined.includes('Mode3 Assembler') ||
    joined.includes('Rendering →') ||
    joined.includes('assemble_video') ||
    joined.includes('Mode8 Assembler') ||
    joined.includes('Mode9 Assembler') ||
    joined.includes(' assembling ') ||
    joined.includes('Final video duration')
  ) return 5;
  
  // TTS / voiceover
  if (
    joined.includes('Synthesizing') ||
    joined.includes('[TTS]') ||
    joined.includes('voiceover')
  ) return 4;
  
  // Images (Mode 8 & 9 use FastGen for video generation with images)
  if (
    joined.includes('Image Generator Agent') ||
    joined.includes('ImageAgent') ||
    joined.includes('fast-gen') ||
    joined.includes('DALL-E') ||
    joined.includes('HuggingFace') ||
    joined.includes('[Mode8]') ||
    joined.includes('[Mode9]') ||
    joined.includes('Generating reference images') ||
    joined.includes('Generating video clips') ||
    joined.includes('Stage ') && joined.includes('image')
  ) return 3;
  
  // Fact check
  if (
    joined.includes('Fact Checker Agent') ||
    joined.includes('Fact check done') ||
    joined.includes('[FactChecker]')
  ) return 2;
  
  // Scenario (Mode 8 & 9)
  if (
    joined.includes('ScenarioWriter') ||
    joined.includes('Scenario Writer Agent') ||
    joined.includes('Scenario ready') ||
    joined.includes('Mode5 Scenario Writer') ||
    joined.includes('[Mode8] Scenario:') ||
    joined.includes('[Mode9] Scenario:') ||
    joined.includes('Building Stages:') ||
    joined.includes('Assembly Stages:') ||
    joined.includes('Generating Building Scenario') ||
    joined.includes('Generating Assembly Scenario')
  ) return 1;
  
  // Mode 3: prompt agent
  if (joined.includes('Mode3 Prompt') || joined.includes('Mode 3 Pipeline')) return 1;
  
  // Mode 6: relaxing video
  if (joined.includes('Mode6') || joined.includes('Mode 6 Pipeline')) return 3;  // images/video step
  // Mode 7: two clips (prompt → images → video)
  if (joined.includes('Mode7') || joined.includes('Mode 7 Pipeline')) return 3;
  // Mode 8: house building timelapse
  if (joined.includes('Mode8') || joined.includes('Mode 8 Pipeline')) return 3;
  // Mode 10: beach cleanup timelapse
  if (joined.includes('Mode10') || joined.includes('Mode 10 Pipeline')) return 3;
  
  // Fact miner
  if (
    joined.includes('Fact Miner Agent') ||
    joined.includes('[FactMiner]')
  ) return 0;

  return 0;
}

function mode5StepFromUiPhase(phaseRaw) {
  const phase = String(phaseRaw || '').trim();
  if (!phase) return null;
  if (Object.prototype.hasOwnProperty.call(MODE5_PHASE_TO_STEP, phase)) {
    return MODE5_PHASE_TO_STEP[phase];
  }
  if (phase.startsWith('checkpoint_')) {
    const tail = phase.slice('checkpoint_'.length);
    if (tail === 'after_images') return 4;
    if (tail === 'after_slices') return 5;
    if (tail === 'after_previews' || tail === 'completed') return 6;
  }
  return null;
}

/**
 * Mode 5: сервер отдаёт mode5_ui_phase, checkpoint и mode5_progress_hint в /review-state.
 * Индексы совпадают с MODE5_STEPS_TEMPLATE (0..6).
 */
function detectMode5Step(progress, awaitIntro) {
  if (awaitIntro) return 1;
  if (!progress || typeof progress !== 'object') return null;

  const fromPhase = mode5StepFromUiPhase(progress.uiPhase);
  if (fromPhase !== null && fromPhase !== undefined) return fromPhase;

  const hintRaw = String(progress.hint || '').trim();
  const hint = hintRaw.toLowerCase();
  const stage = String(progress.checkpoint || '').trim().toLowerCase();

  if (progress.planPending || hint.includes('первый план')) return 0;

  if (hint.includes('сначала проверьте')) return 1;

  /* Префлайт вступления: до подтверждения нет параллельной озвучки всего ролика */
  if (hint.includes('проверьте анимированные') && hint.includes('подтвердите продолжение')) return 1;
  if (hint.includes('подтвердите продолжение') && hint.includes('озвучк') && hint.includes('не запуск')) {
    return 1;
  }
  if (hint.includes('генерир') && hint.includes('анимированн') && hint.includes('превью')) return 0;

  if (hint.includes('параллельная озвучка')) return 2;
  if (hint.includes('озвучка на диске')) return 3;
  if (hint.includes('разметка и иллюстрации')) return 3;
  if (hint.includes('генерация картинок')) return 3;

  const segDone = Number(progress.segmentsImaged);
  const segTotal = Number(progress.segmentsTotal);
  if (Number.isFinite(segTotal) && segTotal > 0 && Number.isFinite(segDone) && segDone < segTotal) {
    return 3;
  }

  if (hint.includes('сборка превью')) return 5;

  const totalCh = Number(progress.totalChunks);
  const prevDone = Number(progress.previewsOnDisk);
  if (Number.isFinite(totalCh) && totalCh > 0 && Number.isFinite(prevDone) && prevDone < totalCh) {
    return 5;
  }

  if (stage === 'after_tts') return 3;
  if (stage === 'after_images') return 4;
  if (stage === 'after_slices') return 5;
  if (stage === 'after_previews') return 6;
  if (stage === 'completed') return 6;
  /* stub без подходящей подсказки — не угадываем «озвучку», остаёмся на «Старт» */
  if (stage === 'stub') return 0;

  return null;
}

export default function StepIndicator({
  logs,
  done,
  error,
  sessionMode,
  mode5ReviewProgress,
  mode5AwaitIntro = false,
  pipelineStatus = '',
}) {
  const steps =
    sessionMode === 5
      ? MODE5_STEPS_TEMPLATE.map((s, i) =>
          i === 1 && (mode5AwaitIntro || mode5IntroWaitFromHint(mode5ReviewProgress))
            ? { ...s, label: 'Проверка вступления', emoji: '🎞️' }
            : { ...s },
        )
      : STEPS;

  const mode5Idx =
    sessionMode === 5 ? detectMode5Step(mode5ReviewProgress || {}, mode5AwaitIntro) : null;
  const logBased = detectStep(logs, sessionMode);
  const current = done
    ? steps.length
    : error
      ? -1
      : sessionMode === 5
        ? (mode5Idx !== null && mode5Idx >= 0 ? mode5Idx : 0)
        : logBased;

  const mode5DisplayIndex =
    sessionMode === 5 ? (mode5Idx !== null && mode5Idx >= 0 ? mode5Idx : 0) : 0;

  return (
    <div className="w-full space-y-0">
    <div className="flex items-center gap-0 w-full">
      {steps.map((step, i) => {
        const isCompleted = current > i || done;
        const isActive    = current === i && !done;
        const isError     = error && i === current;

        return (
          <div key={step.id} className="flex items-center flex-1">
            {/* Node */}
            <div className="flex flex-col items-center gap-1.5 flex-shrink-0">
              <motion.div
                animate={isActive ? { scale: [1, 1.1, 1] } : {}}
                transition={{ repeat: Infinity, duration: 2 }}
                className={clsx(
                  'w-9 h-9 rounded-full flex items-center justify-center text-sm border transition-all duration-300 shadow-sm',
                  isCompleted && 'bg-gradient-to-b from-brand-500 to-brand-700 border-brand-400/40 text-white shadow-glow-sm',
                  isActive && 'bg-brand-600/25 border-brand-400/50 text-brand-300 ring-2 ring-brand-500/25',
                  isError && 'bg-red-950/50 border-red-500/60 text-red-400',
                  !isCompleted && !isActive && !isError && 'bg-white/[0.04] border-white/[0.1] text-[#6b6b7e]',
                )}
              >
                {isCompleted && !done ? (
                  <RiCheckLine className="text-sm" />
                ) : isActive ? (
                  <RiLoader4Line className="animate-spin text-sm" />
                ) : (
                  <span>{step.emoji}</span>
                )}
              </motion.div>
              <span className={clsx(
                'text-[10px] font-semibold whitespace-nowrap tracking-tight',
                isCompleted ? 'text-brand-400' : isActive ? 'text-white' : 'text-[#6b6b7e]',
              )}>
                {step.label}
              </span>
            </div>

            {/* Connector */}
            {i < steps.length - 1 && (
              <div className="flex-1 h-0.5 mx-1 mb-5 rounded-full bg-white/[0.08] overflow-hidden relative">
                <motion.div
                  className="absolute inset-y-0 left-0 bg-gradient-to-r from-brand-500 to-brand-400 rounded-full"
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: isCompleted ? 1 : 0 }}
                  transition={{ duration: 0.4 }}
                  style={{ transformOrigin: 'left', width: '100%' }}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>

    {sessionMode === 5 && !done && !error ? (
      <Mode5ProgressDetail
        stepIndex={mode5DisplayIndex}
        progress={mode5ReviewProgress || {}}
        awaitIntro={mode5AwaitIntro}
        pipelineStatus={pipelineStatus}
      />
    ) : null}

    {sessionMode !== 5 ? (
      <NonMode5ProgressDetail
        done={done}
        error={error}
        logBased={logBased}
        steps={steps}
        logs={logs}
      />
    ) : null}
    </div>
  );
}
