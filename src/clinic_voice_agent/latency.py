"""How long the caller waits, and where the time goes.

The framework attaches timings to each message in the conversation. This
gathers the ones a caller feels:

- `reply`: from the caller finishing to the agent's voice starting. The number that matters.
- `end_of_turn`: how long she waited before deciding the caller had finished
- `llm_first_token`: from asking the model to its first word
- `tts_first_audio`: from having text to having sound
"""

from statistics import median
from typing import Any

# name in the record -> (which speaker's message carries it, the framework's field)
STAGES = {
    "reply": ("assistant", "e2e_latency"),
    "end_of_turn": ("user", "end_of_turn_delay"),
    "llm_first_token": ("assistant", "llm_node_ttft"),
    "tts_first_audio": ("assistant", "tts_node_ttfb"),
}


def latency_of(history: Any) -> dict[str, dict[str, float]]:
    """Median and worst time for each stage, over the messages of one call."""
    seconds: dict[str, list[float]] = {}
    for item in history.items:
        role = getattr(item, "role", None)
        metrics = getattr(item, "metrics", None) or {}
        for name, (speaker, field) in STAGES.items():
            value = metrics.get(field) if role == speaker else None
            if isinstance(value, int | float) and value > 0:
                seconds.setdefault(name, []).append(round(float(value), 3))
    return {
        name: {"median": round(median(values), 3), "max": max(values), "turns": len(values)}
        for name, values in seconds.items()
    }
