import pytest

from clinic_voice_agent.prompt_echo import is_echo


@pytest.mark.parametrize(
    "text",
    [
        "Razgovor na bosanskom jeziku.",  # what a real call heard on noise
        "razgovor na bosanskom jeziku latinicom",
        "Datum rođenja, na primjer: dvadeseti juni",
        "The caller chooses a language: English, español, Nederlands or bosanski.",
        "The caller chooses a language",
    ],
)
def test_a_piece_of_the_hint_is_an_echo(text):
    assert is_echo(text)


@pytest.mark.parametrize(
    "text",
    [
        "Bosanski.",
        "Nederlands",
        "Alex Rivera.",
        "14. mart 1990.",
        "Četrnaesti mart hiljadu devetsto devedesete.",
        "Rođen sam četrnaestog marta hiljadu devetsto devedesete.",
        "Da, jezik je u redu.",
        "",
    ],
)
def test_what_a_caller_says_is_not(text):
    assert not is_echo(text)
