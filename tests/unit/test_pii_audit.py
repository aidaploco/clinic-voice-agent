from evals.pii_audit import Needle, look_alikes, mask, needles_from, parse_env, scan

ENV = """\
# a comment
ALLOWED_NUMBERS=+15550100123
SIP_TRUNK_NUMBER=+15550100456
OPENAI_API_KEY=value-one-for-the-test
LIVEKIT_URL=wss://demo-project-xyz.livekit.cloud
MAX_CALL_SECONDS=300
DEV_CONSOLE=true
"""


def test_the_private_settings_become_needles_and_the_limits_do_not():
    labels = {n.label for n in needles_from(parse_env(ENV), [])}
    assert {"ALLOWED_NUMBERS", "SIP_TRUNK_NUMBER", "OPENAI_API_KEY"} <= labels
    assert "LIVEKIT_URL (project)" in labels and "LIVEKIT_URL (host)" in labels
    assert "MAX_CALL_SECONDS" not in labels and "DEV_CONSOLE" not in labels


def test_a_phone_number_is_found_however_it_is_written():
    needles = needles_from(parse_env(ENV), [])
    for written in ("+15550100123", "+1 (555) 010-0123", "1-555-010-0123", "call 5550100123 now"):
        hits = scan(f"a\n{written}\nb", "file x", needles)
        assert [h.label for h in hits] == ["ALLOWED_NUMBERS"], written
        assert hits[0].line == 2


def test_a_different_number_is_not_found():
    assert scan("+15550100999", "file x", needles_from(parse_env(ENV), [])) == []


def test_a_finding_never_carries_the_value_it_found():
    hit = scan("key value-one-for-the-test here", "file x", needles_from(parse_env(ENV), []))[0]
    assert "value-one" not in repr(hit) and hit.label == "OPENAI_API_KEY"


def test_extra_values_are_looked_for_without_case():
    hits = scan("Written by FIRST Last.", "x", needles_from({}, ["first last"]))
    assert [h.label for h in hits] == ["PII_EXTRA #1"]


def test_look_alikes_skip_the_harmless_and_mask_the_numbers():
    text = "a@users.noreply.github.com b@example.com real@person.org +44 7700 900123 /Users/jo/x"
    found = {(kind, masked) for kind, _, _, masked in look_alikes(text, "f")}
    assert ("email", "…") in found and ("home path", "…") in found
    assert not any(k == "email" for k, m in found if m != "…")
    phone = [m for k, m in found if k == "phone"][0]
    assert phone.endswith("23") and "7700" not in phone


def test_masking_keeps_only_the_last_two_digits():
    assert mask("+15550100123").endswith("23") and "5550" not in mask("+15550100123")


def test_a_short_value_is_not_a_needle():
    assert needles_from({"X_TOKEN": "abc"}, []) == []


def test_needle_is_a_value_type():
    assert Needle("A", "b") == Needle("A", "b")


def test_what_is_meant_to_be_public_is_taken_out_before_looking():
    from evals.pii_audit import without_public

    needles = needles_from({}, ["Smith"])
    text = "by Jo Smith, github.com/josmith/repo and Smith again"
    assert len(scan(text, "x", needles)) == 3
    cleaned = without_public(text, ["josmith", "Jo Smith"])
    assert [h.label for h in scan(cleaned, "x", needles)] == ["PII_EXTRA #1"]  # the lone "Smith"


def test_a_github_that_cannot_be_read_is_an_error_and_not_an_empty_result(monkeypatch):
    import subprocess

    import pytest

    from evals import pii_audit

    def failing(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="HTTP 404: Not Found\n")

    monkeypatch.setattr(pii_audit.subprocess, "run", failing)
    with pytest.raises(pii_audit.GitHubUnreadable):
        pii_audit.github("repos/x/y")
