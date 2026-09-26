import io


class VoiceTranscriptionError(Exception):
    """Raised when recorded speech cannot be understood or reached for recognition."""


def transcribe_audio(audio_bytes: bytes, language: str = "en-KE", recognizer_module=None) -> str:
    """Transcribe recorded audio using Google's speech recognition endpoint."""
    if recognizer_module is None:
        import speech_recognition as recognizer_module

    recognizer = recognizer_module.Recognizer()
    try:
        with recognizer_module.AudioFile(io.BytesIO(audio_bytes)) as source:
            audio = recognizer.record(source)
        return recognizer.recognize_google(audio, language=language)
    except recognizer_module.UnknownValueError as error:
        raise VoiceTranscriptionError("The recording could not be understood.") from error
    except recognizer_module.RequestError as error:
        raise VoiceTranscriptionError("The speech recognition service is unavailable.") from error