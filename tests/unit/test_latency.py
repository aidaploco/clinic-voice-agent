from types import SimpleNamespace

from clinic_voice_agent.latency import LatencyLog


def metric(kind: str, **fields):
    return type(kind, (), {})() if not fields else type(kind, (SimpleNamespace,), {})(**fields)


def test_the_three_stages_a_caller_feels_are_collected_per_turn():
    log = LatencyLog()
    log.add(metric("EOUMetrics", end_of_utterance_delay=0.61, transcription_delay=0.2))
    log.add(metric("LLMMetrics", ttft=0.52))
    log.add(metric("LLMMetrics", ttft=0.9))
    log.add(metric("LLMMetrics", ttft=0.4))
    log.add(metric("TTSMetrics", ttfb=0.18))
    assert log.summary() == {
        "end_of_turn": {"median": 0.61, "max": 0.61, "turns": 1},
        "llm_first_token": {"median": 0.52, "max": 0.9, "turns": 3},
        "tts_first_audio": {"median": 0.18, "max": 0.18, "turns": 1},
    }


def test_other_metrics_and_empty_values_are_ignored():
    log = LatencyLog()
    log.add(metric("STTMetrics", duration=1.0))
    log.add(metric("LLMMetrics", ttft=0))
    log.add(metric("TTSMetrics"))
    assert log.summary() == {}
