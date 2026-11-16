import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import pytest
from livekit.agents.llm import StopResponse

from clinic_voice_agent.clinic import demo_clinic
from clinic_voice_agent.flow import CallState, IdentifyCaller
from clinic_voice_agent.gateway import Gateway
from clinic_voice_agent.menu import ChooseLanguage, digit_to_language, menu_lines
from clinic_voice_agent.timeline import Timeline

NOW = datetime(2026, 11, 16, 10, 0)


class Handle:
    async def wait_for_playout(self):
        pass


class Session:
    def __init__(self):
        self.said = []  # (text, has_audio, interruptible)
        self.next_agent = None

    def say(self, text, audio=None, allow_interruptions=True):
        self.said.append((text, audio is not None, allow_interruptions))
        return Handle()

    def on(self, name, fn):
        self.listeners = [*getattr(self, "listeners", []), fn]

    def off(self, name, fn):
        self.listeners.remove(fn)

    def caller_changes_state(self, state):
        for fn in list(self.listeners):
            fn(SimpleNamespace(new_state=state))

    def update_agent(self, agent):
        self.next_agent = agent


class Voices:
    def __init__(self):
        self.warmed = []

    def agent_args(self, language):
        return {}

    async def warm_menu(self, lines):
        self.warmed.append(lines)

    def menu_audio(self, language, text):
        return object()


def make(phone=False, direction="inbound", answer=0.05, give_up=0.2):
    gateway = Gateway(demo_clinic(NOW), NOW, consent=None)
    state = CallState(gateway=gateway, now=NOW, voices=Voices(), phone=phone)
    step = ChooseLanguage(
        direction, state, Timeline(), answer_seconds=answer, give_up_seconds=give_up
    )
    return step, state, Session()


async def run(step, session, during=None):
    """Enter the step; `during` is an async function that acts while it waits."""
    with patch.object(ChooseLanguage, "session", PropertyMock(return_value=session)):
        entering = asyncio.create_task(step.on_enter())
        if during:
            await asyncio.sleep(0.01)
            await during()
        await entering


def turn(text):
    return SimpleNamespace(text_content=text)


async def test_the_lines_are_said_whole_and_in_order_then_with_no_answer_she_asks_in_english():
    step, state, session = make()
    await run(step, session)
    texts = [t for t, _, _ in session.said]
    assert texts[0].startswith("Thank you for calling") and "full name" not in texts[0]
    assert texts[1:] == [
        "Para continuar en español, diga español.",
        "Voor Nederlands, zeg Nederlands.",
        "Za bosanski, recite bosanski.",
    ]
    assert [a for _, a, _ in session.said] == [False, True, True, True]
    assert not any(interruptible for _, _, interruptible in session.said)  # none can be cut
    nxt = session.next_agent
    assert isinstance(nxt, IdentifyCaller) and nxt._language == "en" and nxt._question_only
    assert state.gateway.language == "en"


async def test_silence_never_ends_the_call_it_hands_on_in_english():
    step, state, session = make()
    await run(step, session)
    assert isinstance(session.next_agent, IdentifyCaller)  # not a goodbye, not a hang-up


async def test_a_phone_caller_is_told_which_key_and_a_browser_caller_is_not():
    step, _, phone = make(phone=True)
    await run(step, phone)
    assert [t for t, _, _ in phone.said[1:]] == [
        "Para continuar en español, diga español o pulse el 1.",
        "Voor Nederlands, zeg Nederlands of druk op de 2.",
        "Za bosanski, recite bosanski ili pritisnite 3.",
    ]
    assert menu_lines(False)[0][1] == "Para continuar en español, diga español."


async def test_the_audio_of_the_lines_is_prepared_all_at_once_before_they_are_said():
    step, state, session = make()
    await run(step, session)
    assert state.voices.warmed == [menu_lines(False)]


@pytest.mark.parametrize(("key", "language"), [("1", "es"), ("2", "nl"), ("3", "bs")])
async def test_a_key_press_chooses_the_language(key, language):
    step, state, session = make(answer=5.0, give_up=10.0)
    await run(step, session, during=lambda: _press(state, key))
    nxt = session.next_agent
    assert nxt._language == language and nxt._switched and not nxt._question_only
    assert state.gateway.language == language


