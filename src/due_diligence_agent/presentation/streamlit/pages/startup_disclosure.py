from __future__ import annotations

from collections.abc import Callable
from typing import Literal, Protocol, cast

from due_diligence_agent.application.services.startup_disclosure_service import (
    StartupDisclosureService,
)
from due_diligence_agent.domain.approvals.startup_disclosure import (
    ClassifiedDisclosureSnapshot,
    DisclosurePreviewSafe,
)


Decision = Literal["approved", "denied", None]


class _ButtonColumn(Protocol):
    def button(self, label: str) -> bool: ...


class _StreamlitLike(Protocol):
    def title(self, body: str) -> None: ...
    def subheader(self, body: str) -> None: ...
    def write(self, value: object) -> None: ...
    def caption(self, body: str) -> None: ...
    def success(self, body: str) -> None: ...
    def text_area(self, label: str, *, max_chars: int) -> str: ...
    def columns(self, spec: int) -> tuple[_ButtonColumn, _ButtonColumn]: ...


def render_startup_disclosure_admin(
    *,
    service: StartupDisclosureService,
    snapshot: ClassifiedDisclosureSnapshot,
    actor: str,
    streamlit_loader: Callable[[], _StreamlitLike] | None = None,
) -> Decision:
    st = streamlit_loader() if streamlit_loader is not None else _load_streamlit()
    preview = service.build_preview(snapshot)

    st.title("Startup Disclosure Approval")
    _render_preview(st, preview)

    comment = st.text_area("Comment", max_chars=240)
    left, right = st.columns(2)
    if left.button("Deny"):
        service.decide(
            snapshot,
            action="denied",
            actor=actor,
            destination=snapshot.destination,
            human_comment=comment,
        )
        st.success("Disclosure denied")
        return "denied"
    if right.button("Approve"):
        service.decide(
            snapshot,
            action="approved",
            actor=actor,
            destination=snapshot.destination,
            human_comment=comment,
        )
        st.success("Disclosure approved")
        return "approved"
    return None


def _render_preview(st: _StreamlitLike, preview: DisclosurePreviewSafe) -> None:
    st.subheader("Safe Preview")
    st.write(
        {
            "artifact_counts": preview.artifact_counts,
            "mime_counts": preview.mime_counts,
            "category_counts": preview.category_counts,
            "fragment_count": preview.fragment_count,
            "detected_classes": [item.value for item in preview.detected_classes],
            "overall_class": preview.overall_class.value,
            "redaction_policy_version": preview.redaction_policy_version,
            "egress_policy_version": preview.egress_policy_version,
            "destination": preview.destination,
            "data_revision": preview.data_revision,
            "content_hash": preview.content_hash,
        }
    )
    st.caption(preview.policy_explanation)


def _load_streamlit() -> _StreamlitLike:
    import streamlit as st

    return cast(_StreamlitLike, st)
