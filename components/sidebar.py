import streamlit as st
from database import get_entity_memory, clear_db
from utils.theme import render_theme_toggle
from utils.auth import render_logout_button
from localization.translations import tr

def render_sidebar(ai_providers: dict, default_provider_label: str, user_id: int):
    """Renders the configuration sidebar and returns the selected AI provider."""
    with st.sidebar:
        render_logout_button()
        st.markdown("<div class='sidebar-section'>", unsafe_allow_html=True)

        render_theme_toggle()
        st.markdown("</div>", unsafe_allow_html=True)
        st.divider()

        st.header(tr("configuration"))

        selected_label = st.selectbox(
            tr("active_ai"),
            list(ai_providers),
            index=list(ai_providers).index(default_provider_label),
        )
        selected_provider = ai_providers[selected_label]
        st.caption(tr("ai_fallback"))

        st.divider()
        st.markdown(f"### {tr('smart_memory')}")
        memory_cache = get_entity_memory(user_id)
        if memory_cache:
            st.caption(tr("memory_caption"))
            for entity, category in list(memory_cache.items())[:5]:
                st.caption(f"• **{entity}** → {category}")
            if len(memory_cache) > 5:
                st.caption(f"...and {len(memory_cache) - 5} more")
        else:
            st.info(tr("no_memory"))

        st.divider()
        if st.button(tr("wipe_ledger"), type="secondary", width="stretch"):
            clear_db(user_id)
            st.rerun()

        return selected_label, selected_provider