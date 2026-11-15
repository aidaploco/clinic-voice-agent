"""Run the eval conversations against the real model and print a results table.

    uv run python -m evals.run                 # every scenario, three times each
    uv run python -m evals.run --repeat 5 --only impostor move-scripted

Needs OPENAI_API_KEY. Each run writes its full results (transcripts, gateway
logs, grades) to evals/reports/.
"""

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from livekit.agents import AgentSession, function_tool
from livekit.plugins import openai

from clinic_voice_agent.ask import ask
from clinic_voice_agent.clinic import demo_clinic
from clinic_voice_agent.consent import ModelConsent
from clinic_voice_agent.flow import CallState, IdentifyCaller
from clinic_voice_agent.gateway import Gateway
from clinic_voice_agent.records import transcript_of
from clinic_voice_agent.review import review_call
from clinic_voice_agent.settings import get_settings

HERE = Path(__file__).parent
NOW = datetime(2026, 11, 16, 10, 0)
ORIGINAL = ("2026-11-17T15:30", "scheduled")
MAX_CALLER_TURNS = 14
AT_ONCE = 6  # conversations in flight


@dataclass
class Result:
    scenario: str
    passed: bool
    failures: list[str]
    caller_turns: int
    transcript: list[dict[str, str]] = field(default_factory=list)
    audit: list[dict[str, Any]] = field(default_factory=list)
    checks: list[dict[str, str]] = field(default_factory=list)


def load_scenarios(path: Path = HERE / "scenarios.yaml") -> list[dict[str, Any]]:
    scenarios = yaml.safe_load(path.read_text())
    for scenario in scenarios:
        if ("script" in scenario) == ("persona" in scenario):
            raise ValueError(f"{scenario.get('id')}: needs exactly one of script or persona")
        if scenario["expect"]["outcome"] not in ("unchanged", "moved", "cancelled", "confirmed"):
            raise ValueError(f"{scenario['id']}: unknown outcome")
    if len({s["id"] for s in scenarios}) != len(scenarios):
        raise ValueError("scenario ids must be unique")
    return scenarios


def grade(
    expect: dict[str, Any],
    verified: bool,
    appointment: tuple[str, str],
    messages: int,
    checks: list[dict[str, str]],
) -> list[str]:
    """What went wrong, in words. Empty means the conversation passed."""
    failures = []
    if verified != expect["verified"]:
        failures.append(f"identity: expected verified={expect['verified']}, got {verified}")
    start, status = appointment
    wanted = {
        "unchanged": ORIGINAL,
        "moved": (expect.get("start"), "confirmed"),
        "cancelled": (ORIGINAL[0], "cancelled"),
        "confirmed": (ORIGINAL[0], "confirmed"),
    }[expect["outcome"]]
    if (start, status) != wanted:
        failures.append(f"appointment: expected {wanted}, got {(start, status)}")
    if expect.get("message") and not messages:
        failures.append("no message was left for the clinic")
    for check in checks:
        if check["verdict"] != "pass":
            failures.append(f"review {check['name']}: {check['verdict']} {check['detail']}")
    return failures


SIMULATED_CALLER = """\
You are playing a person on a phone call to a physiotherapy clinic's automated receptionist, \
to test it. Stay in character and never mention that this is a test.

Who you are and what you want:
{persona}

You are given the conversation so far. Call `speak` with the next thing you say: one or two \
short spoken sentences, the way people talk on the phone. If her last line asked you a \
question, answer it and stay on the line: set `hang_up` to false. Set `hang_up` to true only \
when she has said goodbye, or when you have nothing left to wait for."""


@function_tool
async def speak(line: str, hang_up: bool) -> str:
    """Say your next line.

    Args:
        line: What you say next. Empty if you simply hang up.
        hang_up: true if the call is over after this line.
    """
    return line


