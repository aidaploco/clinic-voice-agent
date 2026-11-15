"""One question to a model, answered through a function call so the answer has a shape."""

import json
from typing import Any

from livekit.agents.llm import LLM, ChatContext, FunctionTool


async def ask(llm: LLM, question: str, facts: dict[str, Any], answer: FunctionTool) -> dict:
    """The arguments the model gave to `answer`. Raises if it gave none."""
    chat = ChatContext()
    chat.add_message(role="system", content=question)
    chat.add_message(role="user", content=json.dumps(facts, ensure_ascii=False))
    reply = await llm.chat(chat_ctx=chat, tools=[answer], tool_choice="required").collect()
    if not reply.tool_calls:
        raise ValueError("the model did not answer")
    return json.loads(reply.tool_calls[0].arguments)
