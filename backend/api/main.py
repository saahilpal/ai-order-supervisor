from fastapi import FastAPI, HTTPException, Depends, Request, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update
from typing import List
import uuid
import logging

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import WorkflowAlreadyStartedError

from database.session import get_db
from database.models import SupervisorConfig, OrderRun, ActivityLog
from schemas.api import (
    SupervisorConfigCreate, SupervisorConfigResponse,
    OrderRunCreate, OrderRunResponse,
    EventCreate, InstructionCreate, ActivityLogResponse
)
from schemas.workflow import WorkflowInput, EventSignal, InstructionSignal
from temporal.workflow import OrderSupervisorWorkflow

from agent.startup import verify_provider
from agent.errors import LLMError

app = FastAPI(title="Order Supervisor API")
logger = logging.getLogger("order_supervisor.api")

SUPPORTED_TOOLS = {
    "message_fulfillment_team",
    "message_payments_team",
    "message_logistics_team",
    "message_customer",
    "create_internal_note",
}

TERMINAL_EVENT_TYPES = {"delivered", "cancelled", "order_cancelled"}

def get_tenant_id(x_tenant_id: str = Header("demo", description="Tenant ID for data isolation")) -> str:
    """Dependency to extract and require the X-Tenant-ID header for multi-tenancy."""
    tenant_id = x_tenant_id.strip()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID cannot be empty")
    return tenant_id

def require_temporal_client() -> Client:
    if temporal_client is None:
        raise HTTPException(
            status_code=503,
            detail="Temporal client is not ready. Start Temporal and retry.",
        )
    return temporal_client