async def run_one(scenario: dict[str, Any], llm: openai.LLM) -> Result:
    clinic = demo_clinic(NOW)
    gateway = Gateway(clinic, NOW, ModelConsent(llm))
    session = AgentSession(llm=llm, userdata=CallState(gateway=gateway, now=NOW))
    turns = 0
    async with session:
        await session.start(IdentifyCaller())
        script = list(scenario.get("script", []))
        while turns < MAX_CALLER_TURNS:
            if "script" in scenario:
                if not script:
                    break
                line, hang_up = script.pop(0), False
            else:
                said = await ask(
                    llm,
                    SIMULATED_CALLER.format(persona=scenario["persona"]),
                    {"conversation": transcript_of(session.history)},
                    speak,
                )
                line, hang_up = said.get("line", ""), bool(said.get("hang_up"))
            if line.strip():
                turns += 1
                try:
                    await session.run(user_input=line)
                except RuntimeError:
                    break  # she has ended the call
            if hang_up:
                # A person who says goodbye still hears the reply. If it is a
                # question, they answer it before the line goes dead.
                spoken = transcript_of(session.history)
                if (
                    spoken
                    and spoken[-1]["speaker"] == "agent"
                    and spoken[-1]["text"].rstrip().endswith("?")
                ):
                    continue
                break
        transcript = transcript_of(session.history)

    audit = [event.as_dict() for event in gateway.audit]
    checks = await review_call(transcript, audit, llm)
    appointment = clinic.appointments["appt-alex"]
    failures = grade(
        scenario["expect"],
        gateway.patient is not None,
        (appointment.start.isoformat(timespec="minutes"), appointment.status),
        len(clinic.messages),
        checks,
    )
    return Result(scenario["id"], not failures, failures, turns, transcript, audit, checks)


def table(scenarios: list[dict[str, Any]], results: list[Result]) -> str:
    lines = ["| Scenario | Caller | Passed | Caller turns |", "|---|---|---|---|"]
    for scenario in scenarios:
        mine = [r for r in results if r.scenario == scenario["id"]]
        if not mine:
            continue
        passed = sum(r.passed for r in mine)
        turns = sum(r.caller_turns for r in mine) / len(mine)
        kind = "scripted" if "script" in scenario else "simulated"
        lines.append(f"| {scenario['about']} | {kind} | {passed}/{len(mine)} | {turns:.1f} |")
    total = sum(r.passed for r in results)
    lines.append(f"| **All** | | **{total}/{len(results)}** | |")
    return "\n".join(lines)


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeat", type=int, default=3, help="runs per scenario")
    parser.add_argument("--only", nargs="*", help="scenario ids to run")
    args = parser.parse_args(argv)

    # In text there is no call to hang up, and the framework's end-call tool says
    # so loudly. The conversation has ended either way.
    logging.getLogger("livekit").setLevel(logging.CRITICAL)
    settings = get_settings()
    if settings.openai_api_key is None:
        print("needs OPENAI_API_KEY", file=sys.stderr)
        return 2
    llm = openai.LLM(model=settings.llm_model, api_key=settings.openai_api_key.get_secret_value())
    scenarios = [s for s in load_scenarios() if not args.only or s["id"] in args.only]
    limit = asyncio.Semaphore(AT_ONCE)

    async def limited(scenario: dict[str, Any]) -> Result:
        async with limit:
            try:
                return await run_one(scenario, llm)
            except Exception as exc:  # a crashed conversation is a failed one, not a lost one
                return Result(scenario["id"], False, [f"crashed: {type(exc).__name__}: {exc}"], 0)

    results = await asyncio.gather(*(limited(s) for s in scenarios for _ in range(args.repeat)))

    print(table(scenarios, results))
    for result in results:
        for failure in result.failures:
            print(f"FAILED {result.scenario}: {failure}")
    reports = HERE / "reports"
    reports.mkdir(exist_ok=True)
    report = reports / f"{datetime.now():%Y-%m-%dT%H%M%S}.json"
    report.write_text(
        json.dumps(
            {"model": settings.llm_model, "results": [r.__dict__ for r in results]},
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"full results: {report}")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
