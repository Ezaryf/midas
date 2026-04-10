import asyncio
import logging
from typing import Any, Callable, Coroutine
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ExecutionTask:
    action: str
    payload: dict[str, Any]
    callback: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None

class ExecutionQueue:
    """
    A persistent, asynchronous queue for dispatching MT5 orders without blocking the main event loops.
    """
    def __init__(self):
        self._queue: asyncio.Queue[ExecutionTask] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    def start(self):
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._process_queue())
            logger.info("Execution Queue worker started")

    async def stop(self):
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            logger.info("Execution Queue worker stopped")

    async def enqueue(self, task: ExecutionTask):
        await self._queue.put(task)
        logger.debug(f"Task queued: {task.action}")

    async def _process_queue(self):
        while True:
            try:
                task = await self._queue.get()
                logger.info(f"Processing execution task: {task.action}")
                
                if task.callback:
                    try:
                        await task.callback(task.payload)
                    except Exception as e:
                        logger.error(f"Error executing callback for {task.action}: {e}")
                
                self._queue.task_done()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Execution queue worker error: {e}")

execution_queue = ExecutionQueue()
