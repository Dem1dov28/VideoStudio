import { useState } from 'react';
import { FiChevronDown, FiChevronUp, FiEdit2, FiImage, FiMic, FiVideo } from 'react-icons/fi';
import clsx from 'clsx';

/* Auto-grow textarea ───────────────────────────────────────────────────────── */
function AutoTextarea({ value, onChange, placeholder, rows = 2, className = '' }) {
  return (
    <textarea
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      className={clsx(
        'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100',
        'placeholder-gray-500 focus:outline-none focus:border-indigo-500 resize-none leading-relaxed',
        className,
      )}
      onInput={e => {
        e.target.style.height = 'auto';
        e.target.style.height = e.target.scrollHeight + 'px';
      }}
    />
  );
}

/* Single scene card ────────────────────────────────────────────────────────── */
function SceneCard({ index, total, scene, onChange }) {
  const [open, setOpen] = useState(true);
  const [promptOpen, setPromptOpen] = useState(false);

  const set = (key, val) => onChange({ ...scene, [key]: val });

  return (
    <div className="border border-gray-700 rounded-xl overflow-hidden">
      {/* header */}
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-800 hover:bg-gray-750 transition-colors"
      >
        <span className="text-sm font-semibold text-gray-200">
          Сцена {index + 1} <span className="text-gray-500 font-normal">/ {total}</span>
        </span>
        {open ? <FiChevronUp className="text-gray-400" /> : <FiChevronDown className="text-gray-400" />}
      </button>

      {open && (
        <div className="p-4 space-y-4 bg-gray-850">
          {/* narration */}
          <div>
            <label className="flex items-center gap-1.5 text-xs font-medium text-indigo-400 mb-1.5">
              <FiMic size={12} /> Озвучка (narration)
            </label>
            <AutoTextarea
              value={scene.narration_text || ''}
              onChange={v => set('narration_text', v)}
              placeholder="Текст озвучки…"
              rows={3}
            />
          </div>

          {/* image_prompt (mode1) or video_search_query (mode2) */}
          <div>
            <button
              type="button"
              onClick={() => setPromptOpen(v => !v)}
              className="flex items-center gap-1.5 text-xs font-medium text-emerald-400 mb-1.5"
            >
              {scene.video_search_query !== undefined ? (
                <><FiVideo size={12} /> Поиск видео (Pexels)</>
              ) : (
                <><FiImage size={12} /> Промт для изображения</>
              )}
              {promptOpen
                ? <FiChevronUp size={12} />
                : <FiChevronDown size={12} />
              }
            </button>
            {promptOpen && (
              <AutoTextarea
                value={scene.video_search_query ?? scene.image_prompt ?? ''}
                onChange={v => scene.video_search_query !== undefined
                  ? set('video_search_query', v)
                  : set('image_prompt', v)}
                placeholder={scene.video_search_query !== undefined
                  ? 'English query for stock video…'
                  : 'Описание изображения для AI…'}
                rows={2}
                className="font-mono text-xs"
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* Main editor component ────────────────────────────────────────────────────── */
export default function ScenarioEditor({ scenario, onChange }) {
  const setField = (key, val) => onChange({ ...scenario, [key]: val });

  const setScene = (idx, updatedScene) => {
    const scenes = [...scenario.scenes];
    scenes[idx] = updatedScene;
    onChange({ ...scenario, scenes });
  };

  return (
    <div className="space-y-6">
      {/* header section */}
      <div className="border border-gray-700 rounded-xl overflow-hidden">
        <div className="px-4 py-3 bg-gray-800 flex items-center gap-2">
          <FiEdit2 size={14} className="text-indigo-400" />
          <span className="text-sm font-semibold text-gray-200">Заголовок и структура</span>
        </div>
        <div className="p-4 space-y-4 bg-gray-850">
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">Название видео</label>
            <input
              type="text"
              value={scenario.title || ''}
              onChange={e => setField('title', e.target.value)}
              placeholder="Название…"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm
                         text-gray-100 placeholder-gray-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">Хук (открывающая фраза)</label>
            <AutoTextarea
              value={scenario.hook || ''}
              onChange={v => setField('hook', v)}
              placeholder="Интригующая открывающая фраза…"
              rows={2}
            />
          </div>

        </div>
      </div>

      {/* scenes */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-300">
          Сцены ({(scenario.scenes || []).length})
        </h3>
        {(scenario.scenes || []).map((scene, idx) => (
          <SceneCard
            key={idx}
            index={idx}
            total={(scenario.scenes || []).length}
            scene={scene}
            onChange={updated => setScene(idx, updated)}
          />
        ))}
      </div>
    </div>
  );
}
