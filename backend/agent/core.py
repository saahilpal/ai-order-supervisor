from agent.provider import get_llm_provider
from schemas.workflow import AgentWakeUpDecision, AgentOutput, EventSignal, InstructionSignal
from typing import List
import json

SUPPORTED_TOOLS = {
    "message_fulfillment_team": "Notify fulfillment about picking, packing, stock, or warehouse handling.",
    "message_payments_team": "Ask payments to investigate payment failures, refunds, or charge issues.",
    "message_logistics_team": "Escalate carrier, tracking, delay, or delivery problems.",
    "message_customer": "Draft a direct customer update.",
    "create_internal_note": "Record context or a decision for internal teams.",
}

MIN_SLEEP_SECONDS = 60
MAX_SLEEP_SECONDS = 7 * 24 * 60 * 60

async def run_classifier_logic(memory_summary: str, wake_up_guidance: str, recent_events: List[EventSignal]) -> AgentWakeUpDecision:
    provider = get_llm_provider()
    
    events_text = "\n".join([f"- {e.event_type} at {e.timestamp}: {json.dumps(e.details, default=str)}" for e in recent_events])
    
    system_prompt = """
    You are a lightweight classifier for an Order Supervisor AI.
    Your job is to decide if the main AI agent needs to wake up and intervene based on recent events.
    Wake up the agent IF:
    - An error occurred (e.g. payment_failed, shipment_delayed)
    - A critical milestone requires attention (e.g. refund_requested, customer_message_received)
    - The events match the explicit wake-up guidance provided by the main agent.
    - You are unsure.
    Do NOT wake up the agent IF:
    - The events are routine progress (e.g. order_created, shipment_created, payment_confirmed) 
      AND the memory summary does not indicate any special handling is needed for them.
    """
    
    user_prompt = f"Memory Summary:\n{memory_summary}\n\nWake-Up Guidance:\n{wake_up_guidance}\n\nRecent Events:\n{events_text}"
    
    # We use the pydantic schema directly as the schema definition for the LLM
    result_dict = await provider.call(system_prompt, user_prompt, AgentWakeUpDecision)
    return AgentWakeUpDecision(**result_dict)

async def run_agent_inference_logic(
    run_id: str,
    base_instruction: str,
    memory_summary: str,
    events: List[EventSignal],
    instructions: List[InstructionSignal],
    available_tools: List[str],
) -> AgentOutput:
    provider = get_llm_provider()
    
    events_text = "\n".join([f"- {e.event_type} at {e.timestamp}: {json.dumps(e.details, default=str)}" for e in events])
    instructions_text = "\n".join([f"- {i.instruction} at {i.timestamp}" for i in instructions])
    allowed_tools = [tool for tool in available_tools if tool in SUPPORTED_TOOLS] or list(SUPPORTED_TOOLS.keys())
    tools_text = "\n".join(f"- {tool}: {SUPPORTED_TOOLS[tool]}" for tool in allowed_tools)
    
    system_prompt = f"""
    You are the core intelligence of the Order Supervisor AI.
    Your job is to read the current memory, recent events, and manual instructions, then decide on actions.

    Base Supervisor Instruction:
    {base_instruction}

    Available tools you can call:
    {tools_text}

    You must output a JSON object conforming exactly to the requested schema.
    If the order reaches a terminal state such as delivered or cancelled, set `terminate_workflow` to true and provide:
    - `final_summary`
    - `key_learnings`
    - `recommendations`
    Otherwise, determine how long to sleep before the next review. Use seconds between 60 and 604800.
    Provide `wake_up_guidance` to instruct the lightweight classifier on what specific events should wake you up before the sleep duration expires.
    Always return concise `updated_memory` tracking order state, open risks, last action, and next review plan.
    """
    
    user_prompt = f"Memory:\n{memory_summary}\n\nNew Events:\n{events_text}\n\nNew Manual Instructions:\n{instructions_text}"
    
    result_dict = await provider.call(system_prompt, user_prompt, AgentOutput)
    output = AgentOutput(**result_dict)
    output.actions = [action for action in output.actions if action.tool_name in allowed_tools]

    if output.sleep_duration_seconds is not None:
        output.sleep_duration_seconds = max(
            MIN_SLEEP_SECONDS,
            min(output.sleep_duration_seconds, MAX_SLEEP_SECONDS),
        )

    return output
