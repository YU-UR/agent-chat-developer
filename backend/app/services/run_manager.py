import asyncio
from collections import defaultdict


class RunManager:

    def __init__(self):
        self.queues: dict[
            str,
            asyncio.Queue
        ] = {}

    def create_run(
            self,
            run_id: str
    ) -> None:
        self.queues[run_id] = asyncio.Queue()

    def get_queue(
            self,
            run_id: str
    ) -> asyncio.Queue:
        return self.queues[run_id]

    async def publish(
            self,
            run_id: str,
            event: dict
    ) -> None:
        queue = self.queues[run_id]

        await queue.put(event)

    def remove_run(
            self,
            run_id: str
    ) -> None:
        self.queues.pop(
            run_id,
            None
        )


run_manager = RunManager()
