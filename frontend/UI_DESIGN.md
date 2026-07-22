# Frontend UI Design & Page Hierarchy

## Design System
- **Typography**: Inter (sans-serif) for all text. Clean, highly legible.
- **Colors**:
  - Background: Neutral very light gray/off-white (`bg-slate-50`).
  - Cards/Containers: Solid white (`bg-white`) with subtle borders (`border-slate-200`) and soft shadows (`shadow-sm`).
  - Primary Accents: Indigo/Blue (`text-indigo-600`, `bg-indigo-600` for primary buttons).
  - Text: `text-slate-900` for headings, `text-slate-600` for body copy.
  - Status Indicators: 
    - Green (`text-emerald-600`, `bg-emerald-100`) for Success/Completed.
    - Yellow (`text-amber-600`, `bg-amber-100`) for Running/Waiting.
    - Red (`text-rose-600`, `bg-rose-100`) for Terminated/Failed.
- **Spacing**: Strict 8px grid (Tailwind `p-2`, `p-4`, `p-6`, `gap-4`).
- **Components**: Use `shadcn/ui` exclusively for Buttons, Inputs, Cards, Dialogs, Badges.

## Page Hierarchy

### 1. Dashboard ( `/` )
**Purpose**: List all active and completed runs, and provide entry points to create new supervisors or start new runs.
- **Header**: "Order Supervisor" logo + simple navigation.
- **Main Layout**:
  - Top Action Bar: "Create Template", "Start New Run" buttons.
  - Run List (Data Table or Grid of Cards):
    - Columns/Fields: Order ID, Status Badge, Supervisor Template Name, Started At, Last Updated.
    - Hover effects: Soft lift (`hover:shadow-md`, `transition-all`).
    - Click: Navigates to `/runs/[id]`.

### 2. Run Details ( `/runs/[id]` )
**Purpose**: The central command center for a single order's AI supervisor.
- **Header**: Breadcrumb (`Home / Run [id]`) + Status Badge + Quick Actions (Interrupt, Terminate, Resume).
- **Layout (2 Columns)**:
  - **Left Column (Primary)**:
    - **Timeline View**: A vertical feed showing events (gray/blue), agent sleep/wake decisions (amber), agent tool actions (purple).
    - Each timeline item: Icon, Title, Timestamp, details expander.
  - **Right Column (Secondary Context & Controls)**:
    - **Memory Box**: A clean card showing the agent's current rolling memory summary.
    - **Event Injector Panel**: A card with predefined buttons (e.g., "Payment Failed", "Shipment Delayed") to mock real-world events.
    - **Manual Instruction Form**: A text input + "Send Instruction" button to steer the agent mid-run.

### 3. Modals / Dialogs
- **Create Supervisor Template**: Dialog with form (Name, Base Instruction, Tool Selectors).
- **Start New Run**: Dialog selecting an existing Supervisor Template and entering an `order_id`.

## Interaction Patterns
- **Empty States**: Friendly illustration or text ("No runs active yet. Start one to see the AI in action.").
- **Loading States**: Skeleton loaders mimicking the structure of the data (no jarring spinners).
- **Feedback**: Toast notifications for "Event Sent", "Instruction Added", "Run Terminated".
