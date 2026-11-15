"""How good is the post-call review? Run it on calls whose right answer is known.

    uv run python -m evals.review              # each case five times
    uv run python -m evals.review --repeat 10

Prints the false-alarm rate (truthful calls it failed) and the catch rate
(misreported calls it failed), which is what to know before trusting it.
Needs OPENAI_API_KEY.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import yaml
from livekit.plugins import openai

from clinic_voice_agent.review import check_said_matches_done
from clinic_voice_agent.settings import get_settings

CASES = Path(__file__).parent / "review_cases.yaml"


def load_cases(path: Path = CASES) -> list[dict]:
    cases = yaml.safe_load(path.read_text())
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("case ids must be unique")
    return cases


def audit_of(case: dict) -> list[dict]:
    """The gateway log such a call would have left: one committed change per entry."""
    return [
        {
            "operation": "commit_change",
            "outcome": "allowed",
            "reason": "",
            "details": {
                "kind": change["kind"],
                "confirmation": {"read_back": change["read_back"], "said": change["said"]},
            },
        }
        for change in case["changes"]
    ]


def rates(cases: list[dict], verdicts: dict[str, list[str]]) -> dict[str, tuple[int, int]]:
    """(wrong, total) for truthful calls (false alarms) and for misreported ones (missed)."""
    truthful = [v for c in cases if c["truthful"] for v in verdicts.get(c["id"], [])]
    misreported = [v for c in cases if not c["truthful"] for v in verdicts.get(c["id"], [])]
    return {
        "false_alarms": (sum(v != "pass" for v in truthful), len(truthful)),
        "missed": (sum(v == "pass" for v in misreported), len(misreported)),
    }


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args(argv)
    settings = get_settings()
    if settings.openai_api_key is None:
        print("needs OPENAI_API_KEY", file=sys.stderr)
        return 2
    llm = openai.LLM(model=settings.llm_model, api_key=settings.openai_api_key.get_secret_value())
    cases = load_cases()

    async def once(case: dict) -> tuple[str, str]:
        check = await check_said_matches_done(case["transcript"], audit_of(case), llm)
        return case["id"], check["verdict"]

    runs = await asyncio.gather(*(once(c) for c in cases for _ in range(args.repeat)))
    verdicts: dict[str, list[str]] = {}
    for case_id, verdict in runs:
        verdicts.setdefault(case_id, []).append(verdict)

    print("| Case | Should | Review said |\n|---|---|---|")
    for case in cases:
        got = verdicts[case["id"]]
        want = "pass" if case["truthful"] else "fail"
        right = sum(v == want for v in got)
        print(f"| {case['id']} | {want} | right {right}/{len(got)} |")
    summary = rates(cases, verdicts)
    for name, (wrong, total) in summary.items():
        print(f"{name}: {wrong}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
