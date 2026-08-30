from __future__ import annotations

STARTUP_MODE_AVAILABLE = False
REGISTERED_WORKFLOWS = {"public_company": "Public Company"}


def main() -> None:
    import streamlit as st

    from due_diligence_agent.presentation.streamlit.pages.admin import render_admin_console
    from due_diligence_agent.presentation.streamlit.pages.public_case import render_public_case

    st.set_page_config(page_title="Investment Due Diligence Admin Console", layout="wide")
    st.sidebar.title("Surfaces")
    surface = st.sidebar.radio("Surface", ["Admin Console", "Public Case"], index=0)
    st.sidebar.info("Admin Console is operator-only. Public Case remains founder-safe.")
    if surface == "Admin Console":
        render_admin_console()
        return
    render_public_case()


if __name__ == "__main__":
    main()
