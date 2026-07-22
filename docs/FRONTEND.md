# Frontend

## Purpose
Explains the user interface for monitoring and interacting with the Order Supervisor.

## Framework
- **Next.js**: Built with the Next.js App Router (`src/app/page.tsx` and `src/app/runs/[id]/page.tsx`).
- **Tailwind CSS & Shadcn/UI**: Used for styling and component primitives.

## Responsibilities
- Monitor running order workflows and display timeline of events.
- Allow operators to manually inject system events (e.g. `payment_failed`) to simulate external hooks.
- Allow operators to send manual instructions directly to the agent.
- View memory summaries, wake-up times, and final outputs.

## Trade-offs
- Uses a polling architecture (`setInterval(loadData, 3000)`) instead of WebSockets. This simplifies the deployment for a POC, ensuring it can run without additional infrastructure (like Redis pub/sub for SSE).

## Future Improvements
- Add WebSocket support for true real-time updates.
- Provide a richer UI for visualizing the JSON payloads of specific events.
