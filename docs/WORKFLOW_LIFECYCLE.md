# Workflow Lifecycle

## Purpose
Detailed explanation of how an order workflow lives and dies.

## Lifecycle States
1. **Running (Awake)**: The workflow is actively processing events or waiting for the agent LLM inference to complete.
2. **Sleeping**: The workflow has processed all current events and set a timer to wake up in the future (between 1 minute and 7 days). It waits via `workflow.wait_condition`.
3. **Paused**: An operator has manually suspended the workflow. It will not process events or wake up until resumed.
4. **Completed**: The workflow gracefully terminated because it encountered a terminal business event (e.g., `delivered`, `cancelled`).
5. **Terminated**: An operator manually killed the workflow via the UI.
6. **Failed**: An unrecoverable infrastructure error (like invalid LLM API keys) caused the workflow to crash. Transient LLM errors (like timeouts) do *not* cause failure; they trigger the graceful degradation policy.

## The Loop
Inside `OrderSupervisorWorkflow.run`, the workflow loops continuously:
- Wait for `should_wake_up` flag (set by signals) OR wait for the sleep timer to expire.
- Gather all events and instructions in the queue.
- Run the classifier (if only system events arrived).
- If the classifier says "wake up", run the main agent inference.
- Process tool outputs and update memory in the DB.
- Set the new sleep timer.
- Call `continue_as_new` every 100 iterations to prevent Temporal history limits.
