import pytest
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from schemas.workflow import WorkflowInput, AgentOutput, AgentWakeUpDecision, EventSignal
from temporal.workflow import OrderSupervisorWorkflow


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
