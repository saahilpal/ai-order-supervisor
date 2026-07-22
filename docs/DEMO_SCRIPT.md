# Demo Script

Step-by-step script for recording the walkthrough video.

---

## Before You Start

Open five terminal tabs and run one command per tab:

```bash
# Tab 1 — Temporal
temporal server start-dev --headless

# Tab 2 — PostgreSQL
docker compose up -d postgres

# Tab 3 — Backend API
cd backend && source venv/bin/activate && uvicorn api.main:app --reload --port 8000

# Tab 4 — Temporal Worker
cd backend && source venv/bin/activate && python worker/main.py

# Tab 5 — Frontend
cd frontend && npm run dev
```

Open `http://localhost:3000` in Chrome.

> Optionally open `http://localhost:8233` in a second tab to show the Temporal Web UI alongside the app.

---

## Recording Script

### Step 1 · Empty Dashboard (0:00)

- Open `http://localhost:3000`
- Show the empty state, counters, refresh control, and the **Template** / **Start Run** buttons
- *Narrate:* "This is the Order Supervisor dashboard. Each card represents one AI-managed order."

---

### Step 2 · Create a Supervisor Template (0:20)

- Click **Template**
- Fill in:
  - **Name:** `Standard Supervisor`
  - **Base instruction:** `You are supervising an e-commerce order. Escalate immediately on payment failure or carrier exceptions. If the order is delivered, write a final summary and terminate.`
- Keep all five available actions selected
- Click **Create Template**
- *Narrate:* "Templates define the AI system prompt and the set of tools the agent is allowed to call."

---

### Step 3 · Start a New Order Run (0:50)

- Click **Start Run**
- **Order ID:** `ORD-77421`
- Select `Standard Supervisor`
- Click **Start Workflow**
- *Narrate:* "This calls our FastAPI backend, which stores the run in the database and starts a long-lived Temporal workflow — one workflow per order."

---

### Step 4 · Open the Run Details Page (1:10)

- Click the `ORD-77421` card
- Show: breadcrumb, status badge (`running`), sleep state, next wake-up, empty timeline, empty memory
- *Narrate:* "The agent woke up on start. It has no events yet so it immediately scheduled a health-check and went back to sleep."

---

### Step 5 · Inject a Payment Confirmed Event (1:30)

- Click **Payment confirmed** in the Inject Event panel
- Wait 2–3 seconds
- Watch the timeline update automatically
- Point to the blue `event received` entry
- *Narrate:* "Events are delivered via Temporal signals — no polling, no queues. The signal wakes the classifier."

---

### Step 6 · Show Agent Waking (1:50)

- Point to the amber `agent woke up` entry
- *Narrate:* "The classifier decided this event warranted full LLM reasoning. The main agent is now processing."

---

### Step 7 · Show Tool Execution (2:00)

- Point to the green `tool executed` entry
- Expand the JSON to show `tool_name` and `arguments`
- *Narrate:* "The LLM output a tool call — here the agent messaged the fulfillment team. In production this would hit a real API."

---

### Step 8 · Show Memory Update (2:15)

- Point to the **Agent Memory** card
- *Narrate:* "The agent updates its rolling memory summary after every wake cycle. This keeps context bounded regardless of how long the workflow runs."

---

### Step 9 · Show Sleep Decision (2:30)

- Point to the grey `sleep decision` entry showing `sleep_duration_seconds`
- *Narrate:* "The agent told Temporal to sleep for N seconds. During this time, no LLM calls happen — the workflow just waits for the next signal."

---

### Step 10 · Inject a Critical Event — Payment Failed (2:45)

- Click **Payment failed**
- Watch for a new `agent woke up` entry
- *Narrate:* "A payment failure is a critical event. The classifier immediately flagged it — the agent didn't wait for its scheduled timer."

---

### Step 11 · Send a Manual Instruction (3:00)

- Type in the instruction box: `This is a VIP customer — prioritise speed over cost.`
- Click **Send Instruction**
- Watch the purple `manual instruction` entry appear
- *Narrate:* "Any human operator can steer the AI mid-run. This is the human-in-the-loop interface."

---

### Step 12 · Inject Delivered Event + Show Final Summary (3:20)

- Click **Delivered**
- Wait for the agent wake cycle
- Show the `agent woke up` → possible `tool executed` → `final output` sequence
- Watch the status badge change to `completed`
- Show final summary, learnings, and recommendations
- *Narrate:* "Delivery is a workflow-owned terminal event. The agent writes final output, and Temporal exits cleanly because the order lifecycle completed."

---

### Step 13 · Return to Dashboard (3:45)

- Navigate back to `http://localhost:3000`
- Show the `completed` badge on the order card
- *Narrate:* "The order card now shows `completed`. A new supervisor and a new order ID would start a fresh workflow."

---

## Things to Say During Recording

- Temporal guarantees the workflow continues even if the worker process restarts mid-execution
- The `memory_summary` field prevents the LLM context from growing unboundedly over a 30-day order lifecycle
- PostgreSQL is the default persistence path, and SQLite remains available for quick local smoke tests
- The `LLMProvider` abstraction means the GenAI SDK can be swapped to OpenAI or Anthropic in a single file
