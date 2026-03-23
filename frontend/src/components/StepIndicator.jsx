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

  // Done
  if (joined.includes('LOCAL ONLY mode') || joined.includes('Pipeline DONE') || joined.includes('Mode 3 Pipeline DONE') || joined.includes('Mode 5 Pipeline DONE')) return STEPS.length - 1;
  // Video assembly (Mode 2 + Mode 3)
  if (
    joined.includes('Video Editor Agent') ||
    joined.includes('Assembling') ||
    joined.includes('Mode3 Assembler') ||
    joined.includes('Rendering →') ||
    joined.includes('assemble_video')
  ) return 5;
  // TTS / voiceover
  if (
    joined.includes('Synthesizing') ||
    joined.includes('[TTS]') ||
    joined.includes('voiceover')
  ) return 4;
  // Images
  if (
    joined.includes('Image Generator Agent') ||
    joined.includes('ImageAgent') ||
    joined.includes('fast-gen') ||
    joined.includes('DALL-E') ||
    joined.includes('HuggingFace')
  ) return 3;
  // Fact check
  if (
    joined.includes('Fact Checker Agent') ||
    joined.includes('Fact check done') ||
    joined.includes('[FactChecker]')
  ) return 2;
  // Scenario
  if (
    joined.includes('ScenarioWriter') ||
    joined.includes('Scenario Writer Agent') ||
    joined.includes('Scenario ready') ||
    joined.includes('Mode5 Scenario Writer')
  ) return 1;
  // Mode 3: prompt agent
  if (joined.includes('Mode3 Prompt') || joined.includes('Mode 3 Pipeline')) return 1;
  // Fact miner
  if (
    joined.includes('Fact Miner Agent') ||
    joined.includes('[FactMiner]')
  ) return 0;
  return 0;
}

export default function StepIndicator({ logs, done, error }) {
  const current = done ? STEPS.length : (error ? -1 : detectStep(logs));

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
                  'w-9 h-9 rounded-full flex items-center justify-center text-sm border-2 transition-all duration-300',
                  isCompleted && 'bg-brand-600 border-brand-600 text-white',
                  isActive    && 'bg-brand-600/20 border-brand-500 text-brand-400',
                  isError     && 'bg-red-900/30 border-red-500 text-red-400',
                  !isCompleted && !isActive && !isError && 'bg-[#1a1a24] border-[#27272f] text-[#52525b]',
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
                'text-[10px] font-medium whitespace-nowrap',
                isCompleted ? 'text-brand-400' : isActive ? 'text-[#e4e4f0]' : 'text-[#52525b]',
              )}>
                {step.label}
              </span>
            </div>

            {/* Connector */}
            {i < STEPS.length - 1 && (
              <div className="flex-1 h-px mx-1 mb-5">
                <motion.div
                  className="h-full bg-brand-600"
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: isCompleted ? 1 : 0 }}
                  transition={{ duration: 0.4 }}
                  style={{ transformOrigin: 'left' }}
                />
                {!isCompleted && <div className="h-full bg-[#27272f]" />}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
