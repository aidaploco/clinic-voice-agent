"""Speak the same call to the worker several times and report how long replies took.

    uv run python -m clinic_voice_agent.worker start        # terminal 1
    uv run python scripts/measure_latency.py --calls 5      # terminal 2

Every turn of every call is pooled, so the median and the 95th percentile are over
turns, not over calls. The caller's voice is the Mac's built-in one (free); each call
costs what the agent's side costs: a few cents of speech and model use.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from clinic_voice_agent.latency import pooled
from clinic_voice_agent.settings import get_settings

LINES = [
    "My name is Alex Rivera.",
    "The fourteenth of March, nineteen ninety.",
    "I need to move my appointment.",
    "The first one, please.",
    "Yes, that's right.",
]

ROWS = [
    ("reply", "Caller finishes -> her voice starts (all replies)"),
    ("reply_after_tool", "Same, only replies that follow a tool call"),
    ("end_of_turn", "Waiting to be sure the caller has finished"),
    ("llm_first_token", "Model: first word"),
    ("tts_first_audio", "Speech: first sound"),
]


async def one_call() -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable, "scripts/audio_caller.py", *LINES,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )  # fmt: skip
    await process.wait()


def table(numbers: dict[str, dict[str, float]]) -> str:
    lines = ["| What | Median (s) | 95th percentile (s) | Turns |", "|---|---|---|---|"]
    for key, label in ROWS:
        if key in numbers:
            n = numbers[key]
            lines.append(f"| {label} | {n['median']:.2f} | {n['p95']:.2f} | {n['turns']} |")
    return "\n".join(lines)


async def main(calls: int) -> int:
    load_dotenv()
    began = time.time()
    for number in range(1, calls + 1):
        print(f"call {number} of {calls}", flush=True)
        await one_call()
    folder: Path = get_settings().recordings_dir
    records = [
        json.loads(path.read_text())
        for path in sorted(folder.glob("*.json"))
        if path.stat().st_mtime >= began
    ]
    print(f"{len(records)} call records")
    if not records:
        return 1
    print(table(pooled(records)))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--calls", type=int, default=5)
    sys.exit(asyncio.run(main(parser.parse_args().calls)))
