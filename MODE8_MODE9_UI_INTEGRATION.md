# Mode8 & Mode9 UI Integration Guide

## ✅ Completed Changes

### StepIndicator Component Updates

The `StepIndicator` component in `frontend/src/components/StepIndicator.jsx` has been updated to properly detect and display progress for **Mode 8 (House Building Timelapse)** and **Mode 9 (Vehicle Assembly Timelapse)**.

## 📊 Step Detection Logic

### Step 0: Факты (Facts) 🔍
- Detects: `Fact Miner Agent`, `[FactMiner]`
- **Mode 8/9**: Not applicable (these modes skip fact mining)

### Step 1: Сценарий (Scenario) ✍️
**Detection patterns:**
- `ScenarioWriter`, `Scenario Writer Agent`, `Scenario ready`
- `Mode5 Scenario Writer`
- **`[Mode8] Scenario:`** ← NEW
- **`[Mode9] Scenario:`** ← NEW
- **`Building Stages:`** ← NEW
- **`Assembly Stages:`** ← NEW
- **`Generating Building Scenario`** ← NEW
- **`Generating Assembly Scenario`** ← NEW
- `Mode3 Prompt`, `Mode 3 Pipeline`

### Step 2: Проверка (Fact Check) 🧪
- Detects: `Fact Checker Agent`, `Fact check done`, `[FactChecker]`
- **Mode 8/9**: Not applicable (these modes skip fact checking)

### Step 3: Картинки (Images) 🖼️
**Detection patterns:**
- `Image Generator Agent`, `ImageAgent`, `fast-gen`, `DALL-E`, `HuggingFace`
- **`[Mode8]`** ← NEW (any Mode8 log with this prefix)
- **`[Mode9]`** ← NEW (any Mode9 log with this prefix)
- **`Generating reference images`** ← NEW
- **`Generating video clips`** ← NEW
- **`Stage ` + `image`** ← NEW (e.g., "Stage 1 image generation")

