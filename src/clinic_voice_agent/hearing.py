"""Noticing that the agent has gone deaf.

Speech to text can stop answering without raising an error: audio keeps going out, no words
come back, and the caller talks into silence. The framework reports it as an event when the
voice detector heard real speech and no transcript followed (`user_transcription_timeout`).

One such event is not enough, and a short one does not count. A cough is speech to the detector
and nothing to the transcriber, and the framework also withholds audio from the transcriber on
purpose at times (while she is speaking and cannot be interrupted). So it takes two in a row,
each from real speech, and any real transcript starts the count again.

Plain logic, tested without audio.
"""


class DeafnessWatch:
    def __init__(self, strikes_to_deaf: int = 2, min_speech: float = 0.8) -> None:
        self.strikes_to_deaf = strikes_to_deaf
        self.min_speech = min_speech  # seconds of speech below which a miss is not counted
        self.strikes = 0

    def words_heard(self) -> None:
        """A non-empty final transcript: the transcriber is alive."""
        self.strikes = 0

    def speech_without_words(self, speech_seconds: float) -> bool:
        """The detector heard `speech_seconds` of speech and no words came. True once deaf."""
        if speech_seconds >= self.min_speech:
            self.strikes += 1
        return self.strikes >= self.strikes_to_deaf
