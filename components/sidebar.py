import streamlit as st
from database import get_entity_memory, clear_db
from utils.theme import render_theme_toggle

def render_sidebar(ai_providers: dict, default_provider_label: str):
    """Renders the configuration sidebar and returns the selected AI provider."""
    with st.sidebar:
        render_theme_toggle()
        st.divider()

        st.header("Configuration")

        selected_label = st.selectbox(
            "Active AI Engine",
            list(ai_providers),
            index=list(ai_providers).index(default_provider_label),
        )
        selected_provider = ai_providers[selected_label]
        st.caption("Auto-switches to local rules if AI fails.")

        st.divider()
        st.markdown("### Smart Memory")
        memory_cache = get_entity_memory()
        if memory_cache:
            st.caption("Auto-categorizing recurring entities:")
            for entity, category in list(memory_cache.items())[:5]:
                st.caption(f"• **{entity}** → {category}")
            if len(memory_cache) > 5:
                st.caption(f"...and {len(memory_cache) - 5} more")
        else:
            st.info("No entities learned yet. Process receipts to train your bookkeeper.")

        st.divider()
        if st.button("Wipe Ledger Data", type="secondary", use_container_width=True):
            clear_db()
            st.rerun()

        return selected_label, selected_provider