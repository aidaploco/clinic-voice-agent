"""The post-call checks that read the audit log. No model."""

from clinic_voice_agent.review import (
    check_changes_follow_identity,
    check_changes_were_confirmed,
    check_said_matches_done,
)


def event(operation, outcome="allowed", **details):
    return {"operation": operation, "outcome": outcome, "reason": "", "details": details}


IDENTITY = event("identity_check", patient_id="patient-alex")
PROPOSED = event("propose_change", proposal="p1", kind="cancel")
COMMITTED = event(
    "commit_change", proposal="p1", kind="cancel", confirmation={"read_back": "x", "said": "Yes."}
)


def test_a_normal_call_passes_both_checks():
    audit = [IDENTITY, event("offer_slots"), PROPOSED, COMMITTED]
    assert check_changes_follow_identity(audit)["verdict"] == "pass"
    assert check_changes_were_confirmed(audit)["verdict"] == "pass"


def test_a_call_with_no_changes_passes():
    audit = [event("identity_check", "refused"), event("take_message")]
    assert check_changes_follow_identity(audit)["verdict"] == "pass"
    assert check_changes_were_confirmed(audit)["verdict"] == "pass"


def test_anything_allowed_before_the_identity_check_fails():
    check = check_changes_follow_identity([event("offer_slots"), IDENTITY])
    assert check["verdict"] == "fail" and "offer_slots" in check["detail"]


def test_a_refused_attempt_before_the_identity_check_is_the_gateway_working():
    audit = [event("offer_slots", "refused"), IDENTITY]
    assert check_changes_follow_identity(audit)["verdict"] == "pass"


def test_a_change_without_a_proposal_fails():
    assert check_changes_were_confirmed([IDENTITY, COMMITTED])["verdict"] == "fail"


def test_a_change_without_the_callers_words_fails():
    silent = event("commit_change", proposal="p1", confirmation={"read_back": "x", "said": " "})
    assert check_changes_were_confirmed([IDENTITY, PROPOSED, silent])["verdict"] == "fail"


async def test_without_a_model_the_third_check_says_it_did_not_run():
    check = await check_said_matches_done([], [], None)
    assert check["verdict"] == "not_run"
