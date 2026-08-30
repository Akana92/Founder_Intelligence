from __future__ import annotations

from collections.abc import Sequence


def render_metrics(rows: Sequence[object]) -> None:
    import streamlit as st

    st.subheader("Metrics")
    if rows:
        st.dataframe(rows, width="stretch")
    else:
        st.caption("Deterministic metrics appear after evidence normalization.")
