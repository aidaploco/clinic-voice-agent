from clinic_voice_agent.languages import DEFAULT_LANGUAGE, LANGUAGES, language_for


def test_the_receptionist_speaks_four_languages():
    assert set(LANGUAGES) == {"en", "es", "nl", "bs"}
    assert LANGUAGES["es"].locale == "es-MX"  # Mexican Spanish, not Castilian
    assert [LANGUAGES[c].native_name for c in ("es", "nl", "bs")] == [
        "Español (México)",
        "Nederlands",
        "Bosanski",
    ]


def test_a_language_is_found_from_a_code_or_a_locale():
    assert language_for("es").code == "es"
    assert language_for("es-MX").code == "es"
    assert language_for(" NL ").code == "nl"
    assert language_for("bs-BA").code == "bs"


def test_an_unsupported_language_falls_back_to_english_instead_of_failing():
    assert language_for("fr") is DEFAULT_LANGUAGE
    assert language_for("") is DEFAULT_LANGUAGE
    assert DEFAULT_LANGUAGE.code == "en"
