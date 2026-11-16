"""Compare the three-service chain with one speech-to-speech model, on the same scripted calls.

    uv run python -m evals.compare_pipelines --runs 1 --scenarios move-scripted    # cost one call
    uv run python -m evals.compare_pipelines --runs 3                              # the batch

It starts two workers of its own under their own names (`clinic-chain`, `clinic-realtime`), so a
worker you have running is never used or stopped, and stops them at the end. Each scripted call
of evals/scenarios.yaml is spoken as real audio by `audio_caller.py` (a macOS voice) to each arm in
turn, alternating, so a slow hour of the model's service affects both. Every call is graded on
what the gateway's log and the clinic's records show, with the evals' own `grade`.

Both arms start at the identity step, in English, with the language menu off.

What is measured, per arm:
- how long the caller waited for a reply (caller stops -> her voice starts, the caller's own clock
  in `audio_caller.py`, the one measure that means the same thing in both arms)
- whether the call came out right, and how many requests the gateway refused
- whether the fixed lines (the read-back above all) were spoken as written, and whether the
  yes-check was shown the question the caller heard
- what the call used, and what that costs at the prices below

Not measured: the post-call review and the yes-check's own model use (the same in both arms), a
person's ear, Bosnian (a separate listening sample), calls on a phone line.
Costs real credit: a few cents a call. Say so before running a batch.
"""

import argparse
import asyncio
import difflib
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from statistics import median

from clinic_voice_agent.latency import percentile
from clinic_voice_agent.settings import get_settings
from evals.run import NOW, ORIGINAL, grade, load_scenarios

ARMS = {
    "chain": {
        "AGENT_NAME": "clinic-chain",
        "PIPELINE": "chain",
        "LANGUAGE_MENU": "false",
        "WORKER_PORT": "0",
    },
    "realtime": {"AGENT_NAME": "clinic-realtime", "PIPELINE": "realtime", "WORKER_PORT": "0"},
    "realtime+wait": {
        "AGENT_NAME": "clinic-realtime-wait",
        "PIPELINE": "realtime",
        "REALTIME_WAITS": "true",
        "WORKER_PORT": "0",
    },
}

# USD per million tokens unless noted. Read from OpenAI's pricing page and Deepgram's on
# 2026-11-16 (standard tier, pay as you go). Deepgram shows these as promotional prices.
PRICE = {
    "realtime_audio_in": 32.00, "realtime_audio_in_cached": 0.40, "realtime_audio_out": 64.00,
    "realtime_text_in": 4.00, "realtime_text_in_cached": 0.40, "realtime_text_out": 16.00,
    "mini_in": 0.40, "mini_in_cached": 0.10, "mini_out": 1.60,
    "transcribe_per_minute": 0.006,  # gpt-4o-transcribe: the realtime arms' side transcription
    "deepgram_stt_per_minute": 0.0048,  # nova-3 monolingual streaming
    "deepgram_tts_per_1000_chars": 0.030,  # aura-2
}  # fmt: skip


def cost_of(record: dict) -> dict[str, float]:
    """What the call's models used, in dollars (excluding the yes-check and the review)."""
    parts: dict[str, float] = {}
    for u in record.get("usage", []):
        if u["type"] == "llm_usage" and u["model"].startswith("gpt-realtime"):
            ai = u["input_audio_tokens"] - u["input_cached_audio_tokens"]
            ti = u["input_text_tokens"] - u["input_cached_text_tokens"]
            parts["realtime model"] = (
                ai * PRICE["realtime_audio_in"]
                + u["input_cached_audio_tokens"] * PRICE["realtime_audio_in_cached"]
                + ti * PRICE["realtime_text_in"]
                + u["input_cached_text_tokens"] * PRICE["realtime_text_in_cached"]
                + u["output_audio_tokens"] * PRICE["realtime_audio_out"]
                + u["output_text_tokens"] * PRICE["realtime_text_out"]
            ) / 1e6
        elif u["type"] == "llm_usage":
            fresh = u["input_tokens"] - u["input_cached_tokens"]
            parts["text model"] = (
                fresh * PRICE["mini_in"]
                + u["input_cached_tokens"] * PRICE["mini_in_cached"]
                + u["output_tokens"] * PRICE["mini_out"]
            ) / 1e6
        elif u["type"] == "stt_usage":
            rate = (
                "transcribe_per_minute" if "transcribe" in u["model"] else "deepgram_stt_per_minute"
            )
            parts["hearing"] = u["audio_duration"] / 60 * PRICE[rate]
        elif u["type"] == "tts_usage":
            parts["speaking"] = u["characters_count"] / 1000 * PRICE["deepgram_tts_per_1000_chars"]
    return parts


