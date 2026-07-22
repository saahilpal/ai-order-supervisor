# System Design

## Purpose
High-level system design of the Order Supervisor.

## Architecture Pattern
The system is built on an **Agentic Workflow Pattern** utilizing an Event-Driven architecture powered by Temporal.

## Components
1. **Database Layer (PostgreSQL)**: Handles persistent state tracking of order lifecycles and append-only activity logs.
2. **Backend API (FastAPI)**: Serves as the gateway for the frontend UI and mock external systems to inject signals.
3. **Orchestrator (Temporal)**: Manages long-running workflows, timers, and retries. Guarantees that the order workflow will not drop state even if the server crashes.
4. **Agent Brain (activities/agent.py & agent/core.py)**: Interacts with LLM providers to synthesize context, make decisions, and execute mocked tool calls.
5. **Frontend (Next.js)**: The control plane for human operators.

## Data Flow
- Events arrive at the API -> API signals Temporal workflow -> Workflow queues the event and potentially triggers the wake-up condition -> Temporal executes the Classifier activity -> If wake-up is required, Temporal executes the Inference activity -> Inference activity records business actions in the DB -> Temporal sleeps until next check.
