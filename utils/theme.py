import streamlit as st

# Dark-mode overrides for the tokens defined in assets/styles.css :root
_DARK_VARS = """
    --ink: #E9EDF0;
    --ink-soft: #9AA7B0;
    --paper: #14191F;
    --surface: #1B222A;
    --border: #2C343D;
    --green: #3FB97E;
    --green-soft: #16302459;
    --terracotta: #E0725A;
    --terracotta-soft: #3A211D;
    --button-text: #08130E;
    --control-text: #E9EDF0;
    --shadow: 0 1px 3px rgba(0,0,0,.4);
"""


def _ensure_theme_initialized():
    if "theme" not in st.session_state:
        st.session_state.theme = "system"


def apply_theme():
    """Call this AFTER styles.css is loaded, so the override wins the
    cascade. No JS involved — pure Python-side conditional CSS."""
    _ensure_theme_initialized()

    mode = st.session_state.theme

    if mode == "dark":
        css = f":root {{ {_DARK_VARS} }}"
    elif mode == "system":
        css = f"@media (prefers-color-scheme: dark) {{ :root {{ {_DARK_VARS} }} }}"
    else:  # light — styles.css defaults already cover this, nothing to override
        css = ""

    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def render_theme_toggle():
    # Same guard as apply_theme() -- this function must not assume apply_theme()
    # ran first. Previously this read st.session_state.theme directly, which
    # crashed with a KeyError whenever the sidebar rendered before anything
    # had initialized it.
    _ensure_theme_initialized()

    st.markdown("##### Appearance")
    cols = st.columns(3)
    opts = {"system": "System", "light": "Light", "dark": "Dark"}
    for col, key in zip(cols, opts):
        if col.button(opts[key], key=f"theme_{key}", width="stretch",
                       type="primary" if st.session_state.theme == key else "secondary"):
            st.session_state.theme = key
            st.rerun()