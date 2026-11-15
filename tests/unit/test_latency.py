from types import SimpleNamespace

from clinic_voice_agent.latency import latency_of


def history(*messages):
    return SimpleNamespace(items=[SimpleNamespace(role=r, metrics=m) for r, m in messages])


def test_what_the_caller_waits_for_is_gathered_per_stage():
    call = history(
        ("assistant", {}),  # the greeting answers nobody
        ("user", {"end_of_turn_delay": 0.61, "transcription_delay": 0.2}),
        ("assistant", {"e2e_latency": 1.42, "llm_node_ttft": 0.52, "tts_node_ttfb": 0.18}),
        ("user", {"end_of_turn_delay": 1.2}),
        ("assistant", {"e2e_latency": 2.9, "llm_node_ttft": 0.9, "tts_node_ttfb": 0.22}),
    )
    summary = latency_of(call)
    assert summary["reply"] == {"median": 2.16, "max": 2.9, "turns": 2, "values": [1.42, 2.9]}
    assert summary["end_of_turn"]["median"] == 0.905 and summary["end_of_turn"]["turns"] == 2
    assert summary["llm_first_token"]["max"] == 0.9
    assert summary["tts_first_audio"]["turns"] == 2


def test_a_stage_is_read_only_from_the_speaker_it_belongs_to():
    # The caller's message carrying an agent-side field must not be counted.
    assert latency_of(history(("user", {"e2e_latency": 9.0}))) == {}


def test_missing_and_zero_timings_are_ignored():
    call = history(("assistant", None), ("assistant", {"e2e_latency": 0}), ("tool", {"x": 1}))
    assert latency_of(call) == {}


def test_a_reply_that_came_after_a_tool_ran_is_counted_apart_from_the_rest():
    def item(role=None, kind=None, **metrics):
        return SimpleNamespace(role=role, type=kind, metrics=metrics)

    call = SimpleNamespace(
        items=[
            item("user"),
            item("assistant", e2e_latency=1.4),
            item("user"),
            item(kind="function_call"),
            item(kind="function_call_output"),
            item("assistant", e2e_latency=3.5),
            item("user"),
            item("assistant", e2e_latency=1.5),  # the tool's effect ended with the caller's turn
        ]
    )
    summary = latency_of(call)
    assert summary["reply"]["values"] == [1.4, 3.5, 1.5]
    assert summary["reply_after_tool"]["values"] == [3.5]


def test_calls_are_pooled_into_a_median_and_a_95th_percentile():
    from clinic_voice_agent.latency import percentile, pooled

    assert percentile([5, 1, 3, 2, 4], 0.95) == 5 and percentile([5, 1, 3, 2, 4], 0.5) == 3
    one = {"latency_seconds": {"reply": {"values": [1.0, 2.0]}}}
    two = {"latency_seconds": {"reply": {"values": [3.0, 4.0]}}}
    assert pooled([one, two, {}]) == {"reply": {"median": 2.5, "p95": 4.0, "turns": 4}}
