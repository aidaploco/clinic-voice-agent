"""Point the phone line's dispatch rule at Emily, or put it back. A dry run unless --apply.

    uv run python scripts/setup_inbound.py              # show what would change
    uv run python scripts/setup_inbound.py --apply      # change it (saves the old rule first)
    uv run python scripts/setup_inbound.py --revert     # put the saved rule back

This changes a live account: while the rule names Emily, a call to the number is dispatched to
her. The rule as it was is saved to
`.inbound-rule-backup.json` (git-ignored; it holds phone numbers) before any change.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from google.protobuf import json_format
from livekit import api

from clinic_voice_agent.allowlist import normalise
from clinic_voice_agent.inbound import agents_of, problems, replace_rule, rule_for_agent
from clinic_voice_agent.settings import get_settings

BACKUP = Path(".inbound-rule-backup.json")


async def main(apply: bool, revert: bool) -> int:
    settings = get_settings()
    if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
        print("LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET must be set")
        return 1
    lk = api.LiveKitAPI(
        settings.livekit_url,
        settings.livekit_api_key.get_secret_value(),
        settings.livekit_api_secret.get_secret_value(),
    )
    try:
        rules = (await lk.sip.list_dispatch_rule(api.ListSIPDispatchRuleRequest())).items
        trunks = (await lk.sip.list_inbound_trunk(api.ListSIPInboundTrunkRequest())).items
        if len(rules) != 1 or len(trunks) != 1:
            print(f"expected one rule and one trunk, found {len(rules)} and {len(trunks)}")
            return 1
        rule, trunk = rules[0], trunks[0]
        print(f"rule '{rule.name}' currently dispatches: {agents_of(rule) or 'no agent'}")

        if revert:
            if not BACKUP.is_file():
                print("no backup to restore")
                return 1
            saved = json_format.Parse(BACKUP.read_text(), api.SIPDispatchRuleInfo())
            print(f"restoring the saved rule (dispatches: {agents_of(saved) or 'no agent'})")
            if apply:
                await replace_rule(lk.sip, rule.sip_dispatch_rule_id, saved)
                print("done")
            else:
                print("dry run: add --apply to restore")
            return 0

        desired = rule_for_agent(rule, settings.agent_name)
        for problem in problems(
            rule, {normalise(n) for n in trunk.allowed_numbers}, set(settings.allowed_set)
        ):
            print("WARNING:", problem)
        print(f"would make it dispatch: {agents_of(desired)}")
        if agents_of(rule) == agents_of(desired):
            print("already set; nothing to do")
            return 0
        if not apply:
            print("dry run: nothing changed. Add --apply to change the rule.")
            return 0
        BACKUP.write_text(json_format.MessageToJson(rule))
        await replace_rule(lk.sip, rule.sip_dispatch_rule_id, desired)
        print(f"done. The old rule is saved in {BACKUP}; `--revert --apply` puts it back.")
        return 0
    finally:
        await lk.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.apply, args.revert)))
