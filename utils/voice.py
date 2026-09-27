import io


def transcribe_audio(audio_file, language: str = "en-KE") -> str:
    try:
        import speech_recognition as sr
    except ImportError as error:
        raise RuntimeError("SpeechRecognition is not installed") from error

    if isinstance(audio_file, dict):
        audio_bytes = audio_file.get("bytes", b"")
    elif isinstance(audio_file, bytes):
        audio_bytes = audio_file
    else:
        audio_bytes = audio_file.getvalue()
    if not audio_bytes:
        raise ValueError("The microphone returned an empty recording")

    recognizer = sr.Recognizer()
    with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
        audio = recognizer.record(source)
    transcript = recognizer.recognize_google(audio, language=language).strip()
    if not transcript:
        raise ValueError("The speech service returned an empty transcript")
    return transcript
