# VideoEditor — структура проекта

## Оркестрация

```
orchestrator/
├── swarm.py          # Точка входа (run_pipeline, backward compat)
├── dispatcher.py     # Маршрутизация по mode (1–5)
├── tracker.py        # AgentExecutionTracker (timeout, retry)
├── swarm_graph.py    # LangGraph Swarm (Mode 1: Image→Video→Publisher)
├── pipelines/
│   └── mode1.py      # Mode 1 sequential pipeline
└── multi_agent/
    └── base.py       # Общие утилиты (checkpoint_if_control)
```

## Мультиагентные пайплайны

### Mode 1 — Scenario Writer (Top-5)
```
agents/scenario_writer/
├── agent.py          # run_scenario_writer_agent (multi/single)
├── types.py          # Scenario, ScenarioScene
└── multi_agent/
    ├── graph.py      # LangGraph: outline → scene (x5) → finalize
    └── prompts.py    # Промпты для OutlineAgent, SceneAgent
```

### Mode 5 — Long-form scenario
```
modes/mode5/
├── scenario_writer.py      # run_long_form_scenario_writer
└── multi_agent_scenario.py # LangGraph: structure → content (per subchapter) → coherence
```

### Fact Miner (Propose → Fetch → Extract)
```
agents/fact_miner/
├── agent.py    # run_fact_miner_agent (оркестрация)
├── types.py    # FactContext, SceneFactEvidence, ClaimCandidate
├── prompts.py  # MINER_SYSTEM, EXTRACT_SYSTEM
├── propose.py  # propose_claims (LLM)
├── fetch.py   # gather_evidence (Wikipedia, DuckDuckGo)
└── extract.py # extract_key_points (LLM)
```

## Агенты

```
agents/
├── scenario_writer/   # Сценарии для Mode 1 (multi-agent)
├── fact_miner/        # Факты по сценам (modular)
├── content_generator/ # Генерация изображений
│   ├── types.py       # EnrichedScene
│   ├── prompt_builder.py
│   ├── fastgen_scraper.py
│   └── agent.py
├── video_editor/      # Сборка видео (moviepy)
├── trends_analyzer/   # Тренды
├── publisher/         # Публикация (Postiz)
└── fact_checker/      # Проверка фактов
```

## Режимы (modes/)

| Mode | Описание | Pipeline |
|------|----------|----------|
| 1 | Top-5 фактов | orchestrator/pipelines/mode1.py |
| 2 | Почему X? | modes/mode2/pipeline.py |
| 3 | Восстановление домов | modes/mode3/pipeline.py |
| 4 | Цитата + фото | modes/mode4/pipeline.py |
| 5 | Длинные видео (~1 ч) | modes/mode5/pipeline.py |

## Зависимости между модулями

- `orchestrator.dispatcher` импортирует mode pipelines по требованию
- `orchestrator.pipelines.mode1` → agents (scenario_writer, fact_miner, content_generator, video_editor, publisher)
- Каждый mode self-contained: scenario/prompt → images → assemble
