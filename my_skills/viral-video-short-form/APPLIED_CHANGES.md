# Viral Short-Form Video Master — Applied to VideoStudio

## Skill Overview
Complete short-form video optimization for TikTok, Instagram Reels, YouTube Shorts, and Facebook Reels based on 2025-2026 algorithm updates.

---

## Changes Applied

### 1. Scenario Writer Agent (`agents/scenario_writer/agent.py`)

**Added Viral Principles:**
- **1.3-Second Hook Rule**: Hooks must stop scroll instantly
- **3/8/12 Rule**: Capture by 3s, deepen by 8s, deliver by 12s
- **Completion Rate Targets**: 80-90% = viral distribution
- **Micro-Niche Focus**: 2.5x better distribution with specific targeting

**Enhanced Hook Rules:**
- Reduced max words: 10 → 8 (shorter = stronger)
- Added pattern interrupt guidance
- High-performing hook templates in Russian:
  - "Вот что скрывают про..."
  - "Топ-5 фактов о... которые шокируют"
  - "Никто не говорит о..."

**Enhanced Outro Rules:**
- Reduced max words: 15 → 12
- Strong CTA templates:
  - "Подпишись — будет ещё жёстче"
  - "Лайк если не знал"
  - "Жми сохранить, пригодится"

---

### 2. Publisher Agent (`agents/publisher/agent.py`)

**Updated Hashtag Strategy:**
- Old: 10-15 broad hashtags
- New: 3-5 highly relevant hashtags (quality over quantity)
- Mix: 1-2 niche + 1-2 category + 0-1 broad

**Added Platform-Specific Guidance:**
- **Instagram (Dec 2025)**: Keywords in caption > hashtags
- **TikTok**: Caption text helps algorithm categorize
- **YouTube Shorts**: Include #Shorts, 55s content = 3x views

---

### 3. Configuration (`config.py`)

**Added Video Length Context:**
- YouTube Shorts: 50-60s optimal (55s = 3x views)
- Instagram Reels: 7-30s viral, 30-90s engagement
- TikTok: 15-60s, 15-30s peak performance

---

## Key Metrics from Skill

| Platform | Optimal Length | Key Signal |
|----------|---------------|------------|
| TikTok | 15-30s | Replays (highest weight) |
| YouTube Shorts | 50-60s | Completion rate |
| Instagram Reels | 7-30s | Sends per reach (DM shares) |

---

## Algorithm Priorities (2025-2026)

1. **Watch Time / Completion Rate** — Highest weight across all platforms
2. **Replays** — TikTok's #1 signal
3. **Shares** — Especially DM shares on Instagram
4. **Micro-Niche Targeting** — 2.5x distribution boost
5. **First 1.3 Seconds** — Scroll-stop critical

---

## Files Modified

- `agents/scenario_writer/agent.py` — Hook/outro rules, viral principles
- `agents/publisher/agent.py` — Hashtag strategy, platform guidance
- `config.py` — Video length documentation

---

## Reference Documents

- `references/tiktok-algorithm-2026.md`
- `references/youtube-shorts-2026.md`
- `references/instagram-reels-2026.md`
