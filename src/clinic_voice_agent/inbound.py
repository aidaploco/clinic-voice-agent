"""Pointing the phone line at Emily, and pointing it back.

A LiveKit SIP dispatch rule turns a call into a room. The worker only answers rooms it is
dispatched to by name, so the rule has to name it. This is pure: it works on rule objects and
touches no account. `scripts/setup_inbound.py` is the part that talks to LiveKit.
"""

from livekit import api


def rule_for_agent(current: api.SIPDispatchRuleInfo, agent_name: str) -> api.SIPDispatchRuleInfo:
    """A copy of the rule that dispatches `agent_name` to each room it creates.

    Everything else is kept as it was (the trunks, the room prefix, whether the caller's number
    is hidden), because a replace overwrites the whole rule. If the number were hidden the
    worker could not see who is calling and would turn everyone away.
    """
    desired = api.SIPDispatchRuleInfo()
    desired.CopyFrom(current)
    del desired.room_config.agents[:]
    desired.room_config.agents.append(api.RoomAgentDispatch(agent_name=agent_name))
    return desired


def agents_of(rule: api.SIPDispatchRuleInfo) -> list[str]:
    return [agent.agent_name for agent in rule.room_config.agents]


def problems(
    rule: api.SIPDispatchRuleInfo, trunk_allowed: set[str], env_allowed: set[str]
) -> list[str]:
    """Reasons the line would not work as intended. Nothing here names a number."""
    found = []
    if rule.hide_phone_number:
        found.append("the rule hides the caller's number, so the worker would refuse every call")
    if not env_allowed:
        found.append("ALLOWED_NUMBERS is empty, so the worker would refuse every phone call")
    if trunk_allowed != env_allowed:
        found.append(
            "the trunk's allowed numbers differ from ALLOWED_NUMBERS "
            f"({len(trunk_allowed)} on the trunk, {len(env_allowed)} in the environment)"
        )
    return found
