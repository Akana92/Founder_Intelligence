from __future__ import annotations

from collections.abc import Sequence


def render_evidence_ledger(rows: Sequence[object]) -> None:
    import streamlit as st

    st.subheader("Evidence Ledger")
    if rows:
        st.dataframe(rows, width="stretch")
    else:
        st.caption("No evidence facts collected yet.")
