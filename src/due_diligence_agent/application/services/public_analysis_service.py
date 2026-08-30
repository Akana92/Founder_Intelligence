from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from langgraph.types import Command

from due_diligence_agent.domain.reports.models import ReportSnapshot


@dataclass(frozen=True)
class ApprovedPublicRun:
    case_id: UUID
    status: str
    report_snapshot_id: UUID
    state: dict[str, Any]


class PublicAnalysisService:
    def __init__(
        self,
        graph: Any,
        *,
        case_repository: Any | None = None,
        evidence_repository: Any | None = None,
        calculation_repository: Any | None = None,
        finding_repository: Any | None = None,
        contradiction_repository: Any | None = None,
        report_service: Any | None = None,
        report_repository: Any | None = None,
    ) -> None:
        self._graph = graph
        self._case_repository = case_repository
        self._evidence_repository = evidence_repository
        self._calculation_repository = calculation_repository
        self._finding_repository = finding_repository
        self._contradiction_repository = contradiction_repository
        self._report_service = report_service
        self._report_repository = report_repository

    def start(self, *, ticker: str, case_id: str, as_of: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"ticker": ticker, "case_id": case_id}
        if as_of is not None:
            payload["as_of"] = as_of
        return cast(
            dict[str, Any],
            self._graph.invoke(
                payload,
                config=_thread_config(case_id),
            ),
        )

    def resume(self, *, case_id: str, decision: dict[str, Any]) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._graph.invoke(Command(resume=decision), config=_thread_config(case_id)),
        )

    def current_state(self, case_id: UUID) -> dict[str, Any]:
        snapshot = self._graph.get_state(config=_thread_config(str(case_id)))
        values = getattr(snapshot, "values", {})
        return dict(values) if isinstance(values, dict) else {}

    def approve_scope(self, case_id: UUID, *, actor: str = "reviewer") -> dict[str, Any]:
        return self.resume(
            case_id=str(case_id),
            decision={"gate": "scope", "approved": True, "actor": actor},
        )

    def resolve_gate3(
        self,
        case_id: UUID,
        *,
        action: str = "leave_unresolved",
        actor: str = "reviewer",
    ) -> dict[str, Any]:
        return self.resume(
            case_id=str(case_id),
            decision={"gate": "gate_3", "action": action, "actor": actor},
        )

    def prepare_report_freeze(self, case_id: UUID) -> dict[str, Any]:
        snapshot = self._build_current_draft(case_id)
        return {
            "status": "awaiting_report_freeze",
            "case_id": str(case_id),
            "report_snapshot_id": str(snapshot.id),
            "data_revision": 1,
        }

    def approve_gate4(
        self, case_id: UUID, *, snapshot_id: UUID, actor: str = "reviewer"
    ) -> dict[str, Any]:
        return self.resume(
            case_id=str(case_id),
            decision={
                "gate": "gate_4",
                "approved": True,
                "snapshot_id": str(snapshot_id),
                "actor": actor,
            },
        )

    def run_with_approvals(self, case_id: UUID, *, approve_all: bool) -> ApprovedPublicRun:
        if not approve_all:
            raise ValueError("manual_rejection_path_not_supported")
        if self._case_repository is None:
            raise RuntimeError("case_repository_required")
        case = self._case_repository.get(case_id)
        state = self.start(
            ticker=case.entity_identifier,
            case_id=str(case.case_id),
            as_of=case.as_of.isoformat(),
        )
        state = self.approve_scope(case_id)
        if state.get("contradiction_ids"):
            state = self.resolve_gate3(case_id)
        prepared = self.prepare_report_freeze(case_id)
        snapshot_id = UUID(str(prepared["report_snapshot_id"]))
        state = self.approve_gate4(case_id, snapshot_id=snapshot_id)
        if state.get("status") != "approved":
            raise RuntimeError(f"fixture_approval_failed:{state.get('status')}")
        return ApprovedPublicRun(
            case_id=case_id,
            status="completed",
            report_snapshot_id=snapshot_id,
            state=state,
        )

    def _build_current_draft(self, case_id: UUID) -> ReportSnapshot:
        if (
            self._case_repository is None
            or self._evidence_repository is None
            or self._calculation_repository is None
            or self._finding_repository is None
            or self._contradiction_repository is None
            or self._report_repository is None
            or self._report_service is None
        ):
            raise RuntimeError("report_dependencies_required")
        report_repository = self._report_repository
        report_service = self._report_service
        existing = report_repository.get_current_draft(case_id)
        if existing is not None:
            return cast(ReportSnapshot, existing)
        case = self._case_repository.get(case_id)
        report_case = _PersistedPublicReportCase(
            case=case,
            facts=tuple(self._evidence_repository.list_for_case(case_id)),
            calculations=tuple(self._calculation_repository.list_for_case(case_id)),
            findings=tuple(self._finding_repository.list_for_case(case_id)),
            contradictions=tuple(self._contradiction_repository.list_for_case(case_id)),
            source_hashes=_source_hashes(report_repository, case_id),
            trace_ids=(f"case-{case_id}",),
        )
        snapshot = cast(ReportSnapshot, report_service.build_public(report_case))
        output_root = getattr(getattr(report_repository, "_db", None), "path", None)
        output_dir = (
            output_root.parent / "reports" / "drafts"
            if output_root is not None
            else Path(".local") / "reports" / "drafts"
        )
        return cast(ReportSnapshot, report_service.render_draft(snapshot, output_dir).snapshot)


@dataclass(frozen=True)
class _PersistedPublicReportCase:
    case: Any
    facts: tuple[Any, ...]
    calculations: tuple[Any, ...]
    findings: tuple[Any, ...]
    contradictions: tuple[Any, ...]
    source_hashes: dict[str, str]
    trace_ids: tuple[str, ...]


def _source_hashes(report_repository: Any, case_id: UUID) -> dict[str, str]:
    db = getattr(report_repository, "_db", None)
    if db is None:
        return {"offline": "sha256:" + "0" * 64}
    rows = db.fetch_all(
        "SELECT payload FROM artifacts WHERE case_id = ? ORDER BY id", (str(case_id),)
    )
    result: dict[str, str] = {}
    for index, row in enumerate(rows, start=1):
        import json

        payload = json.loads(str(row["payload"]))
        source = str(payload.get("source") or f"source-{index}")
        result[f"{source}-{index}"] = "sha256:" + str(payload["content_hash"]).removeprefix(
            "sha256:"
        )
    return result or {"offline": "sha256:" + "0" * 64}


def _thread_config(case_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": case_id}}
