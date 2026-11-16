import pytest

from clinic_voice_agent.wer import word_error_rate, words


def test_case_punctuation_and_spacing_do_not_count_as_errors():
    assert word_error_rate("Dr. Okafor, please!", "dr  okafor please") == 0.0
    assert words("It's  Alex’s call.") == ["its", "alexs", "call"]


def test_each_kind_of_mistake_costs_one_word():
    assert word_error_rate("one two three four", "one two three four") == 0.0
    assert word_error_rate("one two three four", "one two three") == 0.25  # a deletion
    assert word_error_rate("one two three four", "one two three four five") == 0.25  # an insertion
    assert word_error_rate("one two three four", "one two tree four") == 0.25  # a substitution


def test_an_accent_is_part_of_the_word():
    # in Spanish and Bosnian a missing accent is a different word, not a typo
    assert word_error_rate("¿Está bien?", "esta bien") == 0.5
    assert word_error_rate("Žao mi je", "Žao mi je") == 0.0
    assert word_error_rate("Žao mi je", "Zao mi je") == pytest.approx(1 / 3)  # one of three words


def test_everything_wrong_can_exceed_one_and_nothing_heard_is_one():
    assert word_error_rate("hello", "this is a long wrong answer") == 6.0  # six edits, one word
    assert word_error_rate("hello there", "") == 1.0


def test_an_empty_reference_scores_zero_only_when_nothing_was_heard():
    assert word_error_rate("", "") == 0.0
    assert word_error_rate("", "noise") == 1.0


@pytest.mark.parametrize(
    "text", ["Gracias por llamar", "Hvala što ste nazvali", "Bedankt voor het bellen"]
)
def test_the_same_text_always_scores_zero_against_itself(text):
    assert word_error_rate(text, text) == 0.0


def test_the_same_bosnian_in_either_script_is_the_same_words():
    # a transcriber may answer in Cyrillic for the same speech; the script is not a mistake
    assert words("Алекс Ривера, рођен 14. марта 1990.") == [
        "aleks",
        "rivera",
        "rođen",
        "14",
        "marta",
        "1990",
    ]
    assert word_error_rate(
        "Alex Rivera, rođen četrnaestog marta", "Алекс Ривера, рођен четрнаестог марта"
    ) == (
        pytest.approx(1 / 5)  # "alex" and "aleks" differ; the rest match
    )
    assert word_error_rate("Žao mi je", "Жао ми је") == 0.0
    assert words("љубав њега џем") == ["ljubav", "njega", "džem"]
