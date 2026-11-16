import pytest

from clinic_voice_agent.choice import chosen_language


@pytest.mark.parametrize(
    ("said", "code"),
    [
        ("español", "es"),
        ("Español, por favor.", "es"),
        ("espanol", "es"),
        ("espanyol", "es"),
        ("Spanish please", "es"),
        ("Nederlands", "nl"),
        ("nederlands alstublieft", "nl"),
        ("Dutch", "nl"),
        ("bosanski", "bs"),
        ("Bosanski, molim.", "bs"),
        ("bosanskom", "bs"),
        ("Bosnian", "bs"),
        ("English", "en"),
        ("english please", "en"),
    ],
)
def test_a_language_asked_for_by_name_is_found_however_it_is_spelt(said, code):
    assert chosen_language(said) == code


@pytest.mark.parametrize(
    "said",
    [
        "Hello?",
        "Alex Rivera.",
        "Both ones keep.",  # what "bosanski" once became on a phone line: not a choice
        "Crystal",
        "My name is Alexander Riviera",
        "I live in Bosnia and speak Dutch and Spanish",  # two languages: not one choice
        "",
    ],
)
def test_anything_else_chooses_nothing(said):
    assert chosen_language(said) is None
