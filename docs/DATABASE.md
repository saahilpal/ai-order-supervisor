# Database

## Purpose
Explains the data persistence layer of the Order Supervisor system.

## Responsibilities
- Store static `SupervisorConfig` templates.
- Maintain the current state of `OrderRun` instances for fast UI querying (avoiding direct queries to Temporal for list views).
- Keep a detailed chronological `ActivityLog` of every event, action, and decision made by the agent.

## Schema
- **SupervisorConfig**: Name, base instruction, tools, model choice.
- **OrderRun**: Tracks status, sleep state, memory summary, and wake-up times. Indexed by `tenant_id` and `order_id` for fast lookups.
- **ActivityLog**: Appends-only event sourcing for everything that happens during a run.

## Migrations
Alembic is used for database migrations.

## Future Improvements
- Archive completed activity logs to cold storage for long-term audit trails.
