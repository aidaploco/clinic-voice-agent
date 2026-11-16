"""Keeping a caller's phone number out of what this project stores.

LiveKit names the room of a phone call after the caller's number ("inbound-_+14155550123_xyz").
That name reaches record file names, the database and log lines, which have no need of the
number. What is stored here uses an id made from the room name instead; a browser call's room
name carries no number and is kept as it is.
"""

import hashlib
import re

PHONE_IN_ROOM = re.compile(r"\+\d{7,15}")


def call_id_for(room_name: str) -> str:
    """The room name, or a short hash of it when it holds a phone number."""
    if PHONE_IN_ROOM.search(room_name):
        return "phone-" + hashlib.sha256(room_name.encode()).hexdigest()[:10]
    return room_name
