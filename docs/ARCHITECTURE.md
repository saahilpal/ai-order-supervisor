# Architecture

## Purpose
This document provides a high-level overview of the Order Supervisor architecture.

## Responsibilities
- Serve as an asynchronous, resilient, long-running agentic workflow engine.
- Isolate Temporal orchestration from business APIs and UI.

## Flow
1. **Frontend (Next.js)** sends a request to start a run via the **FastAPI Backend**.
2. The Backend validates the request, creates a database record, and kicks off an asynchronous **Temporal Workflow**.
3. The Temporal Workflow (`OrderSupervisorWorkflow`) enters a loop:
   - Evaluates incoming events and instructions using a lightweight LLM classifier.
   - If required, wakes the main LLM Agent to reason, plan, and execute business actions.
   - Calculates a sleep duration and sleeps until the next required wake-up or terminal event.
4. The database (`PostgreSQL`) acts as the source of truth for the frontend UI state, synchronized via Temporal activities.

## Trade-offs
- **Polling over WebSockets**: The frontend polls the backend for state updates. This simplifies infrastructure for a POC but would be replaced with SSE or WebSockets in a large-scale production app.
- **Fail-Open Classifier**: If the lightweight classifier fails due to an LLM provider outage, it defaults to waking the main agent to prevent dropping critical events.

## Future Improvements
- Multi-tenant data segregation.
- WebSocket-based realtime UI updates.
