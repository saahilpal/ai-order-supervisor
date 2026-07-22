# Backend API

## Purpose
Explains the FastAPI backend of the Order Supervisor system.

## Responsibilities
- Serve a RESTful API for the Next.js frontend.
- Start and terminate Temporal workflows.
- Inject signals (events and manual instructions) into running workflows.
- Provide historical activity logs and read-only views of the database.

## Endpoints
- `GET /api/supervisors`: List available supervisor templates.
- `POST /api/supervisors`: Create a new supervisor template.
- `POST /api/runs`: Start a new order supervisor workflow.
- `GET /api/runs`: List active and completed runs.
- `POST /api/runs/{run_id}/events`: Inject a system event into the workflow.
- `POST /api/runs/{run_id}/instructions`: Inject a manual instruction into the workflow.

## Future Improvements
- Add authentication and authorization.
- Implement rate limiting.
