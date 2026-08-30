from __future__ import annotations

from collections.abc import Sequence


def render_risk_matrix(rows: Sequence[object]) -> None:
    import streamlit as st

    st.subheader("Risk Matrix")
    if rows:
        st.dataframe(rows, width="stretch")
    else:
        st.caption("No risk findings synthesized yet.")
