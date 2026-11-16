import json

from clinic_voice_agent.calls import CALL_ID, channel_of, find_call, list_calls, summarise


def write(folder, started, call_id, **fields):
    record = {"room": call_id, "started": started, "ended_because": "caller_hung_up", **fields}
    name = f"{started.replace(':', '')}-{call_id}.json"
    (folder / name).write_text(json.dumps(record))
    return name


def test_how_a_call_came_in_is_read_from_its_id():
    ids = ("phone-7192a98328", "web-0a1b2c3d", "test-94484c28", "console", "x")
    assert [channel_of(i) for i in ids] == ["phone", "browser", "test", "console", "other"]


def test_a_summary_has_what_a_list_needs_and_no_transcript_or_audit_details():
    record = {
        "room": "web-0a1b2c3d",
        "started": "2026-11-15T20:54:00",
        "ended_because": "agent_ended_call",
        "appointment_after": {"start": "2026-11-20T09:00", "practitioner": "L", "status": "ok"},
        "checks": [{"verdict": "pass"}, {"verdict": "pass"}, {"verdict": "not_run"}],
        "audit": [{"operation": "commit_change", "outcome": "allowed", "details": {"secret": "x"}}],
        "transcript": [
            {"speaker": "agent", "text": "Hello. My date of birth is 14 March"},
            {"speaker": "caller", "text": "hi"},
            {"speaker": "caller", "text": "bye"},
        ],
    }  # fmt: skip
    summary = summarise(record)
    assert summary["checks"] == {"pass": 2, "fail": 0, "not_run": 1}
    assert summary["turns"] == 2 and summary["changed"] is True and summary["channel"] == "browser"
    assert (
        "transcript" not in summary
        and "audit" not in summary
        and "March" not in json.dumps(summary)
    )


def test_a_refused_commit_is_not_a_change():
    refused = {
        "room": "web-aaaaaaaa",
        "audit": [{"operation": "commit_change", "outcome": "refused"}],
    }
    assert summarise(refused)["changed"] is False


def test_the_list_is_newest_first_limited_and_skips_files_that_are_not_records(tmp_path):
    write(tmp_path, "2026-11-15T10:00:00", "web-11111111")
    write(tmp_path, "2026-11-15T12:00:00", "phone-aaaaaaaaaa")
    write(tmp_path, "2026-11-14T09:00:00", "test-22222222")
    (tmp_path / "2026-11-15T130000-web-33333333.json").write_text("{ half written")
    (tmp_path / "notes.json").write_text("{}")
    (tmp_path / "2026-11-15T140000-web-44444444.json").write_text("[1, 2]")
    assert [c["id"] for c in list_calls(tmp_path)] == [
        "phone-aaaaaaaaaa",
        "web-11111111",
        "test-22222222",
    ]
    assert [c["id"] for c in list_calls(tmp_path, limit=1)] == ["phone-aaaaaaaaaa"]
    assert list_calls(tmp_path / "missing") == []


def test_one_call_is_found_only_by_exactly_its_id(tmp_path):
    write(
        tmp_path,
        "2026-11-15T10:00:00",
        "web-11111111",
        transcript=[{"speaker": "agent", "text": "hi"}],
    )
    write(tmp_path, "2026-11-15T11:00:00", "test-web-11111111")  # an id that merely ends the same
    assert find_call(tmp_path, "web-11111111")["transcript"][0]["text"] == "hi"
    assert find_call(tmp_path, "11111111") is None  # not a suffix match
    assert find_call(tmp_path, "web-99999999") is None


def test_an_id_that_could_be_a_path_is_never_looked_up(tmp_path):
    for bad in ("../x", "a/b", "a.b", "", "-x", "x" * 80, "x\n"):
        assert not CALL_ID.fullmatch(bad) and find_call(tmp_path, bad) is None
