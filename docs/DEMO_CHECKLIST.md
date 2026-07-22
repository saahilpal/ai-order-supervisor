# Demo Recording Checklist

Use this checklist to ensure your walkthrough video covers every key acceptance criterion.

---

## Pre-Recording Setup

- [ ] Run `temporal server start-dev` — confirm UI at `http://localhost:8233`
- [ ] Run `docker compose up -d postgres`
- [ ] Run `uvicorn api.main:app --reload --port 8000`
- [ ] Run `python worker/main.py`
- [ ] Run `cd frontend && npm run dev`
- [ ] Open browser to `http://localhost:3000`
- [ ] Clear any previous test runs from `orders.db` if desired

---

## Recording Steps

### Step 1 — Show empty dashboard
- Open `http://localhost:3000`
- Point out the empty state, run counters, refresh control, and action buttons

### Step 2 — Create a Supervisor Template
- Click **Template**
- Enter name: `Standard Supervisor`
- Enter instruction: *"You are supervising an e-commerce order. Escalate immediately on payment failure or logistics delays. If the order is delivered, write a final summary and terminate."*
- Keep the default available actions selected
- Click **Create Template**
- ✅ Toast confirms creation

### Step 3 — Start a new order run
- Click **Start Run**
- Enter order ID: `ORD-77421`
- Select the template just created
- Click **Start Workflow**
- ✅ Toast confirms; card appears on dashboard

### Step 4 — Open the Run Details page
- Click the order card
- Show breadcrumb navigation, status badge, sleep state, next wake-up, empty timeline

### Step 5 — Inject Payment Confirmed event
- Click **Payment confirmed** in the Inject Event panel
- Watch the timeline update within 3 seconds
- Point out the blue `event` timeline entry

### Step 6 — Show AI waking up
- Watch for an `agent_wakeup` entry (amber) to appear in the timeline
- This proves the classifier decided the event warranted agent reasoning

### Step 7 — Show tool execution
- Watch for one or more `agent_action` entries (green) to appear
- Expand the JSON to show `tool_name` and `arguments`

### Step 8 — Show memory update
- Point to the **Agent Memory** card on the right
- It should now contain a concise summary of what the agent knows

### Step 9 — Show agent sleeping
- A `sleep_decision` entry (grey) appears showing `sleep_duration_seconds`
- This proves the agent is not calling the LLM again until the next event

### Step 10 — Inject a critical event: Payment Failed
- Click **Payment failed**
- Watch for a new `agent_wakeup` — the agent woke because the classifier flagged it

### Step 11 — Send a manual instruction
- Type: *"The customer has premium status — please expedite."*
- Click **Send Instruction**
- Watch the `manual_instruction` entry (purple) appear and the agent respond

### Step 12 — Inject Delivered event
- Click **Delivered**
- After the next wake cycle, agent should set `terminate_workflow: true`
- Status badge changes from `running` → `completed`
- Final Output shows summary, learnings, and recommendations

### Step 13 — Return to Dashboard
- Show the completed run card with `completed` badge
- Narrate that the Temporal workflow has exited cleanly

---

## Things to Narrate During Recording

- Why Temporal instead of a cron job / queue
- How signals deliver real-time events without polling
- The classifier's role in preventing unnecessary LLM calls
- How `memory_summary` keeps context bounded
- The SQLite → PostgreSQL migration path (one env var change)

---

## Acceptance Criterion Coverage Map

| Criterion | Steps that prove it |
| :--- | :--- |
| One workflow per order | Step 3 — one card per order ID |
| Events as signals | Steps 5, 10, 12 |
| Agent wakes on event | Step 6 |
| Agent can sleep | Step 9 |
| Tool execution | Step 7 |
| Timeline view | Step 4 and throughout |
| Memory compaction | Step 8 |
| Manual instruction | Step 11 |
| Pause/resume/terminate controls | Header controls on run details |
| Final summary + lifecycle completion | Step 12 |
