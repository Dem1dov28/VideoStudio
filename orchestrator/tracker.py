"""
Agent Execution Tracker — timeout, retry, error isolation, logging.

Multi-Agent Orchestration: Supervisor Pattern
- Per-agent timeout prevents blocking
- Exponential backoff retry
- Error isolation: one failure doesn't crash workflow
- Full execution traceability
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger


class AgentExecutionTracker:
    """Track agent execution with timeouts, retries, and error isolation."""

    def __init__(self, timeout: float = 300.0, max_retries: int = 1):
        self.timeout = timeout
        self.max_retries = max_retries
        self.execution_log: list[dict] = []

    async def execute(
        self,
        agent_name: str,
        agent_func: Any,
        *args: Any,
        **kwargs: Any,
    ) -> dict:
        """Execute agent with timeout, retry, and error isolation."""
        start_time = time.time()
        attempt = 0
        last_error: str | None = None

        while attempt <= self.max_retries:
            try:
                logger.info(f"[Orchestrator] Executing {agent_name} (attempt {attempt + 1})")
                result = await asyncio.wait_for(
                    agent_func(*args, **kwargs),
                    timeout=self.timeout,
                )

                execution_time = time.time() - start_time
                self.execution_log.append({
                    "agent": agent_name,
                    "status": "success",
                    "attempt": attempt + 1,
                    "duration": execution_time,
                    "timestamp": time.time(),
                })

                logger.success(f"[Orchestrator] {agent_name} completed in {execution_time:.2f}s")
                return {"success": True, "result": result, "agent": agent_name}

            except asyncio.TimeoutError:
                last_error = f"Timeout after {self.timeout}s"
                logger.warning(f"[Orchestrator] {agent_name} timeout (attempt {attempt + 1})")
            except Exception as e:
                last_error = str(e)
                logger.error(f"[Orchestrator] {agent_name} error: {e}")

            attempt += 1
            if attempt <= self.max_retries:
                wait_time = 2 ** attempt
                logger.info(f"[Orchestrator] Retrying {agent_name} in {wait_time}s...")
                await asyncio.sleep(wait_time)

        execution_time = time.time() - start_time
        self.execution_log.append({
            "agent": agent_name,
            "status": "failed",
            "error": last_error,
            "attempts": attempt,
            "duration": execution_time,
            "timestamp": time.time(),
        })

        logger.error(f"[Orchestrator] {agent_name} failed after {attempt} attempts")
        return {"success": False, "error": last_error, "agent": agent_name}

    def get_log(self) -> list[dict]:
        """Get execution log for monitoring/debugging."""
        return self.execution_log.copy()

    def get_summary(self) -> dict:
        """Get execution summary statistics."""
        total = len(self.execution_log)
        successful = sum(1 for e in self.execution_log if e["status"] == "success")
        failed = total - successful
        total_duration = sum(e.get("duration", 0) for e in self.execution_log)

        return {
            "total_agents": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total if total > 0 else 0,
            "total_duration": total_duration,
        }
