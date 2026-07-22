"""
Temporal activities for Order Supervisor.

Graceful failure policy
────────────────────────
  • LLM errors NEVER propagate as raw exceptions that would exhaust Temporal retries
    and kill the workflow.
  • Transient errors (rate limit, timeout, connection) are retried by Temporal's
    built-in retry policy in workflow.py.
  • Persistent errors fall back to a safe AgentOutput that keeps the workflow alive
    and records the failure in the activity timeline.
  • The classifier defaults to should_wake=True on error (fail open > fail closed).
"""

import logging
from typing import Any, Dict, List
from datetime import datetime

from temporalio import activity
from temporalio.exceptions import ApplicationError

from agent.errors import LLMAuthenticationError, LLMConfigurationError, LLMError
from agent.core import run_classifier_logic, run_agent_inference_logic
from database.session import AsyncSessionLocal
from database.models import OrderRun, ActivityLog
from schemas.workflow import (
    AgentOutput,
    AgentWakeUpDecision,
    EventSignal,
    InstructionSignal,
)
from sqlalchemy import select, update

logger = logging.getLogger("order_supervisor.activities")

# ── Graceful fallback helpers ─────────────────────────────────────────────────

async def _record_llm_error(run_id: str, error: LLMError) -> None:
    """Write an agent_error entry to the activity timeline."""
    async with AsyncSessionLocal() as db:
        entry = ActivityLog(
            run_id=run_id,
            activity_type="agent_error",
            details={
                "error_code": error.error_code,
                "user_message": error.user_message,
                "provider": getattr(error.original_error, "__class__.__name__", "unknown"),
            },
        )
        db.add(entry)
        await db.commit()


def _is_non_retryable(error: LLMError) -> bool:
    """Auth and configuration errors won't self-heal — mark as non-retryable."""
    return isinstance(error, (LLMAuthenticationError, LLMConfigurationError))


# ── Activities ────────────────────────────────────────────────────────────────

@activity.defn
async def run_classifier(
    memory_summary: str, wake_up_guidance: str, recent_events: List[EventSignal]
) -> AgentWakeUpDecision:
    """
    Lightweight classifier: decide if the main agent needs to wake up.

    Failure policy:
      • Non-retryable errors (auth, config) → raise ApplicationError (Temporal won't retry)
      • All other errors → default to should_wake=True (fail open — better to
        wake unnecessarily than to miss a critical event)
    """
    try:
        return await run_classifier_logic(memory_summary, wake_up_guidance, recent_events)
    except LLMError as exc:
        logger.warning(
            f"Classifier LLM error ({exc.error_code}): {exc}. Defaulting to wake=True."
        )
        if _is_non_retryable(exc):
            raise ApplicationError(
                exc.user_message,
                exc.error_code,
                non_retryable=True,
            ) from exc
        # Fail open: wake the agent so events are not silently dropped
        return AgentWakeUpDecision(should_wake=True)


@activity.defn
async def run_agent_inference(
    run_id: str,
    base_instruction: str,
    memory_summary: str,
    events: List[EventSignal],
    instructions: List[InstructionSignal],
    available_tools: List[str],
) -> AgentOutput:
    """
    Main agent reasoning loop: classify situation → decide actions → update memory.

    Failure policy:
      • Non-retryable errors (auth, config) → raise ApplicationError
      • Transient errors → raise plain exception so Temporal retries per retry policy
      • After 2 retries still failing → return degraded AgentOutput that records
        the failure and keeps the workflow alive, sleeping 5 minutes before retry
    """
    # Log wake-up in DB
    async with AsyncSessionLocal() as db:
        db.add(ActivityLog(
            run_id=run_id,
            activity_type="agent_wakeup",
            details={"events_count": len(events), "instructions_count": len(instructions)},
        ))
        await db.commit()

    try:
        agent_output = await run_agent_inference_logic(
            run_id, base_instruction, memory_summary, events, instructions, available_tools
        )

    except LLMError as exc:
        logger.error(
            f"Agent inference LLM error ({exc.error_code}) for run {run_id}: {exc}"
        )

        # Non-retryable: surface to Temporal as ApplicationError
        if _is_non_retryable(exc):
            await _record_llm_error(run_id, exc)
            raise ApplicationError(
                exc.user_message,
                exc.error_code,
                non_retryable=True,
            ) from exc

        # Transient: let Temporal retry the activity
        # (retry policy in workflow.py: max_attempts=3)
        activity_info = activity.info()
        attempt = activity_info.attempt
        if attempt < 3:
            logger.info(f"Attempt {attempt}/3 failed — Temporal will retry.")
            raise  # re-raise so Temporal schedules a retry

        # Exhausted retries: degrade gracefully — keep workflow alive
        await _record_llm_error(run_id, exc)

        degraded_memory = (
            memory_summary
            + f"\n\n⚠ LLM temporarily unavailable ({exc.error_code}). "
            f"Will retry in 5 minutes."
        )
        agent_output = AgentOutput(
            actions=[],
            updated_memory=degraded_memory,
            sleep_duration_seconds=300,   # retry in 5 minutes
            terminate_workflow=False,
        )
        logger.warning(
            f"Run {run_id}: returning degraded AgentOutput after exhausted retries."
        )

    # Log sleep/termination decision
    async with AsyncSessionLocal() as db:
        db.add(ActivityLog(
            run_id=run_id,
            activity_type="agent_sleep_decision",
            details={
                "terminate_workflow": agent_output.terminate_workflow,
                "sleep_duration_seconds": agent_output.sleep_duration_seconds,
                "actions_count": len(agent_output.actions),
            },
        ))
        await db.commit()

    return agent_output


@activity.defn
async def execute_business_action(
    run_id: str, tool_name: str, arguments: Dict[str, Any]
) -> str:
    """
    Execute a business action (mocked external integration).
    Records the action in the activity timeline.
    """
    async with AsyncSessionLocal() as db:
        db.add(ActivityLog(
            run_id=run_id,
            activity_type="agent_action",
            details={"tool_name": tool_name, "arguments": arguments},
        ))
        await db.commit()

    activity.logger.info(f"Executed tool '{tool_name}' for run {run_id}")
    return f"Successfully executed {tool_name}"


@activity.defn
async def update_run_state(
    run_id: str,
    status: str,
    memory_summary: str,
    sleep_state: str = "awake",
    next_wake_at: str | None = None,
    final_summary: str | None = None,
    final_learnings: str | None = None,
    final_recommendations: str | None = None,
) -> None:
    """Update the OrderRun status, memory, sleep state, and final output."""
    parsed_next_wake_at = datetime.fromisoformat(next_wake_at) if next_wake_at else None

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(OrderRun)
            .where(OrderRun.id == run_id)
            .values(
                status=status,
                memory_summary=memory_summary,
                sleep_state=sleep_state,
                next_wake_at=parsed_next_wake_at,
                final_summary=final_summary,
                final_learnings=final_learnings,
                final_recommendations=final_recommendations,
            )
        )
        if final_summary or final_learnings or final_recommendations:
            existing_final_output = await db.execute(
                select(ActivityLog.id).where(
                    ActivityLog.run_id == run_id,
                    ActivityLog.activity_type == "final_output",
                )
            )
            if existing_final_output.scalar_one_or_none():
                await db.commit()
                return
            db.add(ActivityLog(
                run_id=run_id,
                activity_type="final_output",
                details={
                    "final_summary": final_summary,
                    "key_learnings": final_learnings,
                    "recommendations": final_recommendations,
                },
            ))
        await db.commit()
