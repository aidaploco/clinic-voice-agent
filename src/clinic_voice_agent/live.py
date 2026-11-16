"""Sending the gateway's decisions to the room, so a browser page can show them as they happen.

The page already gets the agent's state and the transcript from the framework. The gateway's
events are ours, so they travel on one custom topic as JSON. The audit log never holds a date
of birth, so neither does this.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from clinic_voice_agent.gateway import AuditEvent

logger = logging.getLogger(__name__)

EVENTS_TOPIC = "clinic.audit"

Send = Callable[[str, str], Awaitable[Any]]  # (text, topic)


def event_publisher(send: Send) -> Callable[[AuditEvent], None]:
    """An observer for `Gateway.on_event` that sends each event. A failed send is only logged."""
    pending: set[asyncio.Task] = set()

    async def deliver(text: str) -> None:
        try:
            await send(text, EVENTS_TOPIC)
        except Exception:
            logger.warning("could not send a gateway event to the room", exc_info=True)

    def publish(event: AuditEvent) -> None:
        try:
            task = asyncio.get_running_loop().create_task(deliver(json.dumps(event.as_dict())))
        except RuntimeError:
            return  # no running loop: a unit test or a script, nothing to send to
        pending.add(task)  # a task nobody holds can be collected before it finishes
        task.add_done_callback(pending.discard)

    return publish
