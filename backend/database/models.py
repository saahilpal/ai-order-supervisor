from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from .session import Base

class SupervisorConfig(Base):
    """
    Stores supervisor templates defining base behavior.
    """
    __tablename__ = "supervisor_configs"

    id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    base_instruction = Column(String, nullable=False)
    available_tools = Column(JSON, nullable=False)  # List of tool names
    default_wake_up_behavior = Column(String, nullable=True)
    model_choice = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OrderRun(Base):
    """
    Represents a single long-running order workflow execution.
    """
    __tablename__ = "order_runs"

    id = Column(String, primary_key=True, index=True)  # This will also act as Temporal Workflow ID
    tenant_id = Column(String, nullable=False, index=True)
    supervisor_config_id = Column(String, ForeignKey("supervisor_configs.id"), nullable=False)
    order_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="running")  # running, paused, completed, terminated, failed
    sleep_state = Column(String, nullable=False, default="awake")  # awake, sleeping, paused, completed, terminated
    next_wake_at = Column(DateTime(timezone=True), nullable=True)
    memory_summary = Column(String, nullable=True)
    final_summary = Column(String, nullable=True)
    final_learnings = Column(String, nullable=True)
    final_recommendations = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    from sqlalchemy import Index
    __table_args__ = (
        Index("ix_order_runs_tenant_order", "tenant_id", "order_id"),
    )


class ActivityLog(Base):
    """
    Unified timeline for incoming events, wake/sleep decisions, tool actions, and instructions.
    """
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("order_runs.id"), nullable=False, index=True)
    activity_type = Column(String, nullable=False, index=True)  # event, agent_action, sleep_decision, manual_instruction
    details = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
