from datetime import timedelta
import asyncio
from typing import List

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import schemas and activities inside imports_passed_through so Temporal's
# determinism sandbox can see them at workflow-registration time.
with workflow.unsafe.imports_passed_through():
    from schemas.workflow import WorkflowInput, EventSignal, InstructionSignal, AgentOutput
    from activities.agent import run_classifier, run_agent_inference, execute_business_action, update_run_state


DEFAULT_SLEEP_SECONDS = 24 * 60 * 60
CONTINUE_AS_NEW_EVERY = 100
TERMINAL_EVENT_TYPES = {"delivered", "cancelled", "order_cancelled"}


def get_workflow_state_for_update(
    *,
    is_paused: bool,
    manual_termination_requested: bool,
    default_sleep_state: str,
) -> tuple[str, str]:
    if is_paused:
        return "paused", "paused"
    if manual_termination_requested:
        return "terminating", "terminated"
    return "running", default_sleep_state


@workflow.defn
class OrderSupervisorWorkflow:
    def __init__(self) -> None:
        self.events_queue: List[EventSignal] = []
        self.instructions_queue: List[InstructionSignal] = []
        self.memory_summary: str = ""
        self.wake_up_guidance: str = ""
        self.is_paused: bool = False
        self.manual_termination_requested: bool = False
        self.completed_by_terminal_event: bool = False
        self.should_wake_up: bool = False
        self.run_id: str = ""
        self.iteration_count: int = 0
        self.final_summary: str | None = None
        self.final_learnings: str | None = None
        self.final_recommendations: str | None = None

    @workflow.signal
    def receive_event(self, event: EventSignal) -> None:
        self.events_queue.append(event)
        if event.event_type in TERMINAL_EVENT_TYPES:
            self.should_wake_up = True

    @workflow.signal
    def receive_instruction(self, instruction: InstructionSignal) -> None:
        self.instructions_queue.append(instruction)
        self.should_wake_up = True

    @workflow.signal
    def pause(self) -> None:
        self.is_paused = True
        self.should_wake_up = True

    @workflow.signal
    def resume(self) -> None:
        self.is_paused = False
        self.should_wake_up = True

    @workflow.signal
    def terminate(self) -> None:
        self.manual_termination_requested = True
        self.should_wake_up = True

    @workflow.run
    async def run(self, input_data: WorkflowInput) -> str:
        workflow.logger.info(
            f"Started OrderSupervisorWorkflow for order {input_data.order_id}, iteration {input_data.iteration_count}"
        )
        self.run_id = workflow.info().workflow_id
        self.memory_summary = input_data.memory_summary
        self.wake_up_guidance = input_data.wake_up_guidance
        self.iteration_count = input_data.iteration_count

        if self.iteration_count == 0:
            status, sleep_state = get_workflow_state_for_update(
                is_paused=False,
                manual_termination_requested=False,
                default_sleep_state="awake",
            )
            await workflow.execute_activity(
                update_run_state,
                args=[self.run_id, status, self.memory_summary, sleep_state, None],
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

        sleep_duration = timedelta(seconds=DEFAULT_SLEEP_SECONDS)
        self.should_wake_up = True

        while not self.manual_termination_requested and not self.completed_by_terminal_event:
            if self.is_paused:
                await workflow.wait_condition(
                    lambda: not self.is_paused or self.manual_termination_requested
                )
                continue

            try:
                await workflow.wait_condition(
                    lambda: self.should_wake_up
                    or len(self.events_queue) > 0
                    or self.manual_termination_requested,
                    timeout=sleep_duration,
                )
            except asyncio.TimeoutError:
                self.should_wake_up = True

            if self.manual_termination_requested:
                break

            if self.is_paused:
                self.should_wake_up = False
                continue

            terminal_event_seen = any(
                event.event_type in TERMINAL_EVENT_TYPES for event in self.events_queue
            )
            if terminal_event_seen:
                self.should_wake_up = True

            if self.events_queue and not self.should_wake_up:
                recent_events = self.events_queue.copy()
                decision = await workflow.execute_activity(
                    run_classifier,
                    args=[self.memory_summary, self.wake_up_guidance, recent_events],
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                if decision.should_wake:
                    self.should_wake_up = True
                else:
                    self.events_queue.clear()

            if self.should_wake_up:
                self.should_wake_up = False

                events_to_process = self.events_queue.copy()
                self.events_queue.clear()

                instructions_to_process = self.instructions_queue.copy()
                self.instructions_queue.clear()

                agent_output: AgentOutput = await workflow.execute_activity(
                    run_agent_inference,
                    args=[
                        self.run_id,
                        input_data.base_instruction,
                        self.memory_summary,
                        events_to_process,
                        instructions_to_process,
                        input_data.available_tools,
                    ],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )

                for action in agent_output.actions:
                    await workflow.execute_activity(
                        execute_business_action,
                        args=[self.run_id, action.tool_name, action.arguments],
                        start_to_close_timeout=timedelta(seconds=30),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )

                self.memory_summary = agent_output.updated_memory
                if agent_output.wake_up_guidance:
                    self.wake_up_guidance = agent_output.wake_up_guidance
                self.final_summary = agent_output.final_summary or self.final_summary
                if agent_output.key_learnings:
                    self.final_learnings = "\n".join(agent_output.key_learnings)
                if agent_output.recommendations:
                    self.final_recommendations = "\n".join(agent_output.recommendations)

                processed_terminal_event = any(
                    event.event_type in TERMINAL_EVENT_TYPES for event in events_to_process
                )
                if processed_terminal_event:
                    self.completed_by_terminal_event = True
                    break

                if agent_output.sleep_duration_seconds:
                    sleep_duration = timedelta(seconds=agent_output.sleep_duration_seconds)
                else:
                    sleep_duration = timedelta(seconds=DEFAULT_SLEEP_SECONDS)

                if agent_output.terminate_workflow:
                    self.memory_summary = (
                        f"{self.memory_summary}\n\n"
                        "Agent recommended closure; workflow remains open until a terminal event or manual termination."
                    )

                if not self.is_paused:
                    status, sleep_state = get_workflow_state_for_update(
                        is_paused=self.is_paused,
                        manual_termination_requested=self.manual_termination_requested,
                        default_sleep_state="sleeping",
                    )
                    next_wake_at = workflow.now() + sleep_duration
                    await workflow.execute_activity(
                        update_run_state,
                        args=[
                            self.run_id,
                            status,
                            self.memory_summary,
                            sleep_state,
                            next_wake_at.isoformat(),
                        ],
                        start_to_close_timeout=timedelta(seconds=10),
                        retry_policy=RetryPolicy(maximum_attempts=3),
                    )

            self.iteration_count += 1
            if self.iteration_count >= CONTINUE_AS_NEW_EVERY and not self.manual_termination_requested:
                workflow.logger.info(
                    f"Workflow reached {self.iteration_count} iterations. Continuing as new to compact history."
                )
                workflow.continue_as_new(
                    WorkflowInput(
                        order_id=input_data.order_id,
                        supervisor_config_id=input_data.supervisor_config_id,
                        base_instruction=input_data.base_instruction,
                        available_tools=input_data.available_tools,
                        default_wake_up_behavior=input_data.default_wake_up_behavior,
                        memory_summary=self.memory_summary,
                        wake_up_guidance=self.wake_up_guidance,
                        iteration_count=0,
                    )
                )

        status = "terminated" if self.manual_termination_requested else "completed"
        sleep_state = "terminated" if self.manual_termination_requested else "completed"
        final_summary = self.final_summary or self.memory_summary or (
            "Run ended before the agent produced a memory summary."
        )
        final_learnings = self.final_learnings or (
            "Manual termination." if self.manual_termination_requested else "Order reached a terminal lifecycle event."
        )
        final_recommendations = self.final_recommendations or "Review the timeline for follow-up actions."

        await workflow.execute_activity(
            update_run_state,
            args=[
                self.run_id,
                status,
                self.memory_summary,
                sleep_state,
                None,
                final_summary,
                final_learnings,
                final_recommendations,
            ],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        return f"Workflow {status}. Final summary: {final_summary}"
