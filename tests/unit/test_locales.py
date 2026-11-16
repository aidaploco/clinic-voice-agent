import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from clinic_voice_agent.clinic import demo_clinic
from clinic_voice_agent.locales import LOCALES, locale_of

MONDAY = datetime(2026, 11, 16, 10, 0)
SUNDAY = datetime(2026, 11, 15, 10, 0)  # so that Tuesday is a weekday name, not "tomorrow"
APPROVED = yaml.safe_load(Path("evals/languages.yaml").read_text())
OKAFOR, LINDQVIST = "Dr. Okafor", "Dr. Lindqvist"


def at(now: datetime, days: int, hour: int, minute: int = 0) -> datetime:
    return (now + timedelta(days=days)).replace(hour=hour, minute=minute)


def offer(code, now, *slots):
    locale = LOCALES[code]
    return locale.offer_sentence([(locale.when(when, now, "at"), who) for when, who in slots])


def move(code, now, was, new):
    return LOCALES[code].move_sentence("shoulder physiotherapy", was, new, now)


@pytest.mark.parametrize("code", ["en", "es", "nl", "bs"])
def test_every_language_has_every_line(code):
    locale = LOCALES[code]
    for name in (
        "greeting", "outbound_greeting", "ask_name", "ask_dob", "time_limit_goodbye", "silence_goodbye",
        "deaf_goodbye", "offer", "offer_last", "offer_with", "move", "new_doctor", "cancel", "confirm",
    ):  # fmt: skip
        assert getattr(locale, name).strip(), (code, name)
    assert bool(locale.menu.strip()) == (
        code != "en"
    )  # English is the language the menu is spoken in


def test_english_is_what_the_code_said_before():
    en = LOCALES["en"]
    assert en.greeting == (
        "Thank you for calling Quillbrook Physio. This is Emily, the clinic's automated receptionist. "
        "May I have your full name, please?"
    )
    assert offer("en", MONDAY, (at(MONDAY, 1, 10, 30), OKAFOR), (at(MONDAY, 3, 9), OKAFOR)) == (
        "I can offer you tomorrow at ten thirty in the morning, or Thursday at nine in the morning. "
        "Which would you like?"
    )
    assert offer("en", MONDAY, (at(MONDAY, 2, 9), OKAFOR), (at(MONDAY, 4, 9), LINDQVIST)) == (
        "I can offer you Wednesday at nine in the morning with Dr. Okafor, or Friday at nine in the "
        "morning with Dr. Lindqvist. Which would you like?"
    )
    three = offer("en", MONDAY, *[(at(MONDAY, d, 9), OKAFOR) for d in (1, 2, 3)])
    assert three == (
        "I can offer you tomorrow at nine in the morning, Wednesday at nine in the morning, or Thursday "
        "at nine in the morning. Which would you like?"
    )
    assert offer("en", MONDAY, (at(MONDAY, 1, 10, 30), OKAFOR)) == (
        "I can offer you tomorrow at ten thirty in the morning. Which would you like?"
    )
    # the same doctor, and English still names him: it always did
    assert move("en", MONDAY, (at(MONDAY, 1, 15, 30), OKAFOR), (at(MONDAY, 4, 9), OKAFOR)) == (
        "I'll move your shoulder physiotherapy with Dr. Okafor from tomorrow at three thirty in the "
        "afternoon to Friday at nine in the morning with Dr. Okafor. Is that right?"
    )


@pytest.mark.parametrize("code", ["es", "nl", "bs"])
def test_the_lines_the_owner_reviewed_are_in_the_code_exactly(code):
    sentences = APPROVED[code]["sentences"]
    locale = LOCALES[code]
    assert (
        locale.greeting == f"{sentences[0]} {sentences[1]}"
    )  # the greeting also asks for the name
    assert sentences[2].startswith(
        locale.ask_dob
    )  # the approved line goes on to say "day, month and year"
    assert locale.deaf_goodbye == sentences[7]


@pytest.mark.parametrize("code", ["es", "nl", "bs"])
def test_the_approved_offer_is_said_exactly_as_approved_and_then_asks_which(code):
    approved = APPROVED[code]["sentences"][3]
    # Tuesday, Wednesday and Thursday, as in the approved sentences (from a Sunday)
    said = offer(
        code,
        SUNDAY,
        (at(SUNDAY, 2, 10, 30), OKAFOR),
        (at(SUNDAY, 3, 16, 30), OKAFOR),
        (at(SUNDAY, 4, 9), OKAFOR),
    )
    assert said.startswith(approved), (said, approved)
    assert said != approved  # and it ends by asking which one


@pytest.mark.parametrize("code", ["es", "nl", "bs"])
def test_the_approved_move_read_back_is_said_exactly_as_approved(code):
    approved = APPROVED[code]["sentences"][4]
    # from tomorrow at 15:30 to Friday at 9:00, the same doctor, as approved
    said = move(code, MONDAY, (at(MONDAY, 1, 15, 30), OKAFOR), (at(MONDAY, 4, 9), OKAFOR))
    assert said == approved


