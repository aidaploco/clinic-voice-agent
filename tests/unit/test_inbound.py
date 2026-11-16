import pytest
from livekit import api

from clinic_voice_agent.allowlist import admit, mask, normalise, parse_allowed
from clinic_voice_agent.inbound import agents_of, problems, rule_for_agent

OWNER = "+14155550123"
ALLOWED = frozenset({OWNER})


def test_a_number_is_compared_the_way_it_is_dialled_not_the_way_it_is_typed():
    assert normalise("+1 (415) 555-0123") == OWNER
    assert parse_allowed(" +1 415 555 0123 , +1 415 555 0142") == {OWNER, "+14155550142"}
    assert parse_allowed("") == frozenset()


@pytest.mark.parametrize("bad", ["[+LLLLLLLLLLLL]", "4155550123", "+0123456789", "+1415", "abc"])
def test_a_malformed_allowlist_entry_is_an_error_that_does_not_echo_the_number(bad):
    with pytest.raises(ValueError) as error:
        parse_allowed(f"{OWNER},{bad}")
    assert "entry 2" in str(error.value) and bad not in str(error.value)


def test_the_owners_phone_is_taken_and_a_stranger_is_turned_away():
    assert admit(True, "+1 415 555 0123", ALLOWED).allowed
    refused = admit(True, "+14155550199", ALLOWED)
    assert not refused.allowed and refused.reason == "number_not_allowed"
    assert "555" not in refused.caller and refused.caller.endswith("199")


def test_a_phone_call_is_refused_when_the_number_is_missing_or_the_list_is_empty():
    assert admit(True, None, ALLOWED).reason == "no_caller_number"
    assert admit(True, "", ALLOWED).reason == "no_caller_number"
    assert admit(True, "anonymous", ALLOWED).reason == "no_caller_number"
    assert not admit(True, OWNER, frozenset()).allowed  # fail closed


def test_a_browser_page_needs_no_number():
    assert admit(False, None, frozenset()).allowed


def test_a_masked_number_cannot_be_dialled():
    assert mask(OWNER) == "+…123" and mask(None) == "unknown"


def make_rule(**over):
    rule = api.SIPDispatchRuleInfo(
        sip_dispatch_rule_id="SDR_x", name="line", trunk_ids=["ST_1"], hide_phone_number=False
    )
    rule.rule.dispatch_rule_individual.room_prefix = "call-"
    for key, value in over.items():
        setattr(rule, key, value)
    return rule


def test_pointing_the_rule_at_emily_keeps_everything_else_about_it():
    current = make_rule()
    desired = rule_for_agent(current, "clinic-receptionist")
    assert agents_of(current) == [] and agents_of(desired) == ["clinic-receptionist"]
    assert list(desired.trunk_ids) == ["ST_1"] and desired.name == "line"
    assert desired.rule.dispatch_rule_individual.room_prefix == "call-"
    assert desired.hide_phone_number is False


def test_pointing_the_rule_twice_gives_the_same_rule_and_replaces_another_agent():
    once = rule_for_agent(make_rule(), "clinic-receptionist")
    assert rule_for_agent(once, "clinic-receptionist") == once
    assert agents_of(rule_for_agent(once, "other")) == ["other"]


def test_the_checks_name_what_would_make_the_line_refuse_everyone_without_naming_a_number():
    assert problems(make_rule(), {OWNER}, {OWNER}) == []
    text = " ".join(problems(make_rule(hide_phone_number=True), {OWNER}, set()))
    assert "hides the caller's number" in text and "ALLOWED_NUMBERS is empty" in text
    assert "differ" in " ".join(problems(make_rule(), {OWNER}, {"+14155550199"}))
    assert OWNER not in " ".join(problems(make_rule(), {OWNER}, {"+14155550199"}))


async def test_replacing_a_rule_calls_livekit_the_way_its_client_really_takes_it():
    # An autospec has the real method's signature, so a wrong call is a TypeError here instead
    # of on the owner's account (the first live run of the script made exactly that mistake).
    from unittest.mock import create_autospec

    from livekit.api.sip_service import SipService

    from clinic_voice_agent.inbound import replace_rule

    sip = create_autospec(SipService, instance=True)
    rule = rule_for_agent(make_rule(), "clinic-receptionist")
    await replace_rule(sip, "SDR_x", rule)
    sip.update_dispatch_rule.assert_awaited_once_with("SDR_x", rule)
