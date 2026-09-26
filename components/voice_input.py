import hashlib

import streamlit as st

from localization import get_text
from utils.voice import VoiceTranscriptionError, transcribe_audio


def render_voice_input(language: str) -> str:
    """Record a message and return its transcript, if one is available."""
    audio = st.audio_input(get_text("record_audio", language), key="mpesa_audio")
    if audio is None:
        return ""

    audio_bytes = audio.getvalue()
    cache_key = "voice_transcript_" + hashlib.sha256(audio_bytes).hexdigest()
    if cache_key in st.session_state:
        return ""

    try:
        transcript = transcribe_audio(audio_bytes, language=f"{language}-KE")
    except ImportError:
        st.warning(get_text("transcription_unavailable", language))
        return ""
    except VoiceTranscriptionError as error:
        st.warning(get_text("transcription_error", language, error=str(error)))
        return ""

    st.session_state[cache_key] = transcript
    return transcript