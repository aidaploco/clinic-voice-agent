"""What the receptionist says in each language, when the words come from code and not the model.

Some lines are not left to the model: the offer of free times, the read-back of a change, the
greeting, the goodbyes. Code words them, so they are fast and exact, and so a read-back is the
sentence the caller is asked to say yes to. This module holds those lines for English, Mexican
Spanish, Dutch and Bosnian, and how a time and a day are said in each.

Where it comes from:
- English is what the code said before this module existed, word for word.
- The greeting, the offer, the move read-back and the "cannot hear you" apology for Spanish, Dutch
  and Bosnian are the sentences in `evals/languages.yaml`, which the owner (a native speaker of all
  three) reviewed, with her correction that Bosnian says half hours as "pola" the next hour.
- The cancel and confirm read-backs, the menu lines, the outbound greeting and the time-limit and
  silence goodbyes are drafts by analogy, not yet reviewed. `scripts/print_locales.py` prints
  every line in every language for reading.

Only what the mock clinic can produce is covered: times on the hour or the half hour, weekdays,
"today" and "tomorrow", and one treatment. Anything else falls back to the English wording of
that part (a treatment) or raises (a time with other minutes), and a test fails first, because
the clinic's slots are all checked against every language.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from clinic_voice_agent import spoken

CLINIC_NAME = "Quillbrook Physio"
AGENT_NAME = "Emily"

WEEKDAYS = {
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    "nl": ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"],
    # Bosnian: the form after "u" and "na" (accusative), and after "sa" (genitive).
    "bs": ["ponedjeljak", "utorak", "srijedu", "četvrtak", "petak", "subotu", "nedjelju"],
    "bs_from": ["ponedjeljka", "utorka", "srijede", "četvrtka", "petka", "subote", "nedjelje"],
}

HOURS = {
    "es": ["doce", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once"],
    "nl": ["twaalf", "één", "twee", "drie", "vier", "vijf", "zes", "zeven", "acht", "negen", "tien", "elf"],
    "bs": ["dvanaest", "jedan", "dva", "tri", "četiri", "pet", "šest", "sedam", "osam", "devet", "deset", "jedanaest"],
}  # fmt: skip


def _check_minute(when: datetime) -> None:
    if when.minute not in (0, 30):
        raise ValueError(f"only times on the hour or half hour are worded, not {when:%H:%M}")


# ----- Spanish ------------------------------------------------------------------------------


def es_clock(when: datetime) -> str:
    """ "las diez y media de la mañana", "la una y media de la tarde", "las nueve de la mañana"."""
    _check_minute(when)
    hour = when.hour % 12
    article = "la" if hour == 1 else "las"
    half = " y media" if when.minute else ""
    part = "de la mañana" if when.hour < 12 else "de la tarde" if when.hour < 20 else "de la noche"
    if when.hour == 12 and not when.minute:
        return "las doce del día"
    return f"{article} {HOURS['es'][hour]}{half} {part}"


def es_when(when: datetime, now: datetime, role: str = "at") -> str:
    days = (when.date() - now.date()).days
    weekday = WEEKDAYS["es"][when.weekday()]
    clock = es_clock(when)
    if role == "from":
        day = "de hoy" if days == 0 else "de mañana" if days == 1 else f"del {weekday}"
    elif role == "to":
        day = "para hoy" if days == 0 else "para mañana" if days == 1 else f"al {weekday}"
    else:
        day = "hoy" if days == 0 else "mañana" if days == 1 else f"el {weekday}"
    return f"{day} a {clock}"


# ----- Dutch --------------------------------------------------------------------------------


def nl_clock(when: datetime) -> str:
    """ "half elf 's ochtends", "negen uur 's ochtends": half hours are half of the next hour."""
    _check_minute(when)
    hour = when.hour % 12
    part = (
        "'s nachts" if when.hour < 5 else "'s ochtends" if when.hour < 12
        else "'s middags" if when.hour < 18 else "'s avonds"
    )  # fmt: skip
    if when.minute:
        return f"half {HOURS['nl'][(hour + 1) % 12]} {part}"
    return f"{HOURS['nl'][hour]} uur {part}"


def nl_when(when: datetime, now: datetime, role: str = "at") -> str:
    days = (when.date() - now.date()).days
    day = "vandaag" if days == 0 else "morgen" if days == 1 else WEEKDAYS["nl"][when.weekday()]
    clock = nl_clock(when)
    if role == "from":
        return f"van {day} {clock}"
    if role == "to":
        return f"naar {day} {clock}"
    return f"{day} om {clock}"


# ----- Bosnian ------------------------------------------------------------------------------


def bs_clock(when: datetime) -> str:
    """ "pola jedanaest ujutro" (10:30), "devet sati ujutro" (9:00): half hours are "pola" the next hour."""
    _check_minute(when)
    hour = when.hour % 12
    part = (
        "noću" if when.hour < 5 else "ujutro" if when.hour < 12
        else "poslijepodne" if when.hour < 18 else "uvečer"
    )  # fmt: skip
    if when.minute:
        return f"pola {HOURS['bs'][(hour + 1) % 12]} {part}"
    if hour == 1:
        unit = "jedan sat"
    else:
        unit = f"{HOURS['bs'][hour]} {'sata' if 2 <= hour <= 4 else 'sati'}"
    return f"{unit} {part}"


def bs_when(when: datetime, now: datetime, role: str = "at") -> str:
    days = (when.date() - now.date()).days
    clock = bs_clock(when)
    if role == "from":
        day = (
            "danas" if days == 0 else "sutra" if days == 1 else WEEKDAYS["bs_from"][when.weekday()]
        )
        return f"sa {day} u {clock}"
    day = "danas" if days == 0 else "sutra" if days == 1 else WEEKDAYS["bs"][when.weekday()]
    if role == "to":
        return f"na {day} u {clock}"
    return f"{day} u {clock}"


# ----- English: exactly what the code said before -------------------------------------------


def en_when(when: datetime, now: datetime, role: str = "at") -> str:
    said = spoken.say_when(when, now)
    return f"from {said}" if role == "from" else f"to {said}" if role == "to" else said


# ----- names of things ----------------------------------------------------------------------

TREATMENTS = {
    "shoulder physiotherapy": {
        "es": "fisioterapia de hombro",
        "nl": "schoudertherapie",
        "bs": "fizioterapiju ramena",  # accusative, as every Bosnian template needs it
    }
}


def _treatment(language: str) -> Callable[[str], str]:
    return lambda name: TREATMENTS.get(name, {}).get(language, name)


def _doctor(prefix: str, genitive_a: bool = False) -> Callable[[str], str]:
    """ "Dr. Okafor" as a person is addressed in the language; "Okafora" for Bosnian after "kod"."""

    def say(name: str) -> str:
        if not name.startswith("Dr. "):
            return name
        surname = name.removeprefix("Dr. ")
        if genitive_a and surname[-1] not in "aeiou":
            surname += "a"
        return f"{prefix} {surname}"

    return say


@dataclass(frozen=True)
class Locale:
    code: str
    llm_language: str  # what the model is told to speak
    greeting: str  # the first thing said on a call that came in; ends by asking for the name
    outbound_greeting: str
    menu: str  # said in this language's own voice, offering to continue in it
    ask_name: str  # first words after switching to this language, before the name is known
    ask_dob: str  # ... after the name is known
    time_limit_goodbye: str
    silence_goodbye: str
    deaf_goodbye: str
    offer: str  # {first} is the first time, {rest} the others (", B, or C"): a verb may sit between
    offer_last: str  # joins the last time: ", or "
    offer_with: str  # "{when} with {practitioner}", when the practitioners differ
    move: str  # {new_doctor} is the clause below, or nothing
    new_doctor: str  # " with {practitioner}": the doctor the appointment moves to
    always_names_new_doctor: bool  # English always did; the others only when it is another doctor
    cancel: str
    confirm: str
    when: Callable[[datetime, datetime, str], str]
    treatment: Callable[[str], str]
    practitioner: Callable[[str], str]

    def offer_sentence(self, times: list[tuple[str, str]]) -> str:
        """The sentence offering `times`, each as (when, practitioner), as said to a caller."""
        names = {practitioner for _, practitioner in times}
        items = [
            when if len(names) == 1
            else self.offer_with.format(when=when, practitioner=self.practitioner(practitioner))
            for when, practitioner in times
        ]  # fmt: skip
        rest = ""
        if len(items) > 1:
            middle = items[1:-1]
            rest = (", " + ", ".join(middle) if middle else "") + self.offer_last + items[-1]
        return self.offer.format(first=items[0], rest=rest)

    def cancel_sentence(self, treatment: str, doctor: str, when: datetime, now: datetime) -> str:
        return self.cancel.format(
            treatment=self.treatment(treatment),
            practitioner=self.practitioner(doctor),
            at=self.when(when, now, "at"),
        )

    def confirm_sentence(self, treatment: str, doctor: str, when: datetime, now: datetime) -> str:
        return self.confirm.format(
            treatment=self.treatment(treatment),
            practitioner=self.practitioner(doctor),
            at=self.when(when, now, "at"),
        )

    def move_sentence(
        self,
        treatment: str,
        was: tuple[datetime, str],
        new: tuple[datetime, str],
        now: datetime,
    ) -> str:
        """The read-back of a move, from (when, doctor) to (when, doctor)."""
        (was_when, was_doctor), (new_when, new_doctor) = was, new
        clause = ""
        if self.always_names_new_doctor or new_doctor != was_doctor:
            clause = self.new_doctor.format(practitioner=self.practitioner(new_doctor))
        return self.move.format(
            treatment=self.treatment(treatment),
            practitioner=self.practitioner(was_doctor),
            from_=self.when(was_when, now, "from"),
            to=self.when(new_when, now, "to"),
            new_doctor=clause,
        )


LOCALES: dict[str, Locale] = {
    "en": Locale(
        code="en",
        llm_language="English",
        greeting=(
            f"Thank you for calling {CLINIC_NAME}. This is {AGENT_NAME}, the clinic's automated "
            "receptionist. May I have your full name, please?"
        ),
        outbound_greeting=(
            f"Hello, this is {AGENT_NAME}, the automated assistant at {CLINIC_NAME}, calling about "
            "an appointment. May I have your full name, please?"
        ),
        menu="",
        ask_name="Of course. May I have your full name, please?",
        ask_dob="Thanks. And your date of birth, please?",
        time_limit_goodbye="I'm sorry, we've reached the time limit for this call. Goodbye.",
        silence_goodbye="I haven't heard anything, so I'll end the call now. Goodbye.",
        deaf_goodbye="I'm sorry, I can't hear you properly. Please try calling again. Goodbye.",
        offer="I can offer you {first}{rest}. Which would you like?",
        offer_last=", or ",
        offer_with="{when} with {practitioner}",
        move="I'll move your {treatment} with {practitioner} {from_} {to}{new_doctor}. Is that right?",
        new_doctor=" with {practitioner}",
        always_names_new_doctor=True,
        cancel="I'll cancel your {treatment} with {practitioner} {at}. Is that right?",
        confirm="I'll put you down as coming to your {treatment} with {practitioner} {at}. Is that right?",
        when=en_when,
        treatment=lambda name: name,
        practitioner=lambda name: name,
    ),
    "es": Locale(
        code="es",
        llm_language="Mexican Spanish",
        greeting=(
            f"Gracias por llamar a {CLINIC_NAME}. Soy {AGENT_NAME}, la recepcionista automática "
            "de la clínica. ¿Me puede dar su nombre completo, por favor?"
        ),
        outbound_greeting=(
            f"Hola, le habla {AGENT_NAME}, la asistente automática de {CLINIC_NAME}. Le llamo por "
            "una cita. ¿Me puede dar su nombre completo, por favor?"
        ),
        menu="Para continuar en español, diga español.",
        ask_name="Claro, continuamos en español. ¿Me puede dar su nombre completo, por favor?",
        ask_dob="Gracias. ¿Y su fecha de nacimiento, por favor?",
        time_limit_goodbye="Lo siento, hemos llegado al límite de tiempo de esta llamada. Adiós.",
        silence_goodbye="No he escuchado nada, así que terminaré la llamada. Adiós.",
        deaf_goodbye="Lo siento, no logro escucharle bien. Por favor, intente llamar de nuevo. Adiós.",
        offer="Le puedo ofrecer {first}{rest}. ¿Cuál prefiere?",
        offer_last=", o ",
        offer_with="{when} con {practitioner}",
        move="Voy a cambiar su {treatment} con {practitioner} {from_} {to}{new_doctor}. ¿Es correcto?",
        new_doctor=" con {practitioner}",
        always_names_new_doctor=False,
        cancel="Voy a cancelar su cita de {treatment} con {practitioner} {at}. ¿Es correcto?",
        confirm="Voy a confirmar su asistencia a su cita de {treatment} con {practitioner} {at}. ¿Es correcto?",
        when=es_when,
        treatment=_treatment("es"),
        practitioner=_doctor("el doctor"),
    ),
    "nl": Locale(
        code="nl",
        llm_language="Dutch",
        greeting=(
            f"Bedankt voor het bellen naar {CLINIC_NAME}. U spreekt met {AGENT_NAME}, de "
            "automatische receptioniste van de praktijk. Mag ik uw volledige naam, alstublieft?"
        ),
        outbound_greeting=(
            f"Hallo, u spreekt met {AGENT_NAME}, de automatische assistent van {CLINIC_NAME}. Ik "
            "bel over een afspraak. Mag ik uw volledige naam, alstublieft?"
        ),
        menu="Voor Nederlands, zeg Nederlands.",
        ask_name="Prima, we gaan verder in het Nederlands. Mag ik uw volledige naam, alstublieft?",
        ask_dob="Dank u. En uw geboortedatum, alstublieft?",
        time_limit_goodbye="Het spijt me, we hebben de tijdslimiet van dit gesprek bereikt. Tot ziens.",
        silence_goodbye="Ik hoor niets, dus ik beëindig het gesprek. Tot ziens.",
        deaf_goodbye="Het spijt me, ik kan u niet goed horen. Probeert u het later nog eens. Tot ziens.",
        offer="Ik kan u {first} aanbieden{rest}. Welke past u het best?",
        offer_last=", of ",
        offer_with="{when} bij {practitioner}",
        move="Ik verplaats uw {treatment} bij {practitioner} {from_} {to}{new_doctor}. Klopt dat?",
        new_doctor=" bij {practitioner}",
        always_names_new_doctor=False,
        cancel="Ik annuleer uw afspraak voor {treatment} bij {practitioner} {at}. Klopt dat?",
        confirm="Ik noteer dat u komt voor uw afspraak voor {treatment} bij {practitioner} {at}. Klopt dat?",
        when=nl_when,
        treatment=_treatment("nl"),
        practitioner=_doctor("dokter"),
    ),
    "bs": Locale(
        code="bs",
        llm_language="Bosnian (Latin script)",
        greeting=(
            f"Hvala što ste nazvali {CLINIC_NAME}. Ja sam {AGENT_NAME}, automatska recepcionerka "
            "klinike. Možete li mi reći svoje puno ime, molim vas?"
        ),
        outbound_greeting=(
            f"Dobar dan, ovdje {AGENT_NAME}, automatska asistentica klinike {CLINIC_NAME}. Zovem "
            "zbog termina. Možete li mi reći svoje puno ime, molim vas?"
        ),
        menu="Za bosanski, recite bosanski.",
        ask_name="U redu, nastavljamo na bosanskom. Možete li mi reći svoje puno ime, molim vas?",
        ask_dob="Hvala. A vaš datum rođenja, molim vas?",
        time_limit_goodbye="Žao mi je, dostigli smo vremensko ograničenje ovog poziva. Doviđenja.",
        silence_goodbye="Ne čujem ništa, pa ću završiti poziv. Doviđenja.",
        deaf_goodbye="Žao mi je, ne čujem vas dobro. Molim vas, pokušajte nazvati ponovo. Doviđenja.",
        offer="Mogu vam ponuditi {first}{rest}. Koji vam odgovara?",
        offer_last=", ili ",
        offer_with="{when} kod {practitioner}",
        move="Pomjerit ću vašu {treatment} kod {practitioner} {from_} {to}{new_doctor}. Je li to tačno?",
        new_doctor=" kod {practitioner}",
        always_names_new_doctor=False,
        cancel="Otkazat ću vaš termin za {treatment} kod {practitioner} {at}. Je li to tačno?",
        confirm="Upisat ću da dolazite na svoj termin za {treatment} kod {practitioner} {at}. Je li to tačno?",
        when=bs_when,
        treatment=_treatment("bs"),
        practitioner=_doctor("doktora", genitive_a=True),
    ),
}

DEFAULT = "en"


def locale_of(code: str) -> Locale:
    """The locale for a code such as "es" or "es-MX"; English if it is not one of the four."""
    return LOCALES.get(code.strip().lower().split("-")[0], LOCALES[DEFAULT])
