"""How long the caller waits, and where the time goes.

The framework reports timings as it works. This collects the ones a caller
feels, per turn:

- `end_of_turn`: from the caller going quiet to the agent deciding they have finished
- `llm_first_token`: from asking the model to its first word
- `tts_first_audio`: from having text to having sound

Their sum is roughly the silence before each reply.
"""

from statistics import median
from typing import Any

STAGES = {
    "EOUMetrics": ("end_of_turn", "end_of_utterance_delay"),
    "LLMMetrics": ("llm_first_token", "ttft"),
    "TTSMetrics": ("tts_first_audio", "ttfb"),
}


class LatencyLog:
    def __init__(self) -> None:
        self.seconds: dict[str, list[float]] = {}

    def add(self, metric: Any) -> None:
        """Record one metric event from the framework; anything else is ignored."""
        stage = STAGES.get(type(metric).__name__)
        if stage is None:
            return
        name, field = stage
        value = getattr(metric, field, None)
        if isinstance(value, int | float) and value > 0:
            self.seconds.setdefault(name, []).append(round(float(value), 3))

    def summary(self) -> dict[str, dict[str, float]]:
        return {
            name: {"median": round(median(values), 3), "max": max(values), "turns": len(values)}
            for name, values in self.seconds.items()
        }
