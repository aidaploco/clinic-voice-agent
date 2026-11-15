"""The eval runner's grading and its scenario file. No model."""

from evals.run import ORIGINAL, Result, grade, load_scenarios, table

PASSING = [{"name": "said_matches_done", "verdict": "pass", "detail": ""}]


def test_every_scenario_is_well_formed_and_both_kinds_of_caller_are_present():
    scenarios = load_scenarios()
    assert len(scenarios) >= 10
    assert any("script" in s for s in scenarios) and any("persona" in s for s in scenarios)
    for scenario in scenarios:
        assert scenario["about"] and "verified" in scenario["expect"]
        if scenario["expect"]["outcome"] == "moved":
            assert scenario["expect"]["start"]


def test_an_unverified_caller_must_leave_everything_unchanged_to_pass():
    expect = {"verified": False, "outcome": "unchanged"}
    assert grade(expect, False, ORIGINAL, 0, PASSING) == []
    assert grade(expect, True, ORIGINAL, 0, PASSING)  # got in
    assert grade(expect, False, (ORIGINAL[0], "cancelled"), 0, PASSING)  # changed something


def test_a_move_passes_only_at_the_expected_time():
    expect = {"verified": True, "outcome": "moved", "start": "2026-11-19T16:30"}
    assert grade(expect, True, ("2026-11-19T16:30", "confirmed"), 0, PASSING) == []
    assert grade(expect, True, ("2026-11-18T10:30", "confirmed"), 0, PASSING)
    assert grade(expect, True, ORIGINAL, 0, PASSING)


def test_a_failed_review_fails_the_conversation_even_when_the_outcome_is_right():
    expect = {"verified": True, "outcome": "cancelled"}
    bad = [{"name": "said_matches_done", "verdict": "fail", "detail": "said moved"}]
    assert grade(expect, True, (ORIGINAL[0], "cancelled"), 0, PASSING) == []
    assert "said_matches_done" in grade(expect, True, (ORIGINAL[0], "cancelled"), 0, bad)[0]


def test_a_scenario_that_needs_a_message_fails_without_one():
    expect = {"verified": True, "outcome": "unchanged", "message": True}
    assert grade(expect, True, ORIGINAL, 1, PASSING) == []
    assert grade(expect, True, ORIGINAL, 0, PASSING) == ["no message was left for the clinic"]


def test_the_table_counts_passes_per_scenario_and_overall():
    scenarios = [
        {"id": "a", "about": "A.", "script": []},
        {"id": "b", "about": "B.", "persona": ""},
    ]
    results = [Result("a", True, [], 4), Result("a", False, ["x"], 6), Result("b", True, [], 3)]
    text = table(scenarios, results)
    assert "| A. | scripted | 1/2 | 5.0 |" in text and "| B. | simulated | 1/1 | 3.0 |" in text
    assert "**2/3**" in text
