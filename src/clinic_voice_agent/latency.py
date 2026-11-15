"""How long the caller waits, and where the time goes.

The framework attaches timings to each message in the conversation. This
gathers the ones a caller feels:

- `reply`: from the caller finishing to the agent's voice starting. The number that matters.
- `reply_after_tool`: the same, only for replies that came after a tool ran. Those need the
  model twice, so they are the slow ones.
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
    tool_ran = False
    for item in history.items:
        role = getattr(item, "role", None)
        kind = getattr(item, "type", None)
        metrics = getattr(item, "metrics", None) or {}
        if role == "user":
            tool_ran = False
        elif kind == "function_call_output":
            tool_ran = True
        for name, (speaker, field) in STAGES.items():
            value = metrics.get(field) if role == speaker else None
            if isinstance(value, int | float) and value > 0:
                seconds.setdefault(name, []).append(round(float(value), 3))
                if name == "reply" and tool_ran:
                    seconds.setdefault("reply_after_tool", []).append(round(float(value), 3))
    # `values` keeps every turn, so many calls can be pooled into a median and a 95th percentile.
    return {
        name: {
            "median": round(median(values), 3),
            "max": max(values),
            "turns": len(values),
            "values": values,
        }
        for name, values in seconds.items()
    }


def percentile(values: list[float], share: float) -> float:
    """The value below which `share` of the turns fall (nearest rank; honest for small samples)."""
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * share // 1))  # ceiling without importing math
    return ordered[int(rank) - 1]


def pooled(records: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Every turn of every call together: median, 95th percentile, and how many turns."""
    seconds: dict[str, list[float]] = {}
    for record in records:
        for name, numbers in (record.get("latency_seconds") or {}).items():
            seconds.setdefault(name, []).extend(numbers.get("values", []))
    return {
        name: {
            "median": round(median(values), 2),
            "p95": round(percentile(values, 0.95), 2),
            "turns": len(values),
        }
        for name, values in seconds.items()
    }
