"""
Orchestrator — backward compatibility re-exports.

Structure:
  orchestrator/
    tracker.py      — AgentExecutionTracker
    swarm_graph.py  — LangGraph Swarm (Image→Video→Publisher)
    dispatcher.py   — run_pipeline (mode routing)
    pipelines/
      mode1.py      — Mode 1 sequential pipeline
    multi_agent/
      base.py       — shared utilities for multi-agent workflows
"""

from orchestrator.dispatcher import run_pipeline
from orchestrator.tracker import AgentExecutionTracker
from orchestrator.swarm_graph import (
    _SWARM_AVAILABLE,
    build_swarm_graph,
    run_swarm_pipeline,
)

__all__ = [
    "run_pipeline",
    "AgentExecutionTracker",
    "_SWARM_AVAILABLE",
    "build_swarm_graph",
    "run_swarm_pipeline",
]
