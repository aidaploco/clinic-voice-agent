import asyncio
import json
from datetime import datetime

from clinic_voice_agent.gateway import AuditEvent
from clinic_voice_agent.live import EVENTS_TOPIC, event_publisher

EVENT = AuditEvent(
    datetime(2026, 11, 15, 10, 0), "identity_check", "refused", "no_match", {"attempt": 1}
)


async def test_each_event_is_sent_once_as_json_on_the_clinic_topic():
    sent = []

    async def send(text, topic):
        sent.append((json.loads(text), topic))

    event_publisher(send)(EVENT)
    await asyncio.sleep(0)
    assert sent == [(EVENT.as_dict(), EVENTS_TOPIC)]
    assert "1990" not in json.dumps(sent)


async def test_a_failed_send_is_swallowed():
    async def broken(text, topic):
        raise ConnectionError("room closed")

    event_publisher(broken)(EVENT)
    await asyncio.sleep(0.01)  # would surface as an unhandled task error if not swallowed


def test_with_no_running_loop_publishing_does_nothing():
    async def send(text, topic):
        raise AssertionError("must not be called")

    event_publisher(send)(EVENT)
