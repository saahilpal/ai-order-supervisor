# Temporal Integration

## Purpose
Explains how Temporal is used to orchestrate the Order Supervisor lifecycle.

## Workflow Mechanics
The core engine is the `OrderSupervisorWorkflow`.
- **Event-Driven**: It uses `workflow.wait_condition` to pause execution without consuming resources, waking up only when a timer expires, a manual instruction is received, or a system event arrives.
- **Activities**: All LLM inference, database updates, and external API calls are isolated in Temporal Activities (`activities/agent.py`).
- **Continue-As-New**: To prevent the workflow history from growing infinitely during long-running orders, the workflow utilizes `workflow.continue_as_new` every 100 iterations.

## Failure & Retry Policy
- **Transient Errors**: Rate limits and timeouts from LLM providers are naturally retried by Temporal's built-in RetryPolicy.
- **Graceful Degradation**: If retries are exhausted for the main agent, the activity gracefully falls back to a sleep state, logging the error and keeping the workflow alive.
- **Non-Retryable Errors**: Authentication and configuration errors raise an `ApplicationError(non_retryable=True)` so they do not spin infinitely.

## Future Improvements
- Expand Temporal worker fleets and task routing for specific tenant queues.
