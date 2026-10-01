"""WebSocket hub: pushes twin updates to connected browsers.

Ingestion can run in worker threads, so publishing hands messages to the
event loop with ``call_soon_threadsafe``. Each client has its own bounded
queue; a slow client drops old messages instead of blocking ingestion.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)

QUEUE_SIZE = 50


class Hub:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self._clients: dict[str, set[asyncio.Queue[str]]] = {}

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    @property
    def client_count(self) -> int:
        return sum(len(v) for v in self._clients.values())

    def publish(self, twin_id: str, message: dict[str, Any]) -> None:
        if self.loop is None or not self._clients.get(twin_id):
            return
        text = json.dumps(message, default=str)
        self.loop.call_soon_threadsafe(self._fan_out, twin_id, text)

    def publish_all(self, message: dict[str, Any]) -> None:
        for twin_id in list(self._clients):
            self.publish(twin_id, message)

    def _fan_out(self, twin_id: str, text: str) -> None:
        for queue in list(self._clients.get(twin_id, ())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(text)

    async def serve(self, websocket: WebSocket, twin_id: str, initial: list[dict[str, Any]]) -> None:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._clients.setdefault(twin_id, set()).add(queue)
        try:
            for message in initial:
                await websocket.send_text(json.dumps(message, default=str))
            receiver = asyncio.create_task(self._drain_incoming(websocket))
            while not receiver.done():
                sender = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
                if sender in done:
                    await websocket.send_text(sender.result())
                else:
                    sender.cancel()
        except Exception as exc:  # disconnects surface as various exception types
            log.debug("websocket closed: %s", exc)
        finally:
            self._clients.get(twin_id, set()).discard(queue)

    @staticmethod
    async def _drain_incoming(websocket: WebSocket) -> None:
        """Read (and ignore) client messages; returns when the client disconnects."""
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            return
