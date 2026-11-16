"""The language menu: the first step of a call, decided in code.

Emily says who she is, then offers each other language in its own voice. The caller answers by
saying the language or, on a phone, pressing its key. This step has no model: its only outcomes
are a language, or, after a silence, English. It never ends the call and never guesses from
words that are not a language's name, because a transcriber's hearing of one word on a phone
line is not something a call should hinge on (ADR-0011).

While the lines play they cannot be interrupted, which is what keeps them whole: on a phone the
caller's "Hello?" at pickup, an echo or a cough would otherwise cut one off and the rest would
play on regardless. A key press works at any moment.

Then comes a pause for the answer. Speech that is not a language (a name, "Hello?") is heard
and ignored, and gives the caller a little longer; silence, or too much of it, means English.
"""

import asyncio
from typing import Any

from livekit import rtc
from livekit.agents import Agent, llm
from livekit.agents.llm import StopResponse

from clinic_voice_agent.choice import KEYS, chosen_language
from clinic_voice_agent.flow import CallState, IdentifyCaller, _voice_args, split_opening
from clinic_voice_agent.locales import LOCALES, locale_of
from clinic_voice_agent.timeline import Timeline

# After the last line, how long the caller has to answer; and the most the whole wait can reach
# however much is said that is not a language.
ANSWER_SECONDS = 4.0
GIVE_UP_SECONDS = 12.0


def menu_lines(phone: bool, current: str = "en") -> list[tuple[str, str]]:
    """(language, line) for each language offered, in the order they are said."""
    return [
        (code, locale.menu_line(phone))
        for code, locale in LOCALES.items()
        if code != current and locale.menu
    ]


class ChooseLanguage(Agent):
    def __init__(
        self,
        direction: str,
        state: CallState,
        timeline: Timeline | None = None,
        answer_seconds: float = ANSWER_SECONDS,
        give_up_seconds: float = GIVE_UP_SECONDS,
    ) -> None:
        self._direction = direction
        self._state = state
        self._timeline = timeline or Timeline()
        self._answer_seconds = answer_seconds
        self._give_up_seconds = give_up_seconds
        self._heard = asyncio.Event()  # the caller is speaking, or said what was not a choice
        # The transcriber for this step hears the language names (voice.Voices, "menu").
        super().__init__(
            instructions="You only offer the caller a choice of language.",
            **(_voice_args(state, "menu")),
        )

    async def on_user_turn_completed(self, turn_ctx: llm.ChatContext, new_message: Any) -> None:
        """Every turn is read here, in code. No model answers this step."""
        said = new_message.text_content or ""
        language = chosen_language(said)
        self._timeline.add("menu_heard", text=said, language=language)
        if language is not None:
            self._state.choose(language)
        else:
            self._heard.set()
        raise StopResponse()

    async def on_enter(self) -> None:
        state = self._state
        state.choosing = True
        state.choice = asyncio.get_running_loop().create_future()
        language, how = "en", "no answer"

        def on_user_state(event: Any) -> None:
            # A caller who has started to speak is not yet answered: their words reach us a
            # second or two after they stop (the end of the turn, then the transcriber).
            self._timeline.add("menu_user", to=str(event.new_state))
            self._heard.set()

        self.session.on("user_state_changed", on_user_state)
        try:
            await self._speak()
            language, how = await self._wait_for_choice(state.choice)
        finally:
            self.session.off("user_state_changed", on_user_state)
            state.choosing = False
            state.choice = None
        self._timeline.add("menu_chosen", language=language, how=how)
        state.gateway.language = language
        self.session.update_agent(self._next(language, how))

    async def _speak(self) -> None:
        state = self._state
        opening = locale_of("en")
        intro = opening.outbound_greeting if self._direction == "outbound" else opening.greeting
        handles = [self.session.say(split_opening(intro)[0], allow_interruptions=False)]
        if state.voices is not None:
            lines = menu_lines(state.phone)
            await state.voices.warm_menu(lines)
            for code, text in lines:
                handles.append(
                    self.session.say(
                        text,
                        audio=state.voices.menu_audio(code, text),
                        allow_interruptions=False,
                    )
                )
        await handles[-1].wait_for_playout()
        self._timeline.add("menu_spoken")

    async def _wait_for_choice(self, choice: asyncio.Future[str]) -> tuple[str, str]:
        """The language, and how it was chosen: spoken, by a key, or by no answer (English)."""
        loop = asyncio.get_running_loop()
        started = loop.time()
        while True:
            left = min(self._answer_seconds, self._give_up_seconds - (loop.time() - started))
            if left <= 0:
                return "en", "no answer"
            self._heard.clear()
            heard = asyncio.ensure_future(self._heard.wait())
            try:
                await asyncio.wait(
                    {choice, heard}, timeout=left, return_when=asyncio.FIRST_COMPLETED
                )
            finally:
                heard.cancel()
            if choice.done():
                return choice.result(), "chosen"
            if not self._heard.is_set():
                return "en", "no answer"
            # The caller is speaking, or said something that is not a language: a little longer.

    def _next(self, language: str, how: str) -> Agent:
        if how == "no answer":
            return IdentifyCaller(self._direction, "en", state=self._state, question_only=True)
        return IdentifyCaller(self._direction, language, switched=True, state=self._state)


def digit_to_language(digit: str) -> str | None:
    return KEYS.get(digit)


def watch_keypad(room: rtc.Room, state: CallState, timeline: Timeline) -> None:
    """Route the caller's key presses to the language menu."""

    def on_key(event: rtc.SipDTMF) -> None:
        language = digit_to_language(event.digit)
        timeline.add("key", digit=event.digit, language=language)
        if language is not None:
            state.choose(language)

    room.on("sip_dtmf_received", on_key)
