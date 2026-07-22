from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class EventSignal(BaseModel):
    event_type: str
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)

class InstructionSignal(BaseModel):
    instruction: str
    timestamp: datetime = Field(default_factory=utc_now)

class WorkflowInput(BaseModel):
    order_id: str
    supervisor_config_id: str
    base_instruction: str
    available_tools: List[str] = Field(default_factory=list)
    default_wake_up_behavior: Optional[str] = None
    memory_summary: str = ""
    wake_up_guidance: str = ""
    iteration_count: int = 0

class AgentWakeUpDecision(BaseModel):
    should_wake: bool
    reason: str

class AgentAction(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]

class AgentOutput(BaseModel):
    actions: List[AgentAction] = Field(default_factory=list)
    updated_memory: str
    sleep_duration_seconds: Optional[int] = None
    terminate_workflow: bool = False
    final_summary: Optional[str] = None
    key_learnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    wake_up_guidance: Optional[str] = None
