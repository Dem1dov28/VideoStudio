export function splitTextBlocks(text) {
  return String(text || '')
    .split(/\n\s*\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function normalizeMode4OnlyLang(outputLang, isMulticlip) {
  if (isMulticlip) return outputLang === 'en' ? 'en' : 'ru';
  return outputLang === 'both' ? null : outputLang;
}
