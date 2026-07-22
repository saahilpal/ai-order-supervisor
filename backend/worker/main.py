import asyncio
import logging
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from temporal.workflow import OrderSupervisorWorkflow
from activities.agent import run_classifier, run_agent_inference, execute_business_action, update_run_state

async def main():
    logging.basicConfig(level=logging.INFO)
    client = await Client.connect(
        "localhost:7233",
        data_converter=pydantic_data_converter,
    )
    
    worker = Worker(
        client,
        task_queue="order-supervisor-queue",
        workflows=[OrderSupervisorWorkflow],
        activities=[run_classifier, run_agent_inference, execute_business_action, update_run_state],
    )
    
    logging.info("Starting Temporal Worker for Order Supervisor...")
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
