from clinic_voice_agent.hearing import DeafnessWatch


def test_two_missed_stretches_of_real_speech_in_a_row_mean_deaf():
    watch = DeafnessWatch()
    assert watch.speech_without_words(2.0) is False  # one is not enough
    assert watch.speech_without_words(1.5) is True


def test_a_cough_does_not_count_however_often_it_happens():
    watch = DeafnessWatch()
    for _ in range(10):
        assert watch.speech_without_words(0.3) is False


def test_any_real_transcript_starts_the_count_again():
    watch = DeafnessWatch()
    watch.speech_without_words(2.0)
    watch.words_heard()
    assert watch.speech_without_words(2.0) is False  # back to one strike
    assert watch.speech_without_words(2.0) is True


def test_the_threshold_is_a_setting_not_a_number_in_the_logic():
    watch = DeafnessWatch(strikes_to_deaf=3, min_speech=0.5)
    assert [watch.speech_without_words(1.0) for _ in range(3)] == [False, False, True]
