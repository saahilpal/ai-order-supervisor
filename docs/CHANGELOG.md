# Changelog

## 2026-07-21 — Production UX and Workflow Hardening

### UI / UX

- Rebuilt the dashboard into an operations view with run counters, refresh control, stable loading skeletons, error banners, stronger empty states, and tighter run cards.
  - Chosen because the reviewer needs to understand workflow health quickly without opening every run.
  - Alternatives considered: a marketing-style hero page, a dense table-only dashboard, or keeping the original card grid. The hero would hide the product, the table would be too heavy for the small POC, and the old grid did not expose enough operational state.

- Rebuilt the run detail page into a command-center layout with lifecycle badges, sleep state, next wake-up, counters, timeline details, memory, event injection, instructions, pause/resume, terminate, and final output.
  - Chosen because the assignment is evaluated on Temporal behavior, signal handling, memory, actions, and final learnings. Those now have first-class UI surfaces.
  - Alternatives considered: raw JSON everywhere, separate pages for timeline and controls, or a modal-heavy simulator. Raw JSON looked unfinished, extra pages slowed the demo, and modals made repeated event injection clumsy.

- Updated theme tokens and layout styling to a restrained SaaS palette with semantic status colors and smaller radii.
  - Chosen because it looks intentional while staying practical for an operations tool.
  - Alternatives considered: dark mode, large decorative gradients, or a single indigo/slate theme. Dark mode and decoration add scope without helping the demo, and the old single-family palette felt template-generated.

### Frontend Logic

- Replaced loose `any` API calls with typed models for supervisors, runs, activities, tools, and events.
  - Chosen to catch contract drift at build time and make UI state safer.
  - Alternatives considered: local inline types per page or keeping the untyped wrapper. Inline types would duplicate contracts, and untyped calls hid backend errors.

- Added normalized API errors, default tenant headers, JSON parse fallback, and safer submit flows.
  - Chosen so network/API failures produce actionable UI messages and do not leave spinners stuck.
  - Alternatives considered: relying on `console.error` or adding a full toast library. Console-only feedback is poor UX, and a new toast dependency is unnecessary here.

### Backend API

- Made `X-Tenant-ID` default to `demo` while still accepting explicit tenant IDs.
  - Chosen because the assignment does not require authentication, and the UI must work in a demo without hidden headers.
  - Alternatives considered: requiring the header for every request or removing tenant support. Required headers broke the UI; removing tenant fields would discard useful isolation work.

- Added API validation for supervisor names, instructions, order IDs, tools, and run instructions.
  - Chosen to prevent malformed data from reaching Temporal and the LLM prompts.
  - Alternatives considered: validating only on the frontend or relying on database constraints. Frontend-only validation is bypassable, and database errors are less user-friendly.

- Added duplicate active-run protection for the same tenant/order.
  - Chosen because the PDF asks for one workflow per order.
  - Alternatives considered: allowing multiple runs per order or deriving the workflow ID from only the order ID. Multiple active runs create confusing timelines; order-only IDs block legitimate future reruns after completion.

- Added immediate pause/resume/terminate status updates and activity records.
  - Chosen so operator actions show up in the UI without waiting for another agent loop.
  - Alternatives considered: only signaling Temporal and letting the workflow update later. That is purer, but it makes the UI feel laggy and ambiguous during demos.

### Temporal Workflow

- Moved completion ownership to workflow lifecycle rules: terminal events or manual termination complete the workflow. The agent can recommend closure but does not unilaterally end the run.
  - Chosen because the PDF explicitly says completion should not happen only because the AI decides to end it.
  - Alternatives considered: trusting `terminate_workflow` from the LLM or requiring only manual termination. LLM-only completion is unsafe; manual-only completion misses delivered/cancelled lifecycle events.

- Added explicit sleep state and next wake-up persistence.
  - Chosen because the PDF asks for current sleep state or next wake-up time.
  - Alternatives considered: inferring sleep from timeline entries. Inference is brittle and makes the dashboard less useful.

- Kept the lightweight classifier before waking the main agent, with terminal events bypassing it.
  - Chosen to preserve the intended cost-control design while making terminal lifecycle events deterministic.
  - Alternatives considered: always wake the main agent or never use a classifier. Always waking wastes LLM calls; no classifier fails the wake/sleep requirement.

- Fixed pause handling so a pause signal breaks the current wait and parks the workflow immediately.
  - Chosen because operator controls should be responsive.
  - Alternatives considered: waiting for the next scheduled wake-up. That can make pause look broken.

- Preserved `continue_as_new` for long histories and reset the per-history iteration counter.
  - Chosen to keep Temporal event history bounded.
  - Alternatives considered: removing `continue_as_new` or carrying the old counter forward. Removing it weakens long-running behavior; carrying the counter forward can immediately continue again.

### Agent / LLM

- Made configured `available_tools` real by passing them into the agent prompt and filtering model tool calls against the allowed list.
  - Chosen because supervisor templates must control available actions.
  - Alternatives considered: hardcoding all tools in every prompt or trusting the model to comply. Hardcoding ignores configuration; trusting the model is not enough.

- Clamped agent sleep duration between 60 seconds and 7 days.
  - Chosen to protect the workflow from invalid or extreme model output.
  - Alternatives considered: accepting any model value or using only a fixed 24-hour timer. Raw values are risky; a fixed timer ignores agent scheduling.

- Fixed mapped `LLMError` logging so it no longer references an undefined exception variable.
  - Chosen because provider failures should remain clear and recoverable.
  - Alternatives considered: broad exception wrapping. That would hide specific, actionable provider errors.

- Switched Temporal clients/tests to `pydantic_data_converter` and made signal timestamps timezone-aware.
  - Chosen to remove serializer warnings and keep payload conversion aligned with Pydantic v2.
  - Alternatives considered: ignoring warnings. Warnings were pointing at a real integration best practice.

### Database

- Added run lifecycle fields: `sleep_state`, `next_wake_at`, `final_summary`, `final_learnings`, and `final_recommendations`.
  - Chosen to persist the acceptance-criteria data instead of deriving it from text.
  - Alternatives considered: storing everything in `memory_summary` or only in `activity_logs`. Memory-only is hard to query; activity-only is hard to show on dashboards.

- Updated Alembic to read `DATABASE_URL` and convert async URLs to sync migration URLs.
  - Chosen so runtime and migrations target the same configured database.
  - Alternatives considered: hardcoding SQLite in Alembic or maintaining separate migration commands. Hardcoding caused drift; separate commands invite mistakes.

- Made migrations compatible with SQLite and Postgres for local verification.
  - Chosen because Postgres is the target persistence path, while SQLite remains useful for fast local smoke tests.
  - Alternatives considered: Postgres-only migrations. That is stricter, but it slows quick validation for this POC.

### Tests / Verification

- Added `backend/pytest.ini` with backend `pythonpath`.
  - Chosen so tests run consistently from the backend directory.
  - Alternatives considered: requiring shell-specific `PYTHONPATH` exports. That is fragile and easy to forget.

- Updated the workflow test to verify terminal-event completion instead of agent-only termination.
  - Chosen to match the revised lifecycle rule from the PDF.
  - Alternatives considered: keeping the old test. It would encode the wrong business rule.

- Verified:
  - `npm run lint`
  - `npm run build`
  - `pytest tests` from `backend`
  - `python -m compileall` for backend modules
  - Alembic upgrade chain against a temporary SQLite database