def test_another_doctor_is_named_when_the_appointment_moves_to_one():
    es = move("es", MONDAY, (at(MONDAY, 1, 15, 30), OKAFOR), (at(MONDAY, 4, 9), LINDQVIST))
    assert es.endswith("al viernes a las nueve de la mañana con el doctor Lindqvist. ¿Es correcto?")
    bs = move("bs", MONDAY, (at(MONDAY, 1, 15, 30), OKAFOR), (at(MONDAY, 4, 9), LINDQVIST))
    assert bs.endswith("na petak u devet sati ujutro kod doktora Lindqvista. Je li to tačno?")


def test_bosnian_says_half_hours_as_pola_the_next_hour():
    bs = LOCALES["bs"]
    wednesday = [
        bs.when(at(MONDAY, 2, h, m), MONDAY, "at")
        for h, m in ((10, 30), (16, 30), (15, 30), (9, 0))
    ]
    assert wednesday == [
        "srijedu u pola jedanaest ujutro",
        "srijedu u pola pet poslijepodne",
        "srijedu u pola četiri poslijepodne",
        "srijedu u devet sati ujutro",
    ]
    assert bs.when(at(MONDAY, 2, 16, 30), MONDAY, "from") == "sa srijede u pola pet poslijepodne"
    assert bs.when(at(MONDAY, 4, 9), MONDAY, "to") == "na petak u devet sati ujutro"
    assert bs.when(at(MONDAY, 1, 15, 30), MONDAY, "from") == "sa sutra u pola četiri poslijepodne"


def test_spanish_and_dutch_times_and_days():
    es, nl = LOCALES["es"], LOCALES["nl"]
    assert (
        es.when(at(MONDAY, 2, 10, 30), MONDAY, "at")
        == "el miércoles a las diez y media de la mañana"
    )
    assert (
        es.when(at(MONDAY, 1, 15, 30), MONDAY, "from") == "de mañana a las tres y media de la tarde"
    )
    assert es.when(at(MONDAY, 4, 9), MONDAY, "to") == "al viernes a las nueve de la mañana"
    assert es.when(at(MONDAY, 1, 13, 30), MONDAY, "at") == "mañana a la una y media de la tarde"
    assert nl.when(at(MONDAY, 3, 9), MONDAY, "at") == "donderdag om negen uur 's ochtends"
    assert nl.when(at(MONDAY, 2, 10, 30), MONDAY, "at") == "woensdag om half elf 's ochtends"
    assert nl.when(at(MONDAY, 1, 15, 30), MONDAY, "from") == "van morgen half vier 's middags"
    assert nl.when(at(MONDAY, 4, 9), MONDAY, "to") == "naar vrijdag negen uur 's ochtends"
    assert nl.when(at(MONDAY, 2, 12, 30), MONDAY, "at") == "woensdag om half één 's middags"


def test_doctors_and_treatments_in_each_language():
    assert LOCALES["es"].practitioner("Dr. Okafor") == "el doctor Okafor"
    assert LOCALES["nl"].practitioner("Dr. Lindqvist") == "dokter Lindqvist"
    assert LOCALES["bs"].practitioner("Dr. Okafor") == "doktora Okafora"
    assert LOCALES["bs"].practitioner("Dr. Lindqvist") == "doktora Lindqvista"
    assert LOCALES["en"].practitioner("Dr. Okafor") == "Dr. Okafor"
    assert LOCALES["bs"].treatment("shoulder physiotherapy") == "fizioterapiju ramena"
    assert (
        LOCALES["es"].treatment("a treatment nobody translated") == "a treatment nobody translated"
    )


def test_a_time_with_other_minutes_is_refused_not_misspoken():
    for code in ("es", "nl", "bs"):
        with pytest.raises(ValueError):
            LOCALES[code].when(at(MONDAY, 1, 10, 45), MONDAY, "at")


@pytest.mark.parametrize("code", ["es", "nl", "bs"])
def test_every_time_the_mock_clinic_can_produce_is_worded_with_no_digits(code):
    locale = LOCALES[code]
    for days_ahead in range(0, 14):  # whatever day the call happens on
        now = MONDAY + timedelta(days=days_ahead)
        clinic = demo_clinic(now)
        times = [slot.start for slot in clinic.free_slots()]
        times += [appointment.start for appointment in clinic.appointments.values()]
        assert times
        for when in times:
            for role in ("at", "from", "to"):
                said = locale.when(when, now, role)
                assert said.strip() and not re.search(r"\d", said), (code, when, role, said)


def test_an_unknown_code_is_english():
    assert locale_of("xx").code == "en" and locale_of("ES-mx").code == "es"
