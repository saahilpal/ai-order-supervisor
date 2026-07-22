from unittest.mock import patch

import pytest
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from activities.agent import run_classifier
from agent.errors import LLMModelNotFoundError
from agent.provider import get_llm_provider
from schemas.workflow import WorkflowInput, AgentOutput, AgentWakeUpDecision, EventSignal
from temporal.workflow import OrderSupervisorWorkflow, get_workflow_state_for_update


# Mock Activities
@activity.defn(name="update_run_state")
async def mock_update_run_state(
    run_id: str,
    status: str,
    memory_summary: str,
    sleep_state: str = "awake",
    next_wake_at: str | None = None,
    final_summary: str | None = None,
    final_learnings: str | None = None,
    final_recommendations: str | None = None,
) -> None:
    pass

@activity.defn(name="run_classifier")
async def mock_run_classifier(memory_summary: str, recent_events: list) -> AgentWakeUpDecision:
    # Always wake up for tests
    return AgentWakeUpDecision(should_wake=True, reason="test")

@activity.defn(name="run_agent_inference")
async def mock_run_agent_inference(
    run_id: str,
    base_instruction: str,
    memory_summary: str,
    events: list,
    instructions: list,
    available_tools: list,
) -> AgentOutput:
    terminal_event_seen = any(
        (
            event.get("event_type")
            if isinstance(event, dict)
            else getattr(event, "event_type", None)
        )
        == "delivered"
        for event in events
    )
    return AgentOutput(
        actions=[],
        updated_memory="Test completed" if terminal_event_seen else "Waiting for delivery",
        sleep_duration_seconds=10,
        terminate_workflow=terminal_event_seen,
        final_summary="Delivered successfully" if terminal_event_seen else None,
        key_learnings=["Terminal events complete the workflow"] if terminal_event_seen else [],
        recommendations=["No follow-up required"] if terminal_event_seen else [],
    )

@activity.defn(name="execute_business_action")
async def mock_execute_business_action(run_id: str, tool_name: str, arguments: dict) -> str:
    return "Mock executed"


@pytest.mark.asyncio
async def test_order_supervisor_workflow():
    # Provide a real Temporal environment that runs isolated in-memory for testing
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter,
    ) as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[OrderSupervisorWorkflow],
            activities=[
                mock_update_run_state,
                mock_run_classifier,
                mock_run_agent_inference,
                mock_execute_business_action,
            ],
        ):
            input_data = WorkflowInput(
                order_id="ORD-TEST-001",
                supervisor_config_id="CONFIG-1",
                base_instruction="You are a test supervisor.",
            )

            handle = await env.client.start_workflow(
                OrderSupervisorWorkflow.run,
                input_data,
                id="test-workflow-id",
                task_queue="test-queue",
            )

            await handle.signal(
                OrderSupervisorWorkflow.receive_event,
                EventSignal(event_type="delivered", details={}),
            )
            result = await handle.result()
            
            assert "Workflow completed" in result
            assert "Delivered successfully" in result


def test_provider_uses_repo_dotenv_model(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "llama3.1:8b")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    provider = get_llm_provider()

    assert provider.model_name == "gemma4:latest"


def test_paused_workflow_keeps_paused_state():
    status, sleep_state = get_workflow_state_for_update(is_paused=True, manual_termination_requested=False, default_sleep_state="sleeping")

    assert status == "paused"
    assert sleep_state == "paused"


@pytest.mark.asyncio
async def test_classifier_fallback_returns_reason(monkeypatch):
    async def raise_error(*args, **kwargs):
        raise LLMModelNotFoundError(
            "model not found",
            user_message="model missing",
        )

    monkeypatch.setattr("activities.agent.run_classifier_logic", raise_error)

    decision = await run_classifier("memory", "guidance", [])

    assert decision.should_wake is True
    assert decision.reason
