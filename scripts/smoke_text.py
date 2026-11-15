"""Hold a short text conversation with the receptionist through the agent framework.

No audio and no phone: this checks that the framework, the agent and the
language model are wired together. It makes a few real model calls.

    uv run python scripts/smoke_text.py "Hi, who am I speaking with?" "Can you move my appointment?"
"""

import asyncio
import sys

from livekit.agents import AgentSession
from livekit.plugins import openai

from clinic_voice_agent.receptionist import Receptionist
from clinic_voice_agent.settings import get_settings


async def main(lines: list[str]) -> int:
    settings = get_settings()
    if settings.openai_api_key is None:
        print("OPENAI_API_KEY is not set (see .env.example).", file=sys.stderr)
        return 2
    llm = openai.LLM(model=settings.llm_model, api_key=settings.openai_api_key.get_secret_value())
    async with AgentSession(llm=llm) as session:
        await session.start(Receptionist())
        for line in lines:
            print(f"caller: {line}")
            result = await session.run(user_input=line)
            for event in result.events:
                item = getattr(event, "item", None)
                if getattr(item, "role", None) == "assistant":
                    print(f" agent: {item.text_content}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:] or ["Hello, who is this?"])))