def plain(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def fidelity(record: dict) -> list[float]:
    """For each fixed line she was owed: how closely the closest thing she said matches it."""
    said = [plain(t["text"]) for t in record["transcript"] if t["speaker"] == "agent"]
    return [
        max((difflib.SequenceMatcher(None, plain(line), s).ratio() for s in said), default=0.0)
        for line in record.get("owed_lines", [])
    ]


def graded(scenario: dict, record: dict) -> list[str]:
    appointment = record["appointment_after"] or {}
    pair = (appointment.get("start", ORIGINAL[0]), appointment.get("status", ORIGINAL[1]))
    audit = record["audit"]
    wrong = sum(
        1 for e in audit if e["operation"] == "identity_check" and e["reason"] == "no_match"
    )
    expect = dict(scenario["expect"])
    if expect.get("outcome") == "moved" and date.today() != NOW.date():
        # The scripts name days of the week and the evals' clock is fixed to one date.
        expect["start"] = pair[0] if pair[0] != ORIGINAL[0] else "changed"
    return grade(
        expect, record["patient_id"] is not None, pair, len(record["messages"]),
        record["checks"], wrong,
    )  # fmt: skip


def start_worker(name: str, env: dict[str, str], log: Path) -> subprocess.Popen:
    process = subprocess.Popen(
        ["uv", "run", "python", "-m", "clinic_voice_agent.worker", "start"],
        env={**os.environ, **env},
        stdout=log.open("w"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    for _ in range(90):
        if "registered worker" in log.read_text():
            return process
        time.sleep(1)
    raise RuntimeError(f"the {name} worker did not register; see {log}")


def stop(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=20)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass


def call(arm: str, lines: list[str]) -> tuple[dict | None, list[float]]:
    out = subprocess.run(
        ["uv", "run", "python", "scripts/audio_caller.py", *lines],
        env={**os.environ, "AGENT_NAME": ARMS[arm]["AGENT_NAME"]},
        capture_output=True, text=True, timeout=420,
    )  # fmt: skip
    text = out.stdout
    room = re.search(r"room (test-\w+):", text)
    waits = re.search(r"reply_waits (\[.*?\])", text)
    if not room:
        return None, []
    records = sorted(get_settings().recordings_dir.glob(f"*{room.group(1)}.json"))
    return (
        json.loads(records[-1].read_text()) if records else None,
        [w for w in json.loads(waits.group(1)) if w > 0] if waits else [],
    )


def report(results: list[dict]) -> str:
    rows = ["| | " + " | ".join(ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    by = {arm: [r for r in results if r["arm"] == arm] for arm in ARMS}

    def cell(fn) -> list[str]:
        return [fn(by[arm]) if by[arm] else "-" for arm in ARMS]

    def waits(rs):
        values = [w for r in rs for w in r["waits"]]
        if not values:
            return "-"
        return (
            f"{median(values):.2f} s median, {percentile(values, 95):.2f} s p95 "
            f"({len(values)} turns)"
        )

    def passed(rs):
        return f"{sum(not r['failures'] for r in rs)} of {len(rs)} calls"

    def unsafe(rs):
        return (
            f"{sum(any('identity' in f or 'appointment' in f for f in r['failures']) for r in rs)}"
        )

    def refused(rs):
        return f"{sum(r['refused'] for r in rs) / len(rs):.1f}"

    def exact(rs):
        scores = [s for r in rs for s in r["fidelity"]]
        return (
            f"{sum(s >= 0.98 for s in scores)} of {len(scores)} (worst {min(scores):.2f})"
            if scores
            else "all by construction"
        )

    def asked_right(rs):
        both = [(r["consent_asked_right"]) for r in rs if r["consent_asked_right"] is not None]
        return f"{sum(both)} of {len(both)}" if both else "-"

    def money(rs):
        return f"${sum(sum(r['cost'].values()) for r in rs) / len(rs):.3f}"

    for label, fn in (
        ("Reply time as the caller feels it", waits),
        ("Calls that came out right", passed),
        ("Calls with a wrong outcome (identity or appointment)", unsafe),
        ("Gateway refusals per call", refused),
        ("Fixed lines spoken as written", exact),
        ("Yes-check shown the question the caller heard", asked_right),
        ("Cost per call (models in the call only)", money),
    ):
        rows.append(f"| {label} | " + " | ".join(cell(fn)) + " |")
    return "\n".join(rows)


async def main(runs: int, only: list[str] | None) -> int:
    scenarios = [s for s in load_scenarios() if "script" in s and (not only or s["id"] in only)]
    logs = Path("evals/reports")
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    workers: dict[str, subprocess.Popen] = {}
    results: list[dict] = []
    try:
        for arm, env in ARMS.items():
            workers[arm] = start_worker(arm, env, logs / f"worker-{arm}-{stamp}.log")
        for n in range(runs):
            for scenario in scenarios:
                for arm in ARMS:
                    print(f"run {n + 1}/{runs} {scenario['id']} [{arm}]", flush=True)
                    record, waits = await asyncio.to_thread(call, arm, scenario["script"])
                    if record is None:
                        print("  no record", file=sys.stderr)
                        results.append(dict(arm=arm, scenario=scenario["id"], waits=[],
                                            failures=["no record"], refused=0, fidelity=[],
                                            consent_asked_right=None, cost={}))  # fmt: skip
                        continue
                    owed = record.get("owed_lines", [])
                    seen = record.get("consent_seen", [])
                    results.append(
                        dict(
                            arm=arm,
                            scenario=scenario["id"],
                            waits=waits,
                            failures=graded(scenario, record),
                            refused=sum(e["outcome"] == "refused" for e in record["audit"]),
                            fidelity=fidelity(record),
                            consent_asked_right=(
                                all(s["asked"] in owed for s in seen) if seen and owed else None
                            ),
                            cost=cost_of(record),
                            record=record["room"],
                        )  # fmt: skip
                    )
    finally:
        for process in workers.values():
            stop(process)
    path = logs / f"pipelines-{stamp}.json"
    path.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print("\n" + report(results))
    for r in results:
        if r["failures"]:
            print(f"  [{r['arm']}] {r['scenario']}: {r['failures']}")
    print(f"\nevery call: {path}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--scenarios", nargs="*")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.runs, args.scenarios)))
