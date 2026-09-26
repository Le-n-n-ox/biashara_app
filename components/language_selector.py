import streamlit as st

from localization import get_text

LANGUAGES = {"English": "en", "Kiswahili": "sw"}


def render_language_selector() -> str:
    """Render the language control and return its selected locale code."""
    selected = st.selectbox(
        get_text("language", st.session_state.get("language", "en")),
        options=list(LANGUAGES),
        index=0 if st.session_state.get("language", "en") == "en" else 1,
        key="language_selector",
    )
    st.session_state["language"] = LANGUAGES[selected]
    return LANGUAGES[selected]