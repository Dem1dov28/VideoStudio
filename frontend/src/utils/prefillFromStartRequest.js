/**
 * Map saved StartRequest (from pipeline / topics history) into Generate.jsx form setters.
 * @param {Record<string, unknown>} req
 * @param {Record<string, Function>} f
 * @param {{ houseTypes?: { id: string; label: string }[] }} [options]
 */
export function applyStartRequestToForm(req, f, options = {}) {
  if (!req || typeof req !== 'object') return;
  let m = Number(req.mode);
  if (!Number.isFinite(m) || m < 1 || m > 13) return;

  if (m === 12) {
    const manual = Array.isArray(req.mode12_segments)
      ? req.mode12_segments.map((s) => String(s).trim()).filter(Boolean)
      : [];
    const parable =
      typeof req.mode12_parable_text === 'string' ? req.mode12_parable_text.trim() : '';
    let quote = '';
    let segments = null;
    let multiclip = true;
    if (manual.length >= 2) {
      quote = manual.join('\n\n');
      segments = manual;
    } else if (manual.length === 1) {
      quote = manual[0];
      multiclip = false;
    } else {
      quote = parable;
    }
    req = {
      ...req,
      mode: 4,
      mode4_quote: quote,
      mode4_photo_path: req.mode12_jesus_photo_path,
      mode4_only_lang: req.mode12_only_lang === 'en' ? 'en' : 'ru',
      mode4_segments: multiclip ? segments : null,
      mode4_multiclip: multiclip,
      mode4_skip_final_assembly: multiclip ? true : req.mode4_skip_final_assembly,
      mode4_subtitle_style: 'karaoke',
      language: 'both',
    };
    m = 4;
  }

  const { houseTypes = [] } = options;

  f.setMode?.(m);
  f.setStep?.('form');

  if (m !== 13 && typeof req.show_subtitles === 'boolean') f.setShowSubtitles?.(req.show_subtitles);
  if (typeof req.local_only === 'boolean') f.setLocalOnly?.(req.local_only);
  if (req.language === 'ru' || req.language === 'en') f.setLang?.(req.language);

  if (typeof req.num_scenes === 'number' && req.num_scenes >= 1) {
    if (m === 1 || m === 2 || m === 6) f.setScenes?.(req.num_scenes);
  }
  if (typeof req.use_scenario === 'boolean') f.setScenario?.(req.use_scenario);
  if (m === 1 || m === 2) {
    if (typeof req.topic === 'string' && req.topic.trim()) f.setTopic?.(req.topic.trim());
    if (req.scenario && typeof req.scenario === 'object') f.setScenario2?.(req.scenario);
  }
  if (m === 2 && req.reference_image_path) {
    f.setReferenceImage?.({ path: String(req.reference_image_path), preview: null });
  }

  if (m === 3) {
    const start = req.mode3_start_image_path;
    const end = req.mode3_end_image_path;
    const topicLabel = req.mode3_topic;
    if (start && end) {
      f.setMode3InputMode?.('upload');
      f.setMode3StartImage?.({ path: String(start), preview: null });
      f.setMode3EndImage?.({ path: String(end), preview: null });
    } else if (topicLabel && String(topicLabel).trim()) {
      f.setMode3InputMode?.('type');
      const id = houseTypes.find((h) => h.label === String(topicLabel).trim())?.id;
      if (id) f.setMode3HouseType?.(id);
    }
  }

  if (m === 4) {
    const segs = Array.isArray(req.mode4_segments)
      ? req.mode4_segments.map((s) => String(s).trim()).filter(Boolean)
      : [];
    if (segs.length >= 2) f.setMode4Quote?.(segs.join('\n\n'));
    else if (typeof req.mode4_quote === 'string') f.setMode4Quote?.(req.mode4_quote);
    if (typeof req.mode4_person_name === 'string') f.setMode4PersonName?.(req.mode4_person_name);
    if (req.mode4_photo_path) f.setMode4Photo?.({ path: String(req.mode4_photo_path), preview: null });
    const ol = req.mode4_only_lang;
    if (ol === 'ru' || ol === 'en') f.setMode4OutputLang?.(ol);
    else f.setMode4OutputLang?.('both');
    if (typeof req.mode4_show_author_on_video === 'boolean') {
      f.setMode4ShowAuthorOnVideo?.(req.mode4_show_author_on_video);
    }
    if (typeof req.mode4_video_header_title === 'string' && req.mode4_video_header_title.trim()) {
      f.setMode4HeaderTitle?.(req.mode4_video_header_title.trim());
    } else {
      f.setMode4HeaderTitle?.('');
    }
    const st = req.mode4_subtitle_style;
    if (st === 'plain_whisper' || st === 'karaoke') f.setMode4SubtitleStyle?.(st);
    const lh = typeof req.mode4_location_hint === 'string' ? req.mode4_location_hint.trim() : '';
    f.setMode4LocationHint?.(lh);
    f.setMode4LocationOptions?.(lh ? [lh] : []);
  }

  if (m === 5) {
    if (typeof req.mode5_script_text === 'string') f.setMode5Script?.(req.mode5_script_text);
    if (req.mode5_language === 'ru' || req.mode5_language === 'en' || req.mode5_language === 'auto') f.setMode5Lang?.(req.mode5_language);
    else if (req.language === 'ru' || req.language === 'en' || req.language === 'auto') f.setMode5Lang?.(req.language);
    const cs = Number(req.mode5_chunk_seconds);
    if (Number.isFinite(cs) && cs >= 120) f.setMode5ChunkSeconds?.(Math.min(900, cs));
    const ss = Number(req.mode5_segment_seconds);
    if (Number.isFinite(ss) && ss >= 10) f.setMode5SegmentSeconds?.(Math.min(90, ss));
    const mpi = Number(req.mode5_max_parallel_images);
    if (Number.isFinite(mpi) && mpi >= 1) f.setMode5MaxParallelImages?.(Math.min(10, mpi));
    const ib = String(req.mode5_image_backend || '').trim().toLowerCase();
    if (ib === 'api' || ib === 'playwright') f.setMode5ImageBackend?.(ib);
    else if (ib === 'auto') f.setMode5ImageBackend?.('api');
    if (typeof req.mode5_video_header_title === 'string') f.setMode5HeaderTitle?.(req.mode5_video_header_title);
    const sm5 = req.mode5_sub_mode;
    if (
      sm5 === 'manual' ||
      sm5 === 'bible' ||
      sm5 === 'facts50' ||
      sm5 === 'outline' ||
      sm5 === 'book_night' ||
      sm5 === 'unwritten_chapter'
    ) {
      f.setMode5SubMode?.(sm5);
    }
    else if (req.mode5_bible_mode === true) f.setMode5SubMode?.('bible');
    else f.setMode5SubMode?.('manual');
    if (req.mode5_test_run === true) f.setMode5TestRun?.(true);
    else if (req.mode5_test_run === false) f.setMode5TestRun?.(false);
  }

  if (m === 6) {
    const n = Number(req.mode6_num_characters);
    if (Number.isFinite(n) && n >= 1) f.setMode6NumCharacters?.(n);
  }

  if (m === 7) {
    const at = req.mode7_animal_type;
    f.setMode7AnimalType?.(at && String(at).trim() ? String(at).trim() : 'random');
    const kb = Array.isArray(req.mode7_keyboards) ? req.mode7_keyboards.map(String) : [];
    if (kb.length >= 3) f.setMode7Keyboards?.(kb);
    const nk = typeof req.num_scenes === 'number' ? req.num_scenes : kb.length || 4;
    if (nk >= 3 && nk <= 4) f.setMode7NumKeyboards?.(nk);
  }

  if (m === 8) {
    const hs = req.mode8_house_style;
    f.setMode8HouseStyle?.(hs && String(hs).trim() ? String(hs).trim() : 'random');
    const loc = req.mode8_location;
    f.setMode8Location?.(loc && String(loc).trim() ? String(loc).trim() : 'random');
    const ns = Number(req.mode8_num_stages ?? req.num_scenes);
    if (Number.isFinite(ns) && ns >= 1) f.setMode8NumStages?.(ns);
    const nf = Number(req.mode8_num_floors);
    if (Number.isFinite(nf) && nf >= 1) f.setMode8NumFloors?.(nf);
  }

  if (m === 9) {
    const vt = req.mode9_vehicle_type;
    f.setMode9VehicleType?.(vt && String(vt).trim() ? String(vt).trim() : 'random');
    const loc = req.mode9_location;
    f.setMode9Location?.(loc && String(loc).trim() ? String(loc).trim() : 'random');
    const ns = Number(req.mode9_num_stages ?? req.num_scenes);
    if (Number.isFinite(ns) && ns >= 1) f.setMode9NumStages?.(ns);
  }

  if (m === 10) {
    const bt = req.mode10_beach_type;
    f.setMode10BeachType?.(bt && String(bt).trim() ? String(bt).trim() : 'tropical');
    const cs = req.mode10_coast_setting;
    f.setMode10CoastSetting?.(cs && String(cs).trim() ? String(cs).trim() : 'morning_calm');
    const ns = Number(req.mode10_num_stages ?? req.num_scenes);
    if (Number.isFinite(ns) && ns >= 1) f.setMode10NumStages?.(ns);
  }

  if (m === 11) {
    const st = req.mode11_structure_type;
    if (st && String(st).trim()) f.setMode11StructureType?.(String(st).trim());
    const ns = Number(req.mode11_num_stages ?? req.num_scenes);
    if (Number.isFinite(ns) && ns >= 1) f.setMode11NumStages?.(ns);
  }

  if (m === 13) {
    if (req.mode13_audio_path) {
      f.setMode13Audio?.({ path: String(req.mode13_audio_path), name: '' });
    }
    const vp = req.mode13_voice_preset;
    if (
      vp === 'original' ||
      vp === 'studio' ||
      vp === 'calm' ||
      vp === 'natural' ||
      vp === 'soft' ||
      vp === 'medium' ||
      vp === 'strong'
    ) {
      f.setMode13VoicePreset?.(vp);
    }
    const wl = req.mode13_language;
    if (wl === 'ru' || wl === 'en') {
      f.setMode13WhisperLang?.(wl);
    } else {
      f.setMode13WhisperLang?.('');
    }
    const m13h = req.mode13_video_header_title;
    if (typeof m13h === 'string') {
      f.setMode13HeaderTitle?.(m13h);
    }
    if (typeof req.mode13_show_subtitles === 'boolean') {
      f.setMode13ShowSubtitles?.(req.mode13_show_subtitles);
    }
    const gDb = Number(req.mode13_voice_gain_db);
    if (Number.isFinite(gDb)) {
      f.setMode13GainDb?.(Math.max(-12, Math.min(12, gDb)));
    }
    const tSc = Number(req.mode13_voice_tempo_scale);
    if (Number.isFinite(tSc)) {
      f.setMode13TempoPct?.(Math.max(85, Math.min(115, Math.round(tSc * 100))));
    }
    const pSt = Number(req.mode13_voice_pitch_semitones);
    if (Number.isFinite(pSt)) {
      f.setMode13PitchSemi?.(Math.max(-6, Math.min(6, pSt)));
    }
    const ai = Number(req.mode13_voice_ai_cleanup);
    if (Number.isFinite(ai)) {
      f.setMode13AiCleanup?.(Math.max(0, Math.min(100, ai)));
    }
    const ns = Number(req.mode13_voice_noise_suppression);
    if (Number.isFinite(ns)) {
      f.setMode13NoiseSupp?.(Math.max(0, Math.min(100, ns)));
    }
    const ln = Number(req.mode13_voice_level_normalize);
    if (Number.isFinite(ln)) {
      f.setMode13LevelNorm?.(Math.max(0, Math.min(100, ln)));
    }
    const ds = Number(req.mode13_voice_deesser);
    if (Number.isFinite(ds)) {
      f.setMode13Deesser?.(Math.max(0, Math.min(100, ds)));
    }
    const cl = Number(req.mode13_voice_clarity);
    if (Number.isFinite(cl)) {
      f.setMode13Clarity?.(Math.max(0, Math.min(100, cl)));
    }
    const mc = Number(req.mode13_voice_mud_cut);
    if (Number.isFinite(mc)) {
      f.setMode13MudCut?.(Math.max(0, Math.min(100, mc)));
    }
    const cp = Number(req.mode13_voice_compression);
    if (Number.isFinite(cp)) {
      f.setMode13Compression?.(Math.max(0, Math.min(100, cp)));
    }
    const hp = req.mode13_voice_highpass_hz;
    if (hp == null || hp === '') {
      f.setMode13HpAuto?.(true);
    } else {
      const h = Number(hp);
      if (Number.isFinite(h) && h >= 40) {
        f.setMode13HpAuto?.(false);
        f.setMode13HighpassHz?.(Math.min(200, h));
      }
    }
  }

}