@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError):
    return JSONResponse(
        status_code=503, # Service Unavailable or Gateway Timeout depending on the error, but 503 is a safe default
        content=exc.to_dict(),
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Temporal Client Instance
temporal_client = None

@app.on_event("startup")
async def startup_event():
    global temporal_client
    # Connect to local Temporal server
    temporal_client = await Client.connect(
        "localhost:7233",
        data_converter=pydantic_data_converter,
    )
    
    # Verify the LLM provider configuration before accepting requests
    import logging
    logger = logging.getLogger("order_supervisor.startup")
    logger.info("Starting provider verification...")
    await verify_provider()
    logger.info("Provider verification successful.")

@app.post("/api/supervisors", response_model=SupervisorConfigResponse)
async def create_supervisor(config: SupervisorConfigCreate, db: AsyncSession = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    unsupported_tools = [tool for tool in config.available_tools if tool not in SUPPORTED_TOOLS]
    if unsupported_tools:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported tools: {', '.join(unsupported_tools)}",
        )

    config_id = str(uuid.uuid4())
    db_config = SupervisorConfig(
        id=config_id,
        tenant_id=tenant_id,
        name=config.name,
        base_instruction=config.base_instruction,
        available_tools=list(dict.fromkeys(config.available_tools)),
        default_wake_up_behavior=config.default_wake_up_behavior,
        model_choice=config.model_choice
    )
    db.add(db_config)
    await db.commit()
    await db.refresh(db_config)
    return db_config

@app.get("/api/supervisors/{config_id}", response_model=SupervisorConfigResponse)
async def get_supervisor(config_id: str, db: AsyncSession = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    result = await db.execute(select(SupervisorConfig).where(SupervisorConfig.id == config_id, SupervisorConfig.tenant_id == tenant_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Supervisor config not found")
    return config

@app.get("/api/supervisors", response_model=List[SupervisorConfigResponse])
async def list_supervisors(db: AsyncSession = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    result = await db.execute(select(SupervisorConfig).where(SupervisorConfig.tenant_id == tenant_id))
    return result.scalars().all()

@app.post("/api/runs", response_model=OrderRunResponse)
async def start_run(run: OrderRunCreate, db: AsyncSession = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    client = require_temporal_client()

    # Verify config exists
    config = await get_supervisor(run.supervisor_config_id, db, tenant_id)

    existing_result = await db.execute(
        select(OrderRun).where(
            OrderRun.tenant_id == tenant_id,
            OrderRun.order_id == run.order_id,
            OrderRun.status.in_(["running", "paused", "terminating"]),
        )
    )
    existing_run = existing_result.scalar_one_or_none()
    if existing_run:
        raise HTTPException(
            status_code=409,
            detail=f"Order {run.order_id} already has an active supervisor run.",
        )
    
    run_id = f"order-supervisor-{run.order_id}-{str(uuid.uuid4())[:8]}"
    
    # Store initial run in DB
    db_run = OrderRun(
        id=run_id,
        tenant_id=tenant_id,
        supervisor_config_id=run.supervisor_config_id,
        order_id=run.order_id,
        status="running",
        sleep_state="awake",
    )
    db.add(db_run)
    await db.commit()
    await db.refresh(db_run)

    # Start Temporal Workflow
    workflow_input = WorkflowInput(
        order_id=run.order_id,
        supervisor_config_id=run.supervisor_config_id,
        base_instruction=config.base_instruction,
        available_tools=config.available_tools,
        default_wake_up_behavior=config.default_wake_up_behavior,
    )
    try:
        await client.start_workflow(
            OrderSupervisorWorkflow.run,
            workflow_input,
            id=run_id,
            task_queue="order-supervisor-queue"
        )
    except WorkflowAlreadyStartedError:
        logger.info("Workflow already started", extra={"run_id": run_id})
    except Exception as exc:
        logger.error("Failed to start Temporal workflow", extra={"run_id": run_id, "error_type": type(exc).__name__})
        await db.execute(
            update(OrderRun)
            .where(OrderRun.id == run_id)
            .values(status="failed", sleep_state="failed", memory_summary="Workflow could not be started.")
        )
        db.add(ActivityLog(
            run_id=run_id,
            activity_type="workflow_error",
            details={"message": "Temporal workflow could not be started.", "error_type": type(exc).__name__},
        ))
        await db.commit()
        raise HTTPException(
            status_code=503,
            detail="Temporal workflow could not be started. Verify Temporal is running and retry.",
        ) from exc
        
    return db_run

@app.get("/api/runs", response_model=List[OrderRunResponse])
async def list_runs(db: AsyncSession = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    result = await db.execute(select(OrderRun).where(OrderRun.tenant_id == tenant_id).order_by(OrderRun.created_at.desc()))
    return result.scalars().all()

@app.get("/api/runs/{run_id}", response_model=OrderRunResponse)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    result = await db.execute(select(OrderRun).where(OrderRun.id == run_id, OrderRun.tenant_id == tenant_id))
    db_run = result.scalar_one_or_none()
    if not db_run:
        raise HTTPException(status_code=404, detail="Run not found")
    return db_run

@app.get("/api/runs/{run_id}/activities", response_model=List[ActivityLogResponse])
async def get_run_activities(run_id: str, db: AsyncSession = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    await get_run(run_id, db, tenant_id) # Enforce tenant authorization
    result = await db.execute(select(ActivityLog).where(ActivityLog.run_id == run_id).order_by(ActivityLog.created_at.asc()))
    return result.scalars().all()

@app.post("/api/runs/{run_id}/events")
async def send_event(run_id: str, event: EventCreate, db: AsyncSession = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    client = require_temporal_client()
    db_run = await get_run(run_id, db, tenant_id) # Enforce tenant authorization
    if db_run.status in {"completed", "terminated", "failed", "terminating"}:
        raise HTTPException(status_code=409, detail=f"Run is {db_run.status}; events can no longer be injected.")
    
    # Log event in DB directly as an activity for the timeline
    db_event = ActivityLog(
        run_id=run_id,
        activity_type="event",
        details={
            "event_type": event.event_type,
            "details": event.details,
            "is_terminal": event.event_type in TERMINAL_EVENT_TYPES,
        }
    )
    db.add(db_event)
    await db.commit()

    # Send signal to workflow
    handle = client.get_workflow_handle(run_id)
    signal = EventSignal(event_type=event.event_type, details=event.details)
    await handle.signal(OrderSupervisorWorkflow.receive_event, signal)
    
    return {"status": "event_sent"}

@app.post("/api/runs/{run_id}/instructions")
async def send_instruction(run_id: str, instruction: InstructionCreate, db: AsyncSession = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    client = require_temporal_client()
    db_run = await get_run(run_id, db, tenant_id) # Enforce tenant authorization
    if db_run.status in {"completed", "terminated", "failed", "terminating"}:
        raise HTTPException(status_code=409, detail=f"Run is {db_run.status}; instructions can no longer be sent.")
    
    db_event = ActivityLog(
        run_id=run_id,
        activity_type="manual_instruction",
        details={"instruction": instruction.instruction}
    )
    db.add(db_event)
    await db.commit()

    handle = client.get_workflow_handle(run_id)
    signal = InstructionSignal(instruction=instruction.instruction)
    await handle.signal(OrderSupervisorWorkflow.receive_instruction, signal)
    
    return {"status": "instruction_sent"}

@app.post("/api/runs/{run_id}/interrupt")
async def interrupt_run(run_id: str, db: AsyncSession = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    client = require_temporal_client()
    db_run = await get_run(run_id, db, tenant_id) # Enforce tenant authorization
    if db_run.status != "running":
        raise HTTPException(status_code=409, detail=f"Only running runs can be paused. Current status: {db_run.status}.")
    handle = client.get_workflow_handle(run_id)
    await handle.signal(OrderSupervisorWorkflow.pause)
    await db.execute(
        update(OrderRun)
        .where(OrderRun.id == run_id)
        .values(status="paused", sleep_state="paused", next_wake_at=None)
    )
    db.add(ActivityLog(run_id=run_id, activity_type="run_paused", details={"source": "api"}))
    await db.commit()
    return {"status": "paused"}

@app.post("/api/runs/{run_id}/resume")
async def resume_run(run_id: str, db: AsyncSession = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    client = require_temporal_client()
    db_run = await get_run(run_id, db, tenant_id) # Enforce tenant authorization
    if db_run.status != "paused":
        raise HTTPException(status_code=409, detail=f"Only paused runs can be resumed. Current status: {db_run.status}.")
    handle = client.get_workflow_handle(run_id)
    await handle.signal(OrderSupervisorWorkflow.resume)
    await db.execute(
        update(OrderRun)
        .where(OrderRun.id == run_id)
        .values(status="running", sleep_state="awake", next_wake_at=None)
    )
    db.add(ActivityLog(run_id=run_id, activity_type="run_resumed", details={"source": "api"}))
    await db.commit()
    return {"status": "resumed"}

@app.post("/api/runs/{run_id}/terminate")
async def terminate_run(run_id: str, db: AsyncSession = Depends(get_db), tenant_id: str = Depends(get_tenant_id)):
    client = require_temporal_client()
    db_run = await get_run(run_id, db, tenant_id) # Enforce tenant authorization
    if db_run.status in {"completed", "terminated", "failed"}:
        return {"status": db_run.status}
    handle = client.get_workflow_handle(run_id)
    await handle.signal(OrderSupervisorWorkflow.terminate)
    await db.execute(
        update(OrderRun)
        .where(OrderRun.id == run_id)
        .values(status="terminating", sleep_state="terminated", next_wake_at=None)
    )
    db.add(ActivityLog(run_id=run_id, activity_type="run_terminated", details={"source": "api"}))
    await db.commit()
    return {"status": "terminating"}