### Step 4: Озвучка (Voiceover) 🎙️
- Detects: `Synthesizing`, `[TTS]`, `voiceover`
- **Mode 8/9**: Not applicable (these modes don't use TTS)

### Step 5: Видео (Video Assembly) 🎬
**Detection patterns:**
- `Video Editor Agent`, `Assembling`, `Mode3 Assembler`, `Rendering →`, `assemble_video`
- **`Mode8 Assembler`** ← NEW
- **`Mode9 Assembler`** ← NEW
- **` assembling `** ← NEW
- **`Final video duration`** ← NEW

### Step 6: Готово (Done) ✅
**Detection patterns:**
- `LOCAL ONLY mode`, `Pipeline DONE`, `Mode 3 Pipeline DONE`, `Mode 5 Pipeline DONE`
- **`Mode 8 Pipeline DONE`** ← NEW
- **`Mode 9 Pipeline DONE`** ← NEW

## 🎯 Expected Flow for Mode8 & Mode9

### Mode 8: House Building Timelapse
```
Step 0 (skip) → Step 1 → Step 3 → Step 5 → Step 6
   ↓              ↓         ↓         ↓         ↓
 Facts      Scenario   Images    Video     Done
           [Building]  [FastGen] [Assemble]
```

**Example Log Messages:**
1. `=== Mode 8 Pipeline | House Building Timelapse | session=...`
2. `Step 1/4 - Generating Building Scenario...` → **Step 1**
3. `[Mode8] Scenario: Modern House Construction | ...` → **Step 1**
4. `Step 2/4 - House Video Generator (Sequential Images + Keyframe Videos)` → **Step 3**
5. `[Mode8] Generating reference images SEQUENTIALLY...` → **Step 3**
6. `[Mode8] Stage 1 image: Empty Land...` → **Step 3**
7. `[Mode8] Generated 6/6 videos (includes final drone showcase)` → **Step 3**
8. `Step 3/4 - Video Assembly` → **Step 5**
9. `[Mode8] Final video duration: 45.23s` → **Step 5**
10. `Step 4/4 - Generating Clickbait Title + Publishing Metadata` → **Step 5**
11. `=== Mode 8 Pipeline DONE | video=...` → **Step 6**

### Mode 9: Vehicle Assembly Timelapse
```
Step 0 (skip) → Step 1 → Step 3 → Step 5 → Step 6
   ↓              ↓         ↓         ↓         ↓
 Facts      Scenario   Images    Video     Done
          [Assembly]  [FastGen] [Assemble]
```

**Example Log Messages:**
1. `=== Mode 9 Pipeline | Vehicle Assembly Timelapse | session=...`
2. `Step 1/4 - Generating Assembly Scenario...` → **Step 1**
3. `[Mode9] Scenario: Airplane Assembly | ...` → **Step 1**
4. `Step 2/4 - Vehicle Video Generator (Sequential Images + Keyframe Videos)` → **Step 3**
5. `[Mode9] Generating reference images SEQUENTIALLY...` → **Step 3**
6. `[Mode9] Stage 1 image: Empty Space...` → **Step 3**
7. `[Mode9] Generated 6/6 videos (includes final drone showcase)` → **Step 3**
8. `Step 3/4 - Video Assembly` → **Step 5**
9. `[Mode9] Final video duration: 52.18s` → **Step 5**
10. `Step 4/4 - Generating Clickbait Title + Publishing Metadata` → **Step 5**
11. `=== Mode 9 Pipeline DONE | video=...` → **Step 6**

## 🔍 Key Differences from Other Modes

### Modes 1, 2, 5, 6, 7:
- Use full pipeline: Facts → Scenario → Fact Check → Images → Voiceover → Video

### Mode 3:
- Uses: Scenario → Images → Voiceover → Video (skips facts & fact check)

### **Modes 8 & 9:**
- Use: **Scenario → Images → Video** (skips facts, fact check, and voiceover)
- Image generation uses **FastGen sequential chaining** with reference images
- No TTS/voiceover (uses ambient sounds: construction/assembly)

## 🎨 UI Behavior

When running Mode 8 or Mode 9:

1. **Initial State**: All steps show as inactive (gray)
2. **Scenario Generation**: First node animates and highlights (✍️ Сценарий)
3. **Image/Video Generation**: Third node activates (🖼️ Картинки)
   - Shows spinner animation
   - Connector line fills progressively
4. **Video Assembly**: Fifth node activates (🎬 Видео)
   - Previous nodes show checkmarks ✓
5. **Completion**: Final node shows (✅ Готово)
   - All previous nodes show checkmarks ✓
   - All connector lines filled (brand color)
   - Video player appears below

## 🧪 Testing Checklist

- [x] StepIndicator detects `[Mode8] Scenario:` logs
- [x] StepIndicator detects `[Mode9] Scenario:` logs
- [x] StepIndicator detects `[Mode8]` and `[Mode9]` image generation logs
- [x] StepIndicator detects `Mode 8 Pipeline DONE` and `Mode 9 Pipeline DONE`
- [x] StepIndicator detects video assembly logs for both modes
- [ ] **Test Mode 8 live run** - verify step progression
- [ ] **Test Mode 9 live run** - verify step progression
- [ ] Verify connector line animations work correctly
- [ ] Verify emoji display for each step
- [ ] Verify error state handling (if pipeline fails)

## 🚀 How to Test

1. **Start the frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

2. **Start the backend:**
   ```bash
   uvicorn server:app --reload --port 8000
   ```

3. **Navigate to Generate page** and select:
   - Mode 8: House Timelapse 🏗️
   - Mode 9: Vehicle Assembly 🚗

4. **Configure options** and click "Запустить"

5. **Observe StepIndicator:**
   - Should progress through steps: 1 → 3 → 5 → 6
   - Each active step should show spinner animation
   - Completed steps should show checkmark ✓
   - Connector lines should fill progressively

## 📝 Notes

- Mode 8 and Mode 9 **skip Steps 0, 2, and 4** (Facts, Fact Check, Voiceover)
- This is **by design** - these modes focus on visual timelapse content
- The step indicator will show the correct progression based on log detection
- If steps don't progress correctly, check browser console for log messages

## 🐛 Troubleshooting

If the step indicator doesn't update:

1. **Check browser console** for log messages
2. **Verify WebSocket connection** is active (check Network tab)
3. **Ensure log format** matches expected patterns:
   - `[Mode8]` or `[Mode9]` prefixes
   - `Scenario:`, `Generating`, ` assembling `, etc.
4. **Restart backend** if logs are not being sent

## 📚 Related Files

- `frontend/src/components/StepIndicator.jsx` - Updated step detection logic
- `frontend/src/pages/Progress.jsx` - Progress page with step indicator
- `modes/mode8/pipeline.py` - Mode 8 pipeline implementation
- `modes/mode9/pipeline.py` - Mode 9 pipeline implementation
- `orchestrator/dispatcher.py` - Pipeline routing