async def _press(state, key):
    state.choose(digit_to_language(key))


def test_keys_that_are_not_on_the_menu_choose_nothing():
    assert digit_to_language("0") is None and digit_to_language("#") is None


async def test_saying_a_language_chooses_it_and_no_model_answers():
    step, state, session = make(answer=5.0, give_up=10.0)

    async def say_it():
        with pytest.raises(StopResponse):
            await step.on_user_turn_completed(None, turn("Bosanski, molim."))

    await run(step, session, during=say_it)
    assert session.next_agent._language == "bs"


async def test_words_that_are_not_a_language_are_ignored_and_the_wait_still_ends_in_english():
    step, state, session = make()

    async def say_hello():
        with pytest.raises(StopResponse):
            await step.on_user_turn_completed(None, turn("Hello?"))

    await run(step, session, during=say_hello)
    nxt = session.next_agent
    assert nxt._language == "en" and nxt._question_only  # "Hello?" did not pick anything


async def test_a_caller_who_keeps_talking_gets_no_more_than_the_longest_wait():
    step, state, session = make(answer=0.05, give_up=0.15)

    async def chatter():
        for _ in range(10):
            with pytest.raises(StopResponse):
                await step.on_user_turn_completed(None, turn("uh"))
            await asyncio.sleep(0.03)

    await asyncio.wait_for(run(step, session, during=chatter), timeout=2)
    assert session.next_agent._language == "en"


async def test_nothing_is_expected_to_be_understood_while_choosing_and_afterwards_it_is():
    step, state, session = make(answer=5.0, give_up=10.0)
    seen = []

    async def look():
        seen.append(state.choosing)
        state.choose("es")

    await run(step, session, during=look)
    assert seen == [True] and state.choosing is False and state.choice is None


async def test_what_the_menu_heard_and_chose_is_in_the_timeline():
    step, state, session = make(answer=5.0, give_up=10.0)

    async def say_it():
        with pytest.raises(StopResponse):
            await step.on_user_turn_completed(None, turn("Nederlands"))

    await run(step, session, during=say_it)
    assert [e["kind"] for e in step._timeline.entries] == [
        "menu_spoken",
        "menu_heard",
        "menu_chosen",
    ]
    heard, chosen = step._timeline.entries[1:]
    assert heard["text"] == "Nederlands" and heard["language"] == "nl"
    assert chosen["language"] == "nl" and chosen["how"] == "chosen"


def test_the_timeline_counts_seconds_from_the_start_and_leaves_out_what_is_empty():
    now = [100.0]
    line = Timeline(clock=lambda: now[0])
    now[0] = 102.504
    line.add("words", text="hi", language=None)
    assert line.entries == [{"t": 2.5, "kind": "words", "text": "hi"}]


async def test_a_caller_who_starts_speaking_inside_the_window_is_waited_for():
    """Their words arrive after the window would have closed: the speech restarts it."""
    step, state, session = make(answer=0.1, give_up=1.0)

    async def speak_late():
        session.caller_changes_state("speaking")
        await asyncio.sleep(0.07)
        session.caller_changes_state("listening")
        await asyncio.sleep(0.07)  # 0.14 s after they began: past the first window of 0.1 s
        with pytest.raises(StopResponse):
            await step.on_user_turn_completed(None, turn("Español."))

    await run(step, session, during=speak_late)
    assert session.next_agent._language == "es" and not session.next_agent._question_only
    assert session.listeners == []


async def test_a_caller_who_only_coughs_still_ends_in_english_after_the_longest_wait():
    step, state, session = make(answer=0.05, give_up=0.15)

    async def cough():
        for _ in range(8):
            session.caller_changes_state("speaking")
            await asyncio.sleep(0.03)

    await asyncio.wait_for(run(step, session, during=cough), timeout=2)
    assert session.next_agent._language == "en" and session.next_agent._question_only
