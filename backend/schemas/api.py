from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class SupervisorConfigCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    base_instruction: str = Field(..., min_length=20, max_length=4000)
    available_tools: List[str] = Field(..., min_length=1)
    default_wake_up_behavior: Optional[str] = Field(default=None, max_length=1000)
    model_choice: Optional[str] = Field(default=None, max_length=120)

class SupervisorConfigResponse(SupervisorConfigCreate):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class OrderRunCreate(BaseModel):
    order_id: str = Field(..., min_length=2, max_length=80)
    supervisor_config_id: str = Field(..., min_length=1)

class OrderRunResponse(BaseModel):
    id: str
    order_id: str
    supervisor_config_id: str
    status: str
    sleep_state: str
    next_wake_at: Optional[datetime] = None
    memory_summary: Optional[str] = None
    final_summary: Optional[str] = None
    final_learnings: Optional[str] = None
    final_recommendations: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class EventCreate(BaseModel):
    event_type: str = Field(..., min_length=2, max_length=120)
    details: Dict[str, Any] = Field(default_factory=dict)

class InstructionCreate(BaseModel):
    instruction: str = Field(..., min_length=2, max_length=2000)

class ActivityLogResponse(BaseModel):
    id: int
    run_id: str
    activity_type: str
    details: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True
