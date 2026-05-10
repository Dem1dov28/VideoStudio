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

function detectStep(logs) {
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

  // Mode 5 long-form: без DONE ещё не «Готово», но лог уже помечает пайплайн
  if (joined.includes('Mode 5 Pipeline') && !joined.includes('Mode 5 Pipeline DONE')) return 1;

  return 0;
}

/**
 * Mode 5: сервер отдаёт checkpoint и mode5_progress_hint в /review-state — надёжнее, чем парсить логи.
 * Индекс — текущий активный шаг (как в detectStep).
 */
function detectMode5Step(progress) {
  if (!progress || typeof progress !== 'object') return null;
  const hintRaw = String(progress.hint || '').trim();
  const hint = hintRaw.toLowerCase();
  const stage = String(progress.checkpoint || '').trim().toLowerCase();

  if (progress.planPending || hint.includes('первый план')) return 1;

  if (hint.includes('параллельная озвучка')) return 4;
  if (hint.includes('озвучка на диске')) return 3;
  if (hint.includes('разметка и иллюстрации')) return 1;
  if (hint.includes('генерация картинок')) return 3;
  if (hint.includes('сборка превью')) return 5;

  const segDone = Number(progress.segmentsImaged);
  const segTotal = Number(progress.segmentsTotal);
  if (Number.isFinite(segTotal) && segTotal > 0 && Number.isFinite(segDone) && segDone < segTotal) {
    return 3;
  }

  const totalCh = Number(progress.totalChunks);
  const prevDone = Number(progress.previewsOnDisk);
  if (Number.isFinite(totalCh) && totalCh > 0 && Number.isFinite(prevDone) && prevDone < totalCh) {
    return 5;
  }

  if (stage === 'stub') return 4;
  if (stage === 'after_tts') return 3;
  if (stage === 'after_images' || stage === 'after_slices') return 5;
  if (stage === 'after_previews') return 5;
  if (stage === 'completed') return 6;

  return null;
}

export default function StepIndicator({ logs, done, error, sessionMode, mode5ReviewProgress }) {
  const mode5Idx =
    sessionMode === 5 && mode5ReviewProgress ? detectMode5Step(mode5ReviewProgress) : null;
  const logBased = detectStep(logs);
  const current = done
    ? STEPS.length
    : error
      ? -1
      : mode5Idx !== null && mode5Idx >= 0
        ? mode5Idx
        : logBased;

  return (
    <div className="flex items-center gap-0 w-full">
      {STEPS.map((step, i) => {
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
            {i < STEPS.length - 1 && (
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
  );
}
