from __future__ import annotations

import os
import re
import secrets
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, NamedTuple, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from due_diligence_agent.domain.startup.gtm import StartupGtmSnapshot
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileFieldName,
)
from due_diligence_agent.ports.tracing import AuditEvent
from due_diligence_agent.workflows.startup.runtime import (
    DELETE_RUNTIME_VALUE,
    StartupWorkflowRuntimeStore,
)

FixtureMode = Literal["live", "deterministic_offline"]
ProviderStatus = Literal["deterministic_offline_fixture", "unavailable", "configured"]
AnalysisStatus = Literal[
    "awaiting_upload",
    "awaiting_start",
    "gate2_preview_ready",
    "gate3_review_required",
    "analysis_complete_report_pending",
    "failed",
]
GateStatus = Literal["not_ready", "required", "completed"]
ReportStatus = Literal["not_ready", "pending", "ready"]
FreezeStatus = Literal["not_ready", "required", "approved"]
PdfStatus = Literal["not_ready", "freeze_required", "ready"]

_ALLOWED_PRIVATE_SUFFIXES = {
    ".pdf",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
    ".csv",
    ".xlsx",
    ".txt",
    ".zip",
}
_SAFE_MEDIA_TYPE = re.compile(
    r"[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/[a-z0-9][a-z0-9!#$&^_.+-]{0,63}"
)
_PENDING_UPLOAD_LEASE_TTL_SECONDS = 30.0


class StartupError(RuntimeError):
    status_code = 400

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class StartupNotFound(StartupError):
    status_code = 404


class StartupValidationError(StartupError):
    status_code = 422


class StartupGateConflict(StartupError):
    status_code = 409


class StartupReportRendererUnavailable(StartupError):
    status_code = 503


class StartupAnalysisPort(Protocol):
    def start(self, payload: dict[str, Any], *, thread_id: str) -> dict[str, Any]: ...

    def resume(self, approval: dict[str, Any], *, thread_id: str) -> dict[str, Any]: ...


class StartupCaseResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    case_status: Literal["awaiting_upload"]
    analysis_status: AnalysisStatus
    provider_status: ProviderStatus
    auto_start_triggered: bool


class StartupLangGraphCheckpointResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    checkpoint_hash: str
    checkpoint_id: str
    data_revision: int
    thread_id: str


class StartupStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    case_status: Literal["awaiting_upload"]
    analysis_status: AnalysisStatus
    provider_status: ProviderStatus
    data_revision: int
    active_analysis_thread_id: str
    langgraph_checkpoint: StartupLangGraphCheckpointResponse | None = None
    gate2_status: GateStatus = "not_ready"
    gate3_status: GateStatus = "not_ready"
    gate4_status: GateStatus = "not_ready"
    report_status: ReportStatus = "not_ready"
    snapshot_hash: str | None = None
    snapshot_revision: int | None = None


class StartupUploadResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    accepted_document_ids: list[str]
    analysis_status: AnalysisStatus
    auto_start_triggered: bool
    next_poll_after_ms: int


class StartupGate2PreviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    preview: dict[str, Any]
    resume_token: str
    provider_mode: ProviderStatus


class StartupDecisionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    analysis_status: AnalysisStatus
    gate2_status: GateStatus = "not_ready"
    gate3_status: GateStatus = "not_ready"
    gate4_status: GateStatus = "not_ready"
    report_status: ReportStatus = "not_ready"
    snapshot_hash: str | None = None
    snapshot_revision: int | None = None


class StartupReportResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    report_status: Literal["ready"]
    snapshot_id: str
    snapshot_hash: str
    snapshot_revision: int
    json_url: str
    html_url: str
    pdf_url: str
    freeze_status: FreezeStatus
    pdf_status: PdfStatus


class StartupProfileEvidenceRefResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str
    fragment_id: str | None = None
    artifact_id: str
    artifact_hash: str
    locator_hash: str
    page: int | None = None
    table: str | None = None
    cell: str | None = None
    field_name: str | None = None
    confidence: str


class StartupProfileFieldResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    values: list[str]
    confidence: str
    evidence_refs: list[StartupProfileEvidenceRefResponse]
    dependency_refs: list[str]
    reason_code: str | None = None
    contradiction_ids: list[str]


class StartupProfileParseInventoryResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_hashes: dict[str, str]
    parse_outcomes: dict[str, str]


class StartupProfileResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    profile_id: str
    profile_hash: str
    data_revision: int
    analysis_stage: str
    parent_profile_id: str | None
    fields: dict[str, StartupProfileFieldResponse]
    contradictions: list[str]
    gaps: list[str]
    parse_inventory: StartupProfileParseInventoryResponse


class StartupGtmDimensionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: Literal[
        "audience",
        "geography",
        "channels",
        "offer",
        "market_context",
        "product_proof",
        "adoption_risk",
    ]
    status: Literal["supported", "partial", "missing", "contradicted"]
    evidence_fact_ids: list[str]
    market_source_ids: list[str]
    contradiction_ids: list[str]
    reason_code: str
    gap_code: str | None


class StartupGtmLaunchPhaseResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    horizon: Literal["day_7", "day_30", "day_60", "day_90"]
    experiment_codes: list[str]


class StartupGtmResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    schema_version: Literal["startup_gtm@1"]
    snapshot_id: str
    snapshot_hash: str
    snapshot_revision: int
    status: Literal["supported", "partial", "insufficient", "contradicted"]
    profile_id: str
    product_validation_snapshot_id: str
    market_research_snapshot_id: str
    dimensions: list[StartupGtmDimensionResponse]
    launch_plan: list[StartupGtmLaunchPhaseResponse]
    finding_ids: list[str]
    built_at: datetime


class CanonicalReportSnapshot(NamedTuple):
    snapshot_id: str
    snapshot_hash: str
    snapshot_revision: int


class _IncomingDocument(NamedTuple):
    content: bytes
    content_sha256: str
    suffix: str
    declared_mime_type: str | None
    source_name_sha256: str


class StartupReportPort(Protocol):
    def current_snapshot(self, case_id: str) -> CanonicalReportSnapshot: ...

    def canonical_json_bytes(self, case_id: str) -> bytes: ...

    def founder_json_bytes(self, case_id: str) -> bytes: ...

    def html(self, case_id: str) -> str: ...

    def pdf(self, case_id: str) -> bytes: ...

    def decide_gate4(
        self,
        case_id: str,
        *,
        decision: Literal["approved", "rejected"],
        snapshot_hash: str,
        snapshot_revision: int,
        reason: str | None = None,
    ) -> CanonicalReportSnapshot: ...

    def freeze_status(self, case_id: str) -> FreezeStatus: ...

    def pdf_status(self, case_id: str) -> PdfStatus: ...


class StartupProfileQueryPort(Protocol):
    def get_current(self, case_id: UUID) -> StartupProfile: ...

    def get(self, profile_id: UUID) -> StartupProfile: ...


class StartupGtmQueryPort(Protocol):
    def get_current(self, case_id: str) -> StartupGtmSnapshot: ...


class CanonicalStartupCaseRevisionPort(Protocol):
    def current_revision(self, case_id: str) -> int: ...

    def advance_revision(
        self,
        case_id: str,
        *,
        expected_current_revision: int,
        document_ids: list[str],
        source_refs: list[dict[str, str]],
        metadata: dict[str, str],
    ) -> int: ...


class StartupAuditSpool(Protocol):
    def append(self, event: AuditEvent) -> str: ...


class StartupCaseCoordinator:
    def __init__(
        self,
        *,
        analysis_service: StartupAnalysisPort,
        deterministic_analysis_service: StartupAnalysisPort | None = None,
        workflow_store: StartupWorkflowRuntimeStore,
        inbox_root: Path,
        report_port: StartupReportPort | None = None,
        deterministic_report_port: StartupReportPort | None = None,
        profile_port: StartupProfileQueryPort | None = None,
        deterministic_profile_port: StartupProfileQueryPort | None = None,
        gtm_port: StartupGtmQueryPort | None = None,
        deterministic_gtm_port: StartupGtmQueryPort | None = None,
        case_revision_port: CanonicalStartupCaseRevisionPort | None = None,
        deterministic_case_revision_port: CanonicalStartupCaseRevisionPort | None = None,
        audit_spool: StartupAuditSpool | None = None,
        deterministic_audit_spool: StartupAuditSpool | None = None,
        live_provider_configured: bool = False,
    ) -> None:
        self._analysis_service = analysis_service
        self._deterministic_analysis_service = deterministic_analysis_service
        self._workflow_store = workflow_store
        self._inbox_root = inbox_root
        self._report_port = report_port
        self._deterministic_report_port = deterministic_report_port
        self._profile_port = profile_port
        self._deterministic_profile_port = deterministic_profile_port
        self._gtm_port = gtm_port
        self._deterministic_gtm_port = deterministic_gtm_port
        self._case_revision_port = case_revision_port
        self._deterministic_case_revision_port = deterministic_case_revision_port
        self._audit_spool = audit_spool
        self._deterministic_audit_spool = deterministic_audit_spool
        self._live_provider_configured = live_provider_configured

    def create_case(self, request: dict[str, Any]) -> StartupCaseResponse:
        fixture_mode = _fixture_mode(request.get("fixture_mode"))
        case_id = str(uuid4())
        values = {
            "case_exists": True,
            "case_status": "awaiting_upload",
            "analysis_status": "awaiting_upload",
            "fixture_mode": fixture_mode,
            "provider_status": self._provider_status(fixture_mode),
            "company_name": _optional_text(request.get("company_name")),
            "website": _optional_text(request.get("website")),
            "as_of": _optional_text(request.get("as_of")),
            "document_class_hint": _optional_text(request.get("document_class_hint")),
            "document_ids": [],
            "documents": [],
            "gate2_status": "not_ready",
            "gate3_status": "not_ready",
            "gate4_status": "not_ready",
            "report_status": "not_ready",
            "canonical_report_snapshot_id": None,
            "canonical_report_snapshot_hash": None,
            "canonical_report_snapshot_revision": None,
        }
        self._workflow_store.save(case_id, values)
        return StartupCaseResponse(
            case_id=case_id,
            case_status="awaiting_upload",
            analysis_status="awaiting_upload",
            provider_status=self._provider_status(fixture_mode),
            auto_start_triggered=False,
        )

    def get_status(self, case_id: str) -> StartupStatusResponse:
        runtime = self._load_existing(case_id)
        return self._status_response(case_id, runtime)

    def get_analysis(self, case_id: str) -> StartupStatusResponse:
        return self.get_status(case_id)

    def upload_documents(
        self,
        case_id: str,
        *,
        files: list[dict[str, Any]],
        auto_start: bool,
        metadata: dict[str, Any] | None = None,
    ) -> StartupUploadResponse:
        non_empty = [item for item in files if bytes(item.get("content") or b"")]
        if not non_empty:
            raise StartupValidationError("empty_upload")
        prepared = [
            _IncomingDocument(
                content=bytes(file.get("content") or b""),
                content_sha256=sha256(bytes(file.get("content") or b"")).hexdigest(),
                suffix=_canonical_private_suffix(file.get("filename")),
                declared_mime_type=_safe_declared_mime_type(file.get("content_type")),
                source_name_sha256=_source_name_sha256(file.get("filename")),
            )
            for file in non_empty
        ]
        case_dir = self._inbox_root / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        accepted_ids: list[str] = []
        pending_files: list[tuple[str, str, str, bytes]] = []
        start_payload: dict[str, Any] | None = None
        start_thread_id: str | None = None
        start_revision: int | None = None
        upload_metadata = _sanitize_metadata(metadata or {})
        pending_deadline = time.monotonic() + 5.0

        while True:
            accepted_ids = []
            pending_files = []
            stale_pending_files: list[tuple[str, str, str]] = []
            wait_for_pending_upload = False

            def reserve_pending_upload(runtime: dict[str, Any]) -> dict[str, Any]:
                nonlocal accepted_ids, pending_files, stale_pending_files, wait_for_pending_upload
                if not runtime.get("case_exists"):
                    return {}
                documents = _runtime_documents(runtime)
                document_ids = [str(item) for item in runtime.get("document_ids", [])]
                pending_uploads = _pending_document_uploads(runtime)
                content_to_document_id = {
                    str(item["content_sha256"]): str(item["document_id"])
                    for item in documents
                    if isinstance(item.get("content_sha256"), str)
                    and isinstance(item.get("document_id"), str)
                }
                accepted_ids = []
                for incoming in prepared:
                    existing_id = content_to_document_id.get(incoming.content_sha256)
                    if existing_id is not None:
                        accepted_ids.append(existing_id)
                        continue
                    pending_record = pending_uploads.get(incoming.content_sha256)
                    if pending_record is not None:
                        if _pending_upload_is_stale(pending_record):
                            stale_pending_files.append(  # noqa: B023
                                _pending_file_identity(incoming.content_sha256, pending_record)
                            )
                            continue
                        pending_document = _pending_record_document(pending_record)
                        accepted_ids.append(str(pending_document["document_id"]))
                        wait_for_pending_upload = True
                        continue
                    document_id = _next_document_id(document_ids, pending_uploads)
                    private_name = f"{document_id}{incoming.suffix}"
                    lease_id = uuid4().hex
                    document = {
                        "document_id": document_id,
                        "private_name": private_name,
                        "declared_mime_type": incoming.declared_mime_type,
                        "byte_size": len(incoming.content),
                        "source_name_sha256": incoming.source_name_sha256,
                        "content_sha256": incoming.content_sha256,
                    }
                    pending_uploads[incoming.content_sha256] = {
                        "lease_id": lease_id,
                        "created_at": time.time(),
                        "document": document,
                    }
                    pending_files.append(  # noqa: B023
                        (incoming.content_sha256, lease_id, private_name, incoming.content)
                    )
                    accepted_ids.append(document_id)
                values: dict[str, Any] = {}
                if pending_files:  # noqa: B023
                    values["pending_document_uploads"] = pending_uploads
                return values

            reserved = self._workflow_store.update(case_id, reserve_pending_upload)
            if not reserved.get("case_exists"):
                raise StartupNotFound("case_not_found")
            if stale_pending_files:
                _recover_stale_pending_files(case_dir, stale_pending_files)
                self._workflow_store.update(
                    case_id,
                    lambda runtime: _release_stale_pending_uploads(
                        runtime, stale_pending_files  # noqa: B023
                    ),
                )
                continue
            if pending_files:
                try:
                    _write_and_verify_pending_files(case_dir, pending_files)
                except Exception:
                    self._workflow_store.update(
                        case_id,
                        lambda runtime: _release_pending_uploads(
                            runtime, pending_files  # noqa: B023
                        ),
                    )
                    raise
                break
            if not wait_for_pending_upload:
                break
            if time.monotonic() >= pending_deadline:
                raise StartupGateConflict("document_upload_pending")
            _wait_for_pending_upload_retry()

        if pending_files:
            def publish_upload(runtime: dict[str, Any]) -> dict[str, Any]:
                nonlocal start_payload, start_thread_id, start_revision
                if not runtime.get("case_exists"):
                    return {}
                documents = _runtime_documents(runtime)
                document_ids = [str(item) for item in runtime.get("document_ids", [])]
                pending_uploads = _pending_document_uploads(runtime)
                published_new_document = False
                for content_hash, lease_id, _private_name, _content in pending_files:
                    pending_record = pending_uploads.get(content_hash)
                    if pending_record is None or pending_record.get("lease_id") != lease_id:
                        continue
                    document = _pending_record_document(pending_record)
                    documents.append(document)
                    pending_uploads.pop(content_hash, None)
                    published_new_document = True
                documents = _sort_runtime_documents(documents)
                document_ids = [
                    str(item["document_id"])
                    for item in documents
                    if isinstance(item.get("document_id"), str)
                ]
                values: dict[str, Any] = {
                    "documents": documents,
                    "document_ids": document_ids,
                    "pending_document_uploads": (
                        pending_uploads if pending_uploads else DELETE_RUNTIME_VALUE
                    ),
                }
                if not published_new_document:
                    return values
                source_refs = _source_refs(documents)
                revision_port = self._case_revision_port_for(runtime)
                if revision_port is None:
                    requested_revision = _current_data_revision(runtime)
                    requested_revision = 1 if requested_revision == 0 else requested_revision + 1
                else:
                    requested_revision = _advance_case_revision(
                        revision_port,
                        case_id,
                        runtime=runtime,
                        document_ids=document_ids,
                        source_refs=source_refs,
                        metadata=upload_metadata,
                    )
                active_thread_id = _analysis_thread_id(case_id, requested_revision)
                values.update(_revision_invalidation_values(requested_revision, active_thread_id))
                values.update(
                    {
                        "source_document_ids": list(document_ids),
                        "source_refs": source_refs,
                        "source_refs_revision": requested_revision,
                        "source_ref_resolution_status": "resolved",
                    }
                )
                if upload_metadata:
                    values["upload_metadata"] = upload_metadata
                start_payload = None
                start_thread_id = None
                start_revision = None
                if auto_start:
                    provider_mode = _provider_mode(runtime)
                    values.update(
                        {
                            "analysis_start_claim_thread_id": active_thread_id,
                            "analysis_start_claim_data_revision": requested_revision,
                        }
                    )
                    start_payload = _start_payload(
                        case_id,
                        document_ids=document_ids,
                        source_refs=source_refs,
                        data_revision=requested_revision,
                        fixture_mode=runtime.get("fixture_mode"),
                        execution_mode=provider_mode,
                    )
                    start_thread_id = active_thread_id
                    start_revision = requested_revision
                return values

            reserved = self._workflow_store.update(case_id, publish_upload)
        else:
            def claim_existing_start(runtime: dict[str, Any]) -> dict[str, Any]:
                nonlocal start_payload, start_thread_id, start_revision, accepted_ids
                start_payload = None
                start_thread_id = None
                start_revision = None
                if not runtime.get("case_exists"):
                    return {}
                documents = _runtime_documents(runtime)
                documents = _sort_runtime_documents(documents)
                document_ids = [str(item) for item in runtime.get("document_ids", [])]
                document_ids = [
                    str(item["document_id"])
                    for item in documents
                    if isinstance(item.get("document_id"), str)
                ]
                content_to_document_id = {
                    str(item["content_sha256"]): str(item["document_id"])
                    for item in documents
                    if isinstance(item.get("content_sha256"), str)
                    and isinstance(item.get("document_id"), str)
                }
                accepted_ids = [
                    content_to_document_id[incoming.content_sha256] for incoming in prepared
                ]
                current_revision = _current_data_revision(runtime)
                revision_port = self._case_revision_port_for(runtime)
                if revision_port is None:
                    active_thread_id = _active_analysis_thread_id(case_id, runtime)
                else:
                    current_revision = _reconcile_case_revision(
                        revision_port,
                        case_id,
                        runtime=runtime,
                    )
                    active_thread_id = _analysis_thread_id(case_id, current_revision)
                source_refs = _source_refs(documents)
                values: dict[str, Any] = {
                    "data_revision": current_revision,
                    "active_analysis_thread_id": active_thread_id,
                    "source_document_ids": list(document_ids),
                    "source_refs": source_refs,
                    "source_refs_revision": current_revision,
                    "source_ref_resolution_status": "resolved",
                }
                if upload_metadata:
                    values["upload_metadata"] = upload_metadata
                claimed_thread_id = runtime.get("analysis_start_claim_thread_id")
                can_claim_start = (
                    auto_start
                    and current_revision >= 1
                    and _analysis_status(runtime.get("analysis_status")) == "awaiting_start"
                    and claimed_thread_id != active_thread_id
                )
                if can_claim_start:
                    provider_mode = _provider_mode(runtime)
                    values.update(
                        {
                            "analysis_start_claim_thread_id": active_thread_id,
                            "analysis_start_claim_data_revision": current_revision,
                        }
                    )
                    start_payload = _start_payload(
                        case_id,
                        document_ids=document_ids,
                        source_refs=source_refs,
                        data_revision=current_revision,
                        fixture_mode=runtime.get("fixture_mode"),
                        execution_mode=provider_mode,
                    )
                    start_thread_id = active_thread_id
                    start_revision = current_revision
                return values

            reserved = self._workflow_store.update(case_id, claim_existing_start)
            if not reserved.get("case_exists"):
                raise StartupNotFound("case_not_found")

        auto_start_triggered = False
        if start_payload is not None and start_thread_id is not None and start_revision is not None:
            service = self._analysis_service_for(str(reserved.get("fixture_mode") or "live"))
            try:
                result = service.start(start_payload, thread_id=start_thread_id)
            except Exception:
                self._workflow_store.update(
                    case_id,
                    lambda runtime: _release_start_claim(
                        runtime,
                        thread_id=start_thread_id,
                        data_revision=start_revision,
                    ),
                )
                raise

            projection_applied = False

            def project_start(current: dict[str, Any]) -> dict[str, Any]:
                nonlocal projection_applied
                if (
                    _current_data_revision(current) != start_revision
                    or current.get("active_analysis_thread_id") != start_thread_id
                ):
                    return {}
                projection_applied = True
                return self._project_graph_result(result, runtime=current)

            projected = self._workflow_store.update(case_id, project_start)
            if (
                projection_applied
                and result.get("status") == "failed"
                and projected.get("analysis_status") == "failed"
            ):
                raise StartupGateConflict(_workflow_failure_code(result))
            auto_start_triggered = projection_applied
        updated = self._load_existing(case_id)
        return StartupUploadResponse(
            case_id=case_id,
            accepted_document_ids=accepted_ids,
            analysis_status=_analysis_status(updated.get("analysis_status")),
            auto_start_triggered=auto_start_triggered,
            next_poll_after_ms=0,
        )

    def reanalyze_existing_documents(
        self,
        case_id: str,
        *,
        document_ids: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> StartupStatusResponse:
        """Advance the case revision and restart analysis from existing private documents."""

        selected_ids = [str(item) for item in document_ids if str(item)]
        if not selected_ids or len(selected_ids) != len(set(selected_ids)):
            raise StartupValidationError("document_selection_invalid")
        start_payload: dict[str, Any] | None = None
        start_thread_id: str | None = None
        start_revision: int | None = None
        reanalysis_metadata = _sanitize_metadata(metadata or {})

        def claim_reanalysis(runtime: dict[str, Any]) -> dict[str, Any]:
            nonlocal start_payload, start_thread_id, start_revision
            if not runtime.get("case_exists"):
                return {}
            documents = _sort_runtime_documents(_runtime_documents(runtime))
            canonical_document_ids = [
                str(item["document_id"])
                for item in documents
                if isinstance(item.get("document_id"), str)
            ]
            if not set(selected_ids).issubset(canonical_document_ids):
                raise StartupGateConflict("document_not_in_case")
            source_refs = _source_refs(documents)
            revision_port = self._case_revision_port_for(runtime)
            if revision_port is None:
                current_revision = _current_data_revision(runtime)
                if current_revision < 1:
                    raise StartupGateConflict("case_revision_conflict")
                requested_revision = current_revision + 1
            else:
                requested_revision = _advance_case_revision(
                    revision_port,
                    case_id,
                    runtime=runtime,
                    document_ids=canonical_document_ids,
                    source_refs=source_refs,
                    metadata=reanalysis_metadata,
                )
            active_thread_id = _analysis_thread_id(case_id, requested_revision)
            values = _revision_invalidation_values(requested_revision, active_thread_id)
            values.update(
                {
                    "source_document_ids": list(canonical_document_ids),
                    "source_refs": source_refs,
                    "source_refs_revision": requested_revision,
                    "source_ref_resolution_status": "resolved",
                    "analysis_start_claim_thread_id": active_thread_id,
                    "analysis_start_claim_data_revision": requested_revision,
                }
            )
            provider_mode = _provider_mode(runtime)
            start_payload = _start_payload(
                case_id,
                document_ids=canonical_document_ids,
                source_refs=source_refs,
                data_revision=requested_revision,
                fixture_mode=runtime.get("fixture_mode"),
                execution_mode=provider_mode,
            )
            start_thread_id = active_thread_id
            start_revision = requested_revision
            return values

        reserved = self._workflow_store.update(case_id, claim_reanalysis)
        if not reserved.get("case_exists"):
            raise StartupNotFound("case_not_found")
        if start_payload is None or start_thread_id is None or start_revision is None:
            raise StartupGateConflict("analysis_restart_not_claimed")

        service = self._analysis_service_for(str(reserved.get("fixture_mode") or "live"))
        try:
            result = service.start(start_payload, thread_id=start_thread_id)
        except Exception:
            self._workflow_store.update(
                case_id,
                lambda runtime: _release_start_claim(
                    runtime,
                    thread_id=start_thread_id,
                    data_revision=start_revision,
                ),
            )
            raise

        projection_applied = False

        def project_start(current: dict[str, Any]) -> dict[str, Any]:
            nonlocal projection_applied
            if (
                _current_data_revision(current) != start_revision
                or current.get("active_analysis_thread_id") != start_thread_id
            ):
                return {}
            projection_applied = True
            return self._project_graph_result(result, runtime=current)

        projected = self._workflow_store.update(case_id, project_start)
        if (
            projection_applied
            and result.get("status") == "failed"
            and projected.get("analysis_status") == "failed"
        ):
            raise StartupGateConflict(_workflow_failure_code(result))
        return self._status_response(case_id, self._load_existing(case_id))

    def seed_revision_analysis(self, payload: dict[str, Any], *, thread_id: str) -> None:
        case_id = payload.get("case_id")
        data_revision = payload.get("data_revision")
        if not isinstance(case_id, str) or not case_id or type(data_revision) is not int:
            raise StartupGateConflict("analysis_revision_seed_payload_invalid")
        runtime = self._load_existing(case_id)
        canonical_payload = _analysis_revision_seed_payload(case_id, runtime)
        if (
            canonical_payload is None
            or payload != canonical_payload
            or thread_id != _analysis_thread_id(case_id, data_revision)
            or not _analysis_revision_seed_runtime_matches(
                runtime,
                thread_id=thread_id,
                data_revision=data_revision,
            )
        ):
            raise StartupGateConflict("analysis_revision_seed_payload_invalid")

        service = self._analysis_service_for(str(runtime.get("fixture_mode") or "live"))
        requires_checkpoint = bool(
            getattr(service, "checkpoint_identity_required_for_resume", False)
        )
        if self._current_langgraph_checkpoint(case_id, runtime) is not None:
            self._workflow_store.update(
                case_id,
                lambda current: _complete_analysis_revision_seed_without_claim(
                    current,
                    thread_id=thread_id,
                    data_revision=data_revision,
                ),
            )
            return

        claim_id = uuid4().hex
        claimed = False

        def claim_seed(current: dict[str, Any]) -> dict[str, Any]:
            nonlocal claimed
            if not _analysis_revision_seed_runtime_matches(
                current,
                thread_id=thread_id,
                data_revision=data_revision,
            ):
                raise StartupGateConflict("analysis_revision_seed_payload_invalid")
            seed_status = current.get("analysis_revision_seed_status")
            if seed_status == "starting":
                raise StartupGateConflict("analysis_revision_seed_in_progress")
            if seed_status == "seeded" and not requires_checkpoint:
                return {}
            claimed = True
            return {
                "analysis_revision_seed_required": True,
                "analysis_revision_seed_status": "starting",
                "analysis_revision_seed_claim_id": claim_id,
                "analysis_start_claim_thread_id": thread_id,
                "analysis_start_claim_data_revision": data_revision,
                "error_code": DELETE_RUNTIME_VALUE,
            }

        reserved = self._workflow_store.update(case_id, claim_seed)
        if not claimed:
            return

        try:
            result = service.start(canonical_payload, thread_id=thread_id)
            if (
                result.get("status") != "approval_required"
                or result.get("pending_gate") != "startup_disclosure"
            ):
                raise RuntimeError("analysis_revision_seed_unexpected_result")
            if requires_checkpoint and self._current_langgraph_checkpoint(case_id, reserved) is None:
                raise RuntimeError("analysis_revision_seed_checkpoint_missing")
        except Exception:  # noqa: BLE001 - fail closed without exposing provider payloads.
            self._workflow_store.update(
                case_id,
                lambda current: _fail_analysis_revision_seed(
                    current,
                    claim_id=claim_id,
                    thread_id=thread_id,
                    data_revision=data_revision,
                ),
            )
            raise StartupGateConflict("analysis_revision_seed_failed") from None

        projected = self._project_graph_result(result, runtime=runtime)
        projection_applied = False

        def complete_seed(current: dict[str, Any]) -> dict[str, Any]:
            nonlocal projection_applied
            if (
                current.get("analysis_revision_seed_claim_id") != claim_id
                or not _analysis_revision_seed_runtime_matches(
                    current,
                    thread_id=thread_id,
                    data_revision=data_revision,
                )
            ):
                return {}
            projection_applied = True
            return {
                **projected,
                "analysis_revision_seed_required": True,
                "analysis_revision_seed_status": "seeded",
                "analysis_revision_seed_claim_id": DELETE_RUNTIME_VALUE,
            }

        self._workflow_store.update(case_id, complete_seed)
        if not projection_applied:
            raise StartupGateConflict("analysis_revision_seed_stale")

    def get_gate2_preview(self, case_id: str) -> StartupGate2PreviewResponse:
        runtime = self._load_existing(case_id)
        if runtime.get("analysis_status") != "gate2_preview_ready":
            raise StartupNotFound("gate2_preview_not_ready")
        if runtime.get("analysis_revision_seed_required"):
            if runtime.get("analysis_revision_seed_status") != "seeded":
                raise StartupGateConflict("analysis_checkpoint_not_ready")
            service = self._analysis_service_for(str(runtime.get("fixture_mode") or "live"))
            if (
                getattr(service, "checkpoint_identity_required_for_resume", False)
                and self._current_langgraph_checkpoint(case_id, runtime) is None
            ):
                raise StartupGateConflict("analysis_checkpoint_not_ready")
        token = secrets.token_urlsafe(32)
        self._workflow_store.save(
            case_id,
            {
                "gate2_resume_token_digest": _token_digest(case_id, "gate2", token),
                "gate2_resume_token_used": False,
            },
        )
        preview = runtime.get("gate2_preview")
        if not isinstance(preview, dict):
            preview = {"evidence_fact_ids": list(runtime.get("evidence_fact_ids", []))}
        return StartupGate2PreviewResponse(
            case_id=case_id,
            preview=preview,
            resume_token=token,
            provider_mode=_provider_mode(runtime),
        )

    def decide_gate2(self, case_id: str, request: dict[str, Any]) -> StartupDecisionResponse:
        runtime = self._load_existing(case_id)
        decision = str(request.get("decision") or "")
        if decision not in {"approved", "denied"}:
            raise StartupValidationError("invalid_gate2_decision")
        if (
            runtime.get("analysis_revision_seed_required")
            and runtime.get("analysis_revision_seed_status") != "seeded"
        ):
            raise StartupGateConflict("analysis_checkpoint_not_ready")
        token = str(request.get("resume_token") or "")
        if not self._workflow_store.consume_resume_token(
            case_id,
            gate="gate2",
            expected_digest=_token_digest(case_id, "gate2", token),
        ):
            raise StartupGateConflict("resume_token_invalid")
        reason = _sanitize_reason(request.get("reason"))
        if reason is not None:
            self._workflow_store.save(case_id, {"gate2_decision_reason": reason})
        service = self._analysis_service_for(str(runtime.get("fixture_mode") or "live"))
        try:
            result = service.resume(
                {"action": decision},
                thread_id=_active_analysis_thread_id(case_id, runtime),
            )
        except Exception:  # noqa: BLE001 - workflow adapters can fail with provider-specific exceptions.
            self._workflow_store.save(
                case_id,
                {
                    "analysis_status": "failed",
                    "gate2_status": "required",
                    "error_code": "gate2_resume_failed",
                },
            )
            raise StartupGateConflict("gate2_resume_failed") from None
        values = self._project_graph_result(result, runtime=runtime)
        if result.get("status") == "failed" and values.get("analysis_status") == "failed":
            values["gate2_status"] = "required"
            self._workflow_store.save(case_id, values)
            raise StartupGateConflict(_workflow_failure_code(result))
        values.update(
            {
                "gate2_status": "completed",
            }
        )
        self._workflow_store.save(case_id, values)
        return self._decision_response(case_id, self._load_existing(case_id))

    def decide_gate3(self, case_id: str, request: dict[str, Any]) -> StartupDecisionResponse:
        runtime = self._load_existing(case_id)
        if request.get("decision") != "continue":
            raise StartupValidationError("invalid_gate3_decision")
        allowed = {str(item) for item in runtime.get("evidence_fact_ids", [])}
        raw_exclusions = request.get("exclusions", [])
        if not isinstance(raw_exclusions, list):
            raise StartupValidationError("invalid_gate3_exclusions")
        exclusions: list[str] = []
        reasons: dict[str, str] = {}
        for item in raw_exclusions:
            if not isinstance(item, dict):
                raise StartupValidationError("invalid_gate3_exclusions")
            evidence_fact_id = str(item.get("evidence_fact_id") or "")
            exclusions.append(evidence_fact_id)
            reason = _sanitize_reason(item.get("reason"))
            if reason is not None:
                reasons[evidence_fact_id] = reason
        if any(item not in allowed for item in exclusions):
            raise StartupValidationError("unknown_evidence_fact_id")
        approval = {
            "gate": "startup_gate3_review",
            "action": "continue",
            "exclusions": [{"evidence_fact_id": item} for item in exclusions],
        }
        service = self._analysis_service_for(str(runtime.get("fixture_mode") or "live"))
        result = service.resume(approval, thread_id=_active_analysis_thread_id(case_id, runtime))
        values = self._project_graph_result(result, runtime=runtime)
        values["gate3_status"] = "completed"
        if reasons:
            values["gate3_exclusion_reasons"] = reasons
        if (
            values.get("analysis_status") == "analysis_complete_report_pending"
            and not _has_canonical_report_tuple({**runtime, **values})
        ):
            values["report_status"] = "not_ready"
        self._workflow_store.save(case_id, values)
        return self._decision_response(case_id, self._load_existing(case_id))

    def decide_gate4(self, case_id: str, _request: dict[str, Any]) -> StartupDecisionResponse:
        runtime = self._load_existing(case_id)
        port = self._report_port_for(runtime)
        if port is None:
            _canonical_report_snapshot(runtime)
            raise StartupGateConflict("gate_4_freeze_required")
        decision = str(_request.get("decision") or "")
        if decision not in {"approved", "rejected"}:
            raise StartupValidationError("invalid_gate4_decision")
        snapshot_hash = str(_request.get("snapshot_hash") or "")
        snapshot_revision = _request.get("snapshot_revision")
        if type(snapshot_revision) is not int:
            raise StartupGateConflict("gate_4_snapshot_mismatch")
        if runtime.get("last_pending_gate") == "startup_gate4_freeze":
            try:
                current = port.current_snapshot(case_id)
            except (KeyError, LookupError):
                raise StartupNotFound("report_not_ready") from None
            if (
                current.snapshot_hash != snapshot_hash
                or current.snapshot_revision != snapshot_revision
            ):
                raise StartupGateConflict("gate_4_snapshot_mismatch")
            service = self._analysis_service_for(str(runtime.get("fixture_mode") or "live"))
            result = service.resume(
                {
                    "action": decision,
                    "actor": "founder",
                    "report_snapshot_id": current.snapshot_id,
                    "report_snapshot_hash": current.snapshot_hash,
                    "report_snapshot_revision": current.snapshot_revision,
                    "reason": _sanitize_reason(_request.get("reason")),
                },
                thread_id=_active_analysis_thread_id(case_id, runtime),
            )
            if result.get("status") == "failed":
                code = str(result.get("error_code") or "gate_4_resume_failed")
                if code in {"gate_4_snapshot_mismatch", "invalid_gate4_decision"}:
                    raise StartupGateConflict("gate_4_snapshot_mismatch") from None
                raise StartupGateConflict("gate_4_resume_failed") from None
            values = self._project_graph_result(result, runtime=runtime)
            values.update(
                {
                    "gate4_status": "completed",
                    "report_status": "ready",
                    "gate4_last_decision": decision,
                }
            )
            self._workflow_store.save(case_id, values)
            self._save_report_tuple(
                case_id,
                current,
                {
                    "gate4_status": "completed",
                    "report_status": "ready",
                    "gate4_last_decision": decision,
                },
                event_type="startup_report.gate4_completed",
                event_status="completed",
                decision=decision,
            )
            return self._decision_response(case_id, self._load_existing(case_id))
        try:
            snapshot = port.decide_gate4(
                case_id,
                decision="approved" if decision == "approved" else "rejected",
                snapshot_hash=snapshot_hash,
                snapshot_revision=snapshot_revision,
                reason=_sanitize_reason(_request.get("reason")),
            )
        except (KeyError, LookupError):
            raise StartupNotFound("report_not_ready") from None
        except StartupError:
            raise
        except ValueError as exc:
            code = str(exc) or "gate_4_snapshot_mismatch"
            if code == "report_not_ready":
                raise StartupNotFound("report_not_ready") from None
            if code == "invalid_gate4_decision":
                raise StartupValidationError(code) from None
            raise StartupGateConflict("gate_4_snapshot_mismatch") from None
        self._save_report_tuple(
            case_id,
            snapshot,
            {
                "gate4_status": "completed",
                "report_status": "ready",
                "gate4_last_decision": decision,
            },
            event_type="startup_report.gate4_completed",
            event_status="completed",
            decision=decision,
        )
        return self._decision_response(case_id, self._load_existing(case_id))

    def get_report(self, case_id: str) -> StartupReportResponse:
        runtime = self._load_existing(case_id)
        port = self._report_port_for(runtime)
        if port is not None:
            snapshot = self._current_report_snapshot(case_id, port)
            self._save_report_tuple(
                case_id,
                snapshot,
                {"report_status": "ready"},
                event_type="startup_report.canonical_snapshot",
                event_status="success",
            )
            freeze_status = _freeze_status(port.freeze_status(case_id))
            pdf_status = _pdf_status(port.pdf_status(case_id))
        else:
            snapshot = _canonical_report_snapshot(runtime)
            freeze_status = "required"
            pdf_status = "freeze_required"
        return StartupReportResponse(
            case_id=case_id,
            report_status="ready",
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.snapshot_hash,
            snapshot_revision=snapshot.snapshot_revision,
            json_url=f"/api/v1/startup/cases/{case_id}/report/json",
            html_url=f"/api/v1/startup/cases/{case_id}/report/html",
            pdf_url=f"/api/v1/startup/cases/{case_id}/report/pdf",
            freeze_status=freeze_status,
            pdf_status=pdf_status,
        )

    def get_report_json(self, case_id: str) -> bytes:
        runtime = self._load_existing(case_id)
        port = self._report_port_for(runtime)
        if port is None:
            raise StartupNotFound("report_not_ready")
        snapshot = self._current_report_snapshot(case_id, port)
        self._save_report_tuple(
            case_id,
            snapshot,
            {"report_status": "ready"},
            event_type="startup_report.canonical_snapshot",
            event_status="success",
        )
        try:
            return port.founder_json_bytes(case_id)
        except (KeyError, LookupError):
            raise StartupNotFound("report_not_ready") from None

    def get_report_html(self, case_id: str) -> str:
        runtime = self._load_existing(case_id)
        port = self._report_port_for(runtime)
        if port is None:
            raise StartupNotFound("report_not_ready")
        snapshot = self._current_report_snapshot(case_id, port)
        self._save_report_tuple(
            case_id,
            snapshot,
            {"report_status": "ready"},
            event_type="startup_report.canonical_snapshot",
            event_status="success",
        )
        try:
            return port.html(case_id)
        except (KeyError, LookupError):
            raise StartupNotFound("report_not_ready") from None

    def get_report_pdf(self, case_id: str) -> bytes:
        runtime = self._load_existing(case_id)
        port = self._report_port_for(runtime)
        if port is None:
            _canonical_report_snapshot(runtime)
            raise StartupGateConflict("gate_4_freeze_required")
        snapshot = self._current_report_snapshot(case_id, port)
        self._save_report_tuple(
            case_id,
            snapshot,
            {"report_status": "ready"},
            event_type="startup_report.canonical_snapshot",
            event_status="success",
        )
        try:
            return port.pdf(case_id)
        except (KeyError, LookupError):
            raise StartupNotFound("report_not_ready") from None
        except StartupError:
            raise
        except RuntimeError as exc:
            if str(exc) == "report_renderer_unavailable":
                raise StartupReportRendererUnavailable("report_renderer_unavailable") from None
            if str(exc) == "gate_4_freeze_required":
                raise StartupGateConflict("gate_4_freeze_required") from None
            raise StartupNotFound("report_not_ready")

    def get_profile(self, case_id: str) -> StartupProfileResponse:
        runtime = self._load_existing(case_id)
        profile_id = runtime.get("profile_id")
        profile_hash = runtime.get("profile_hash")
        profile_revision = runtime.get("profile_revision")
        if (
            not isinstance(profile_id, str)
            or not profile_id
            or not isinstance(profile_hash, str)
            or not profile_hash
            or type(profile_revision) is not int
        ):
            raise StartupGateConflict("startup_profile_not_ready")
        port = self._profile_port_for(runtime)
        if port is None:
            raise StartupGateConflict("startup_profile_not_ready")
        try:
            current = port.get_current(UUID(case_id))
            exact = port.get(UUID(profile_id))
        except (KeyError, LookupError, ValueError):
            raise StartupGateConflict("startup_profile_not_ready") from None
        if current.profile_id != exact.profile_id or current.profile_hash != exact.profile_hash:
            raise StartupGateConflict("startup_profile_stale") from None
        if (
            str(exact.case_id) != case_id
            or str(exact.profile_id) != profile_id
            or exact.profile_hash != profile_hash
            or exact.data_revision != profile_revision
        ):
            raise StartupGateConflict("startup_profile_stale") from None
        return _profile_response(case_id, exact)

    def get_gtm(self, case_id: str) -> StartupGtmResponse:
        runtime = self._load_existing(case_id)
        runtime_profile_hash = runtime.get("profile_hash")
        snapshot_id = runtime.get("gtm_snapshot_id")
        snapshot_hash = runtime.get("gtm_snapshot_hash")
        snapshot_revision = runtime.get("gtm_snapshot_revision")
        if (
            not isinstance(snapshot_id, str)
            or not snapshot_id
            or not isinstance(snapshot_hash, str)
            or not snapshot_hash
            or type(snapshot_revision) is not int
        ):
            raise StartupGateConflict("startup_gtm_not_ready")
        gtm_port = self._gtm_port_for(runtime)
        if gtm_port is None:
            raise StartupGateConflict("startup_gtm_not_ready")
        try:
            snapshot = gtm_port.get_current(case_id)
        except (KeyError, LookupError, TypeError, ValueError):
            raise StartupGateConflict("startup_gtm_stale") from None
        profile_port = self._profile_port_for(runtime)
        revision_port = self._case_revision_port_for(runtime)
        if profile_port is None or revision_port is None:
            raise StartupGateConflict("startup_gtm_not_ready")
        try:
            current_profile = profile_port.get_current(UUID(case_id))
            exact_profile = profile_port.get(snapshot.profile_id)
            canonical_revision = revision_port.current_revision(case_id)
        except (KeyError, LookupError, ValueError):
            raise StartupGateConflict("startup_gtm_stale") from None
        if (
            type(canonical_revision) is not int
            or canonical_revision < 1
            or canonical_revision != snapshot.data_revision
            or str(current_profile.case_id) != case_id
            or current_profile.profile_id != exact_profile.profile_id
            or current_profile.profile_hash != exact_profile.profile_hash
            or current_profile.data_revision != canonical_revision
            or str(exact_profile.case_id) != case_id
            or exact_profile.profile_id != snapshot.profile_id
            or runtime_profile_hash != exact_profile.profile_hash
            or exact_profile.data_revision != snapshot.data_revision
        ):
            raise StartupGateConflict("startup_gtm_stale")
        expected_lineage = (
            runtime.get("profile_id"),
            runtime.get("product_validation_snapshot_id"),
            runtime.get("market_research_snapshot_id"),
            runtime.get("data_revision"),
        )
        actual_lineage = (
            str(snapshot.profile_id),
            str(snapshot.product_validation_snapshot_id),
            str(snapshot.market_research_snapshot_id),
            snapshot.data_revision,
        )
        if (
            str(snapshot.case_id) != case_id
            or str(snapshot.snapshot_id) != snapshot_id
            or snapshot.snapshot_hash != snapshot_hash
            or snapshot.data_revision != snapshot_revision
            or expected_lineage != actual_lineage
        ):
            raise StartupGateConflict("startup_gtm_stale")
        return _gtm_response(case_id, snapshot)

    def seed_gate2_preview_for_test(self, case_id: str, preview: dict[str, Any]) -> None:
        self._load_existing(case_id)
        self._workflow_store.save(
            case_id,
            {
                "analysis_status": "gate2_preview_ready",
                "gate2_status": "required",
                "gate2_preview": _sanitize_preview(preview),
            },
        )

    def seed_status_for_test(self, case_id: str, values: dict[str, Any]) -> None:
        self._load_existing(case_id)
        self._workflow_store.save(case_id, values)

    def runtime_for_test(self, case_id: str) -> dict[str, Any]:
        return self._load_existing(case_id)

    def _load_existing(self, case_id: str) -> dict[str, Any]:
        runtime = self._workflow_store.load(case_id)
        if not runtime.get("case_exists"):
            raise StartupNotFound("case_not_found")
        return runtime

    def _status_response(self, case_id: str, runtime: dict[str, Any]) -> StartupStatusResponse:
        return StartupStatusResponse(
            case_id=case_id,
            case_status="awaiting_upload",
            analysis_status=_analysis_status(runtime.get("analysis_status")),
            provider_status=_provider_mode(runtime),
            data_revision=_current_data_revision(runtime),
            active_analysis_thread_id=_active_analysis_thread_id(case_id, runtime),
            langgraph_checkpoint=self._current_langgraph_checkpoint(case_id, runtime),
            gate2_status=_gate_status(runtime.get("gate2_status")),
            gate3_status=_gate_status(runtime.get("gate3_status")),
            gate4_status=_gate_status(runtime.get("gate4_status")),
            report_status=_runtime_report_status(runtime),
            snapshot_hash=_optional_text(runtime.get("canonical_report_snapshot_hash")),
            snapshot_revision=(
                runtime.get("canonical_report_snapshot_revision")
                if type(runtime.get("canonical_report_snapshot_revision")) is int
                else None
            ),
        )

    def _current_langgraph_checkpoint(
        self,
        case_id: str,
        runtime: dict[str, Any],
    ) -> StartupLangGraphCheckpointResponse | None:
        thread_id = _active_analysis_thread_id(case_id, runtime)
        data_revision = _current_data_revision(runtime)
        service = self._analysis_service_for(str(runtime.get("fixture_mode") or "live"))
        read_identity = getattr(service, "checkpoint_identity", None)
        if callable(read_identity):
            try:
                identity = read_identity(thread_id=thread_id)
            except Exception:
                raise StartupGateConflict("analysis_checkpoint_lookup_failed") from None
            return _langgraph_checkpoint_response(
                identity,
                thread_id=thread_id,
                data_revision=data_revision,
            )
        return None

    def _decision_response(self, case_id: str, runtime: dict[str, Any]) -> StartupDecisionResponse:
        return StartupDecisionResponse(
            case_id=case_id,
            analysis_status=_analysis_status(runtime.get("analysis_status")),
            gate2_status=_gate_status(runtime.get("gate2_status")),
            gate3_status=_gate_status(runtime.get("gate3_status")),
            gate4_status=_gate_status(runtime.get("gate4_status")),
            report_status=_runtime_report_status(runtime),
            snapshot_hash=_optional_text(runtime.get("canonical_report_snapshot_hash")),
            snapshot_revision=(
                runtime.get("canonical_report_snapshot_revision")
                if type(runtime.get("canonical_report_snapshot_revision")) is int
                else None
            ),
        )

    def _current_profile_projection(
        self,
        result: dict[str, Any],
        runtime: dict[str, Any],
    ) -> dict[str, Any]:
        case_id = result.get("case_id") or runtime.get("case_id")
        profile_revision = result.get("profile_revision")
        profile_id = result.get("profile_id")
        profile_hash = result.get("profile_hash")
        if (
            not isinstance(case_id, str)
            or not case_id
            or type(profile_revision) is not int
            or not isinstance(profile_id, str)
            or not profile_id
            or not isinstance(profile_hash, str)
            or not profile_hash
        ):
            return {}
        port = self._profile_port_for(runtime)
        if port is None:
            return {}
        try:
            result_profile_id = UUID(profile_id)
            current = port.get_current(UUID(case_id))
        except (KeyError, LookupError, TypeError, ValueError):
            return {}
        if (
            current.data_revision != profile_revision
            or str(current.case_id) != case_id
            or (
                current.profile_id == result_profile_id
                and current.profile_hash == profile_hash
            )
        ):
            return {}
        primary_profile_id = (
            current.parent_profile_id
            if current.analysis_stage is not StartupProfileAnalysisStage.PRIMARY
            else current.profile_id
        )
        return {
            "profile_id": str(current.profile_id),
            "profile_hash": current.profile_hash,
            "profile_revision": current.data_revision,
            "primary_profile_id": str(primary_profile_id) if primary_profile_id else None,
        }

    def _project_graph_result(
        self,
        result: dict[str, Any],
        *,
        runtime: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pending_gate = result.get("pending_gate")
        status = result.get("status")
        values: dict[str, Any] = {
            "last_graph_status": status,
            "last_pending_gate": pending_gate,
        }
        if "evidence_fact_ids" in result:
            values["evidence_fact_ids"] = [str(item) for item in result.get("evidence_fact_ids", [])]
        for key in (
            "profile_id",
            "profile_hash",
            "market_research_snapshot_id",
            "market_research_snapshot_hash",
            "product_validation_snapshot_id",
            "product_validation_snapshot_hash",
            "gtm_snapshot_id",
            "gtm_snapshot_hash",
        ):
            value = result.get(key)
            if isinstance(value, str) and value:
                values[key] = value
        for key in (
            "profile_revision",
            "market_research_snapshot_revision",
            "product_validation_snapshot_revision",
            "gtm_snapshot_revision",
        ):
            value = result.get(key)
            if type(value) is int:
                values[key] = value
        if runtime is not None:
            values.update(self._current_profile_projection(result, runtime))
        report_snapshot_id = result.get("report_snapshot_id")
        if isinstance(report_snapshot_id, str) and report_snapshot_id:
            values["draft_report_snapshot_id"] = report_snapshot_id
            values["canonical_report_snapshot_id"] = report_snapshot_id
        report_snapshot_hash = result.get("report_snapshot_hash")
        if isinstance(report_snapshot_hash, str) and report_snapshot_hash:
            values["canonical_report_snapshot_hash"] = report_snapshot_hash
        if type(result.get("report_snapshot_revision")) is int:
            values["canonical_report_snapshot_revision"] = result["report_snapshot_revision"]
        if status == "approval_required" and pending_gate == "startup_disclosure":
            values.update(
                {
                    "analysis_status": "gate2_preview_ready",
                    "gate2_status": "required",
                    "gate2_preview": _sanitize_preview(
                        {
                            "evidence_fact_ids": values.get("evidence_fact_ids", []),
                            "pending_gate": "startup_disclosure",
                        }
                    ),
                }
            )
        elif status == "review_required" and pending_gate == "startup_gate3_review":
            values.update({"analysis_status": "gate3_review_required", "gate3_status": "required"})
        elif status == "approval_required" and pending_gate == "startup_gate4_freeze":
            values.update(
                {
                    "analysis_status": "analysis_complete_report_pending",
                    "gate4_status": "required",
                }
            )
            if (
                isinstance(values.get("canonical_report_snapshot_id"), str)
                and isinstance(values.get("canonical_report_snapshot_hash"), str)
                and type(values.get("canonical_report_snapshot_revision")) is int
            ):
                values["report_status"] = "ready"
        elif status in {"completed", "completed_with_policy_blocks"} and pending_gate is None:
            values.update({"analysis_status": "analysis_complete_report_pending"})
            if (
                isinstance(values.get("canonical_report_snapshot_id"), str)
                and isinstance(values.get("canonical_report_snapshot_hash"), str)
                and type(values.get("canonical_report_snapshot_revision")) is int
            ):
                values["report_status"] = "ready"
            if status == "completed_with_policy_blocks":
                values["policy_blocked"] = True
                values["policy_block_codes"] = [
                    str(item) for item in result.get("policy_block_codes", [])
                ]
        elif status == "failed":
            values.update(
                {
                    "analysis_status": "failed",
                    "error_code": _workflow_failure_code(result),
                }
            )
        return values

    def _analysis_service_for(self, fixture_mode: str) -> StartupAnalysisPort:
        if fixture_mode == "deterministic_offline" and self._deterministic_analysis_service is not None:
            return self._deterministic_analysis_service
        return self._analysis_service

    def _report_port_for(self, runtime: dict[str, Any]) -> StartupReportPort | None:
        if (
            runtime.get("fixture_mode") == "deterministic_offline"
            and self._deterministic_report_port is not None
        ):
            return self._deterministic_report_port
        return self._report_port

    def _profile_port_for(self, runtime: dict[str, Any]) -> StartupProfileQueryPort | None:
        if (
            runtime.get("fixture_mode") == "deterministic_offline"
            and self._deterministic_profile_port is not None
        ):
            return self._deterministic_profile_port
        return self._profile_port

    def _gtm_port_for(self, runtime: dict[str, Any]) -> StartupGtmQueryPort | None:
        if (
            runtime.get("fixture_mode") == "deterministic_offline"
            and self._deterministic_gtm_port is not None
        ):
            return self._deterministic_gtm_port
        return self._gtm_port

    def _case_revision_port_for(
        self,
        runtime: dict[str, Any],
    ) -> CanonicalStartupCaseRevisionPort | None:
        if (
            runtime.get("fixture_mode") == "deterministic_offline"
            and self._deterministic_case_revision_port is not None
        ):
            return self._deterministic_case_revision_port
        return self._case_revision_port

    def _audit_spool_for(self, runtime: dict[str, Any]) -> StartupAuditSpool | None:
        if (
            runtime.get("fixture_mode") == "deterministic_offline"
            and self._deterministic_audit_spool is not None
        ):
            return self._deterministic_audit_spool
        return self._audit_spool

    def _current_report_snapshot(
        self,
        case_id: str,
        port: StartupReportPort,
    ) -> CanonicalReportSnapshot:
        try:
            return port.current_snapshot(case_id)
        except (KeyError, LookupError):
            raise StartupNotFound("report_not_ready") from None

    def _save_report_tuple(
        self,
        case_id: str,
        snapshot: CanonicalReportSnapshot,
        values: dict[str, Any] | None = None,
        *,
        event_type: str | None = None,
        event_status: str = "success",
        decision: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "canonical_report_snapshot_id": snapshot.snapshot_id,
            "canonical_report_snapshot_hash": snapshot.snapshot_hash,
            "canonical_report_snapshot_revision": snapshot.snapshot_revision,
        }
        if values:
            payload.update(values)
        if event_type is not None:
            runtime = self._load_existing(case_id)
            gate4_status = str(
                payload.get("gate4_status") or runtime.get("gate4_status") or "not_ready"
            )
            marker_key = _report_audit_marker_key(event_type)
            marker_value = _report_audit_marker_value(
                event_type=event_type,
                snapshot=snapshot,
                gate4_status=gate4_status,
                decision=decision,
            )
            if runtime.get(marker_key) != marker_value:
                self._emit_report_audit_event(
                    case_id,
                    runtime=runtime,
                    snapshot=snapshot,
                    event_type=event_type,
                    event_status=event_status,
                    gate4_status=gate4_status,
                    decision=decision,
                )
                payload[marker_key] = marker_value
        self._workflow_store.save(case_id, payload)

    def _emit_report_audit_event(
        self,
        case_id: str,
        *,
        runtime: dict[str, Any],
        snapshot: CanonicalReportSnapshot,
        event_type: str,
        event_status: str,
        gate4_status: str,
        decision: str | None,
    ) -> None:
        audit_spool = self._audit_spool_for(runtime)
        if audit_spool is None:
            return
        attributes: dict[str, str | int | float | bool | None] = {
            "case_id": case_id,
            "status": event_status,
            "report_status": "canonical",
            "report_id": snapshot.snapshot_id,
            "report_revision": snapshot.snapshot_revision,
            "report_checksum": _safe_report_checksum(snapshot.snapshot_hash),
            "gate4_status": gate4_status,
        }
        if decision is not None:
            attributes["decision"] = decision
        try:
            audit_spool.append(
                AuditEvent(
                    schema_version="audit_event@1",
                    event_id=f"startup-report-{uuid4().hex}",
                    timestamp_utc=_utc_now_z(),
                    run_id=_startup_audit_run_id(case_id),
                    correlation_id=case_id,
                    span_name="report.generate",
                    event_type=event_type,
                    attributes=attributes,
                )
            )
        except Exception as exc:
            raise StartupReportRendererUnavailable("startup_audit_append_failed") from exc

    def _provider_status(self, fixture_mode: str) -> ProviderStatus:
        if fixture_mode == "deterministic_offline" and self._deterministic_analysis_service is not None:
            return "deterministic_offline_fixture"
        if fixture_mode == "live" and self._live_provider_configured:
            return "configured"
        return "unavailable"


def _profile_response(case_id: str, profile: StartupProfile) -> StartupProfileResponse:
    fields: dict[str, StartupProfileFieldResponse] = {}
    for name in StartupProfileFieldName:
        field = profile.fields[name.value]
        fields[name.value] = StartupProfileFieldResponse(
            status=field.status.value,
            values=list(field.values),
            confidence=str(field.confidence),
            evidence_refs=[
                StartupProfileEvidenceRefResponse(
                    evidence_id=str(ref.evidence_id),
                    fragment_id=str(ref.fragment_id) if ref.fragment_id is not None else None,
                    artifact_id=str(ref.artifact_id),
                    artifact_hash=ref.artifact_hash,
                    locator_hash=ref.locator_hash,
                    page=ref.page,
                    table=ref.table,
                    cell=ref.cell,
                    field_name=ref.field_name.value if ref.field_name is not None else None,
                    confidence=str(ref.confidence),
                )
                for ref in field.evidence_refs
            ],
            dependency_refs=[str(item) for item in field.dependency_refs],
            reason_code=field.reason_code,
            contradiction_ids=[str(item) for item in field.contradiction_ids],
        )
    return StartupProfileResponse(
        case_id=case_id,
        profile_id=str(profile.profile_id),
        profile_hash=profile.profile_hash,
        data_revision=profile.data_revision,
        analysis_stage=profile.analysis_stage.value,
        parent_profile_id=str(profile.parent_profile_id) if profile.parent_profile_id else None,
        fields=fields,
        contradictions=[str(item) for item in profile.contradiction_ids],
        gaps=list(profile.gap_codes),
        parse_inventory=StartupProfileParseInventoryResponse(
            source_hashes=dict(profile.source_hashes),
            parse_outcomes=dict(profile.parse_outcomes),
        ),
    )


def _gtm_response(case_id: str, snapshot: StartupGtmSnapshot) -> StartupGtmResponse:
    return StartupGtmResponse(
        case_id=case_id,
        schema_version="startup_gtm@1",
        snapshot_id=str(snapshot.snapshot_id),
        snapshot_hash=snapshot.snapshot_hash,
        snapshot_revision=snapshot.data_revision,
        status=snapshot.status.value,
        profile_id=str(snapshot.profile_id),
        product_validation_snapshot_id=str(snapshot.product_validation_snapshot_id),
        market_research_snapshot_id=str(snapshot.market_research_snapshot_id),
        dimensions=[
            StartupGtmDimensionResponse(
                name=dimension.name.value,
                status=dimension.status.value,
                evidence_fact_ids=list(dimension.evidence_fact_ids),
                market_source_ids=list(dimension.market_source_ids),
                contradiction_ids=list(dimension.contradiction_ids),
                reason_code=dimension.reason_code,
                gap_code=dimension.gap_code,
            )
            for dimension in snapshot.dimensions
        ],
        launch_plan=[
            StartupGtmLaunchPhaseResponse(
                horizon=phase.horizon.value,
                experiment_codes=[code.value for code in phase.experiment_codes],
            )
            for phase in snapshot.launch_plan
        ],
        finding_ids=list(snapshot.finding_ids),
        built_at=snapshot.built_at,
    )


def _fixture_mode(value: Any) -> FixtureMode:
    if value == "deterministic_offline":
        return "deterministic_offline"
    if value == "live":
        return "live"
    raise StartupValidationError("invalid_fixture_mode")


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_declared_mime_type(value: Any) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    if "\r" in text or "\n" in text:
        return None
    media_type = text.split(";", maxsplit=1)[0].strip().lower()
    if len(media_type) > 127:
        return None
    if not _SAFE_MEDIA_TYPE.fullmatch(media_type):
        return None
    return media_type


def _token_digest(case_id: str, gate: str, token: str) -> str:
    return sha256(f"{case_id}:{gate}:{token}".encode()).hexdigest()


def _sanitize_preview(preview: dict[str, Any]) -> dict[str, Any]:
    blocked = {"filename", "filenames", "original_filename", "original_filenames", "resume_token"}
    return {str(key): value for key, value in preview.items() if str(key) not in blocked}


def _provider_mode(runtime: dict[str, Any]) -> ProviderStatus:
    provider_status = runtime.get("provider_status")
    if provider_status == "deterministic_offline_fixture":
        return "deterministic_offline_fixture"
    if provider_status == "configured":
        return "configured"
    return "unavailable"


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    allowed = {"company_name", "website", "as_of", "document_class_hint"}
    return {
        key: text
        for key in allowed
        if (text := _optional_text(metadata.get(key))) is not None
    }


def _canonical_private_suffix(filename: Any) -> str:
    basename = _safe_basename(filename)
    suffix = Path(basename).suffix.lower()
    if suffix in _ALLOWED_PRIVATE_SUFFIXES:
        return suffix
    return ".bin"


def _safe_basename(filename: Any) -> str:
    text = _optional_text(filename)
    if text is None:
        return ""
    return text.replace("\\", "/").rsplit("/", maxsplit=1)[-1]


def _source_name_sha256(filename: Any) -> str:
    return sha256(_safe_basename(filename).encode("utf-8")).hexdigest()


def _runtime_documents(runtime: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in runtime.get("documents", []) if isinstance(item, dict)]


def _sort_runtime_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        documents,
        key=lambda item: (
            _document_number(str(item.get("document_id") or "")),
            str(item.get("document_id") or ""),
        ),
    )


def _pending_document_uploads(runtime: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_pending = runtime.get("pending_document_uploads")
    if not isinstance(raw_pending, dict):
        return {}
    return {
        str(content_hash): dict(record)
        for content_hash, record in raw_pending.items()
        if isinstance(record, dict)
    }


def _pending_record_document(record: dict[str, Any]) -> dict[str, Any]:
    document = record.get("document")
    if not isinstance(document, dict):
        raise StartupGateConflict("document_upload_pending_invalid")
    return dict(document)


def _pending_upload_is_stale(record: dict[str, Any]) -> bool:
    created_at = record.get("created_at")
    if not isinstance(created_at, int | float):
        return True
    return time.time() - float(created_at) > _PENDING_UPLOAD_LEASE_TTL_SECONDS


def _pending_file_identity(
    content_hash: str,
    record: dict[str, Any],
) -> tuple[str, str, str]:
    document = _pending_record_document(record)
    lease_id = record.get("lease_id")
    private_name = document.get("private_name")
    if not isinstance(lease_id, str) or not isinstance(private_name, str):
        raise StartupGateConflict("document_upload_pending_invalid")
    return (content_hash, lease_id, private_name)


def _next_document_id(
    document_ids: list[str],
    pending_uploads: dict[str, dict[str, Any]],
) -> str:
    used_numbers = [_document_number(document_id) for document_id in document_ids]
    for record in pending_uploads.values():
        document = record.get("document")
        if isinstance(document, dict):
            used_numbers.append(_document_number(str(document.get("document_id") or "")))
    return f"doc-{max(used_numbers, default=0) + 1:04d}"


def _document_number(document_id: str) -> int:
    match = re.fullmatch(r"doc-(\d{4,})", document_id)
    return int(match.group(1)) if match is not None else 0


def _write_and_verify_pending_files(
    case_dir: Path,
    pending_files: list[tuple[str, str, str, bytes]],
) -> None:
    for content_hash, _lease_id, private_name, content in pending_files:
        _atomic_write_verified(case_dir / private_name, content, expected_hash=content_hash)


def _atomic_write_verified(path: Path, content: bytes, *, expected_hash: str) -> None:
    if path.exists() and not path.is_file():
        raise StartupGateConflict("document_storage_conflict")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if sha256(temp.read_bytes()).hexdigest() != expected_hash:
            raise StartupGateConflict("document_storage_hash_mismatch")
        temp.replace(path)
        if sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise StartupGateConflict("document_storage_hash_mismatch")
    finally:
        temp.unlink(missing_ok=True)


def _recover_stale_pending_files(
    case_dir: Path,
    stale_pending_files: list[tuple[str, str, str]],
) -> None:
    for _content_hash, _lease_id, private_name in stale_pending_files:
        path = case_dir / private_name
        if path.exists():
            if not path.is_file():
                raise StartupGateConflict("document_storage_conflict")
            path.unlink()
        for temp in case_dir.glob(f".{private_name}.*.tmp"):
            if temp.is_file():
                temp.unlink()


def _release_pending_uploads(
    runtime: dict[str, Any],
    pending_files: list[tuple[str, str, str, bytes]],
) -> dict[str, Any]:
    pending_uploads = _pending_document_uploads(runtime)
    for content_hash, lease_id, _private_name, _content in pending_files:
        pending_record = pending_uploads.get(content_hash)
        if pending_record is not None and pending_record.get("lease_id") == lease_id:
            pending_uploads.pop(content_hash, None)
    return {
        "pending_document_uploads": pending_uploads if pending_uploads else DELETE_RUNTIME_VALUE,
    }


def _release_stale_pending_uploads(
    runtime: dict[str, Any],
    stale_pending_files: list[tuple[str, str, str]],
) -> dict[str, Any]:
    pending_uploads = _pending_document_uploads(runtime)
    for content_hash, lease_id, _private_name in stale_pending_files:
        pending_record = pending_uploads.get(content_hash)
        if pending_record is not None and pending_record.get("lease_id") == lease_id:
            pending_uploads.pop(content_hash, None)
    return {
        "pending_document_uploads": pending_uploads if pending_uploads else DELETE_RUNTIME_VALUE,
    }


def _wait_for_pending_upload_retry() -> None:
    time.sleep(0.01)


def _release_start_claim(
    runtime: dict[str, Any],
    *,
    thread_id: str,
    data_revision: int,
) -> dict[str, Any]:
    if (
        runtime.get("analysis_start_claim_thread_id") != thread_id
        or runtime.get("analysis_start_claim_data_revision") != data_revision
    ):
        return {}
    return {
        "analysis_start_claim_thread_id": DELETE_RUNTIME_VALUE,
        "analysis_start_claim_data_revision": DELETE_RUNTIME_VALUE,
        "analysis_start_claim_status": "retryable",
    }


def _start_payload(
    case_id: str,
    *,
    document_ids: list[str],
    source_refs: list[dict[str, str]],
    data_revision: int,
    fixture_mode: Any,
    execution_mode: ProviderStatus,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "run_id": f"startup-api-{case_id}",
        "correlation_id": case_id,
        "source_document_ids": list(document_ids),
        "source_refs": source_refs,
        "data_revision": data_revision,
        "fixture_mode": fixture_mode,
        "execution_mode": execution_mode,
    }


def _analysis_revision_seed_payload(
    case_id: str,
    runtime: dict[str, Any],
) -> dict[str, Any] | None:
    data_revision = _current_data_revision(runtime)
    document_ids = runtime.get("source_document_ids")
    source_refs = runtime.get("source_refs")
    if (
        data_revision < 1
        or not isinstance(document_ids, list)
        or not document_ids
        or not all(isinstance(item, str) and item for item in document_ids)
        or not isinstance(source_refs, list)
        or not source_refs
        or runtime.get("source_refs_revision") != data_revision
    ):
        return None
    canonical_refs: list[dict[str, str]] = []
    for item in source_refs:
        if not isinstance(item, dict):
            return None
        document_id = item.get("document_id")
        private_name = item.get("private_name")
        content_sha256 = item.get("content_sha256")
        if (
            not isinstance(document_id, str)
            or not document_id
            or not isinstance(private_name, str)
            or not private_name
            or not isinstance(content_sha256, str)
            or not content_sha256
        ):
            return None
        canonical_refs.append(
            {
                "document_id": document_id,
                "private_name": private_name,
                "content_sha256": content_sha256,
            }
        )
    return _start_payload(
        case_id,
        document_ids=list(document_ids),
        source_refs=canonical_refs,
        data_revision=data_revision,
        fixture_mode=runtime.get("fixture_mode"),
        execution_mode=_provider_mode(runtime),
    )


def _analysis_revision_seed_runtime_matches(
    runtime: dict[str, Any],
    *,
    thread_id: str,
    data_revision: int,
) -> bool:
    analysis_status = runtime.get("analysis_status")
    return (
        _current_data_revision(runtime) == data_revision
        and runtime.get("active_analysis_thread_id") == thread_id
        and runtime.get("analysis_start_claim_thread_id") == thread_id
        and runtime.get("analysis_start_claim_data_revision") == data_revision
        and (
            analysis_status == "gate2_preview_ready"
            or (
                analysis_status == "failed"
                and runtime.get("analysis_revision_seed_status") in {"retryable", "starting"}
            )
        )
    )


def _complete_analysis_revision_seed_without_claim(
    runtime: dict[str, Any],
    *,
    thread_id: str,
    data_revision: int,
) -> dict[str, Any]:
    if not _analysis_revision_seed_runtime_matches(
        runtime,
        thread_id=thread_id,
        data_revision=data_revision,
    ):
        return {}
    return {
        "analysis_revision_seed_required": True,
        "analysis_revision_seed_status": "seeded",
        "analysis_revision_seed_claim_id": DELETE_RUNTIME_VALUE,
    }


def _fail_analysis_revision_seed(
    runtime: dict[str, Any],
    *,
    claim_id: str,
    thread_id: str,
    data_revision: int,
) -> dict[str, Any]:
    if (
        runtime.get("analysis_revision_seed_claim_id") != claim_id
        or _current_data_revision(runtime) != data_revision
        or runtime.get("active_analysis_thread_id") != thread_id
    ):
        return {}
    return {
        "analysis_status": "failed",
        "gate2_status": "required",
        "error_code": "analysis_revision_seed_failed",
        "analysis_revision_seed_required": True,
        "analysis_revision_seed_status": "retryable",
        "analysis_revision_seed_claim_id": DELETE_RUNTIME_VALUE,
        "gate2_resume_token_digest": DELETE_RUNTIME_VALUE,
        "gate2_resume_token_used": DELETE_RUNTIME_VALUE,
    }


def _advance_case_revision(
    revision_port: CanonicalStartupCaseRevisionPort,
    case_id: str,
    *,
    runtime: dict[str, Any],
    document_ids: list[str],
    source_refs: list[dict[str, str]],
    metadata: dict[str, str],
) -> int:
    current_revision = _canonical_case_revision(revision_port, case_id)
    runtime_revision = _current_data_revision(runtime)
    if runtime_revision > current_revision:
        raise StartupGateConflict("case_revision_conflict")
    requested_revision = revision_port.advance_revision(
        case_id,
        expected_current_revision=current_revision,
        document_ids=list(document_ids),
        source_refs=[dict(item) for item in source_refs],
        metadata=dict(metadata),
    )
    expected_revision = current_revision + 1
    if requested_revision != expected_revision:
        raise StartupGateConflict("case_revision_conflict")
    return requested_revision


def _reconcile_case_revision(
    revision_port: CanonicalStartupCaseRevisionPort,
    case_id: str,
    *,
    runtime: dict[str, Any],
) -> int:
    current_revision = _canonical_case_revision(revision_port, case_id)
    runtime_revision = _current_data_revision(runtime)
    if current_revision < 1 or (runtime_revision >= 1 and runtime_revision > current_revision):
        raise StartupGateConflict("case_revision_conflict")
    return current_revision


def _canonical_case_revision(
    revision_port: CanonicalStartupCaseRevisionPort,
    case_id: str,
) -> int:
    revision = revision_port.current_revision(case_id)
    if type(revision) is not int or revision < 0:
        raise StartupGateConflict("case_revision_conflict")
    return revision


def _current_data_revision(runtime: dict[str, Any]) -> int:
    revision = runtime.get("data_revision")
    if type(revision) is int and revision >= 1:
        return revision
    return 1 if runtime.get("document_ids") else 0


def _langgraph_checkpoint_response(
    value: Any,
    *,
    thread_id: str,
    data_revision: int,
) -> StartupLangGraphCheckpointResponse | None:
    if not isinstance(value, dict):
        return None
    checkpoint_id = _optional_text(value.get("checkpoint_id"))
    checkpoint_hash = _optional_text(value.get("checkpoint_hash"))
    checkpoint_revision = value.get("data_revision")
    if (
        checkpoint_id is None
        or re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{5,127}", checkpoint_id, re.IGNORECASE) is None
        or checkpoint_hash is None
        or re.fullmatch(r"[a-f0-9]{64}", checkpoint_hash) is None
        or type(checkpoint_revision) is not int
        or checkpoint_revision != data_revision
        or not thread_id
    ):
        return None
    return StartupLangGraphCheckpointResponse(
        checkpoint_hash=checkpoint_hash,
        checkpoint_id=checkpoint_id,
        data_revision=checkpoint_revision,
        thread_id=thread_id,
    )


def _analysis_thread_id(case_id: str, data_revision: int) -> str:
    return f"{case_id}:r{data_revision}"


def _active_analysis_thread_id(case_id: str, runtime: dict[str, Any]) -> str:
    thread_id = runtime.get("active_analysis_thread_id")
    if isinstance(thread_id, str) and thread_id:
        return thread_id
    revision = _current_data_revision(runtime)
    return _analysis_thread_id(case_id, revision) if revision else case_id


def _startup_audit_run_id(case_id: str) -> str:
    return f"startup-api-{case_id}"


def _report_audit_marker_key(event_type: str) -> str:
    suffix = "gate4" if event_type == "startup_report.gate4_completed" else "canonical"
    return f"startup_report_audit_{suffix}_marker"


def _report_audit_marker_value(
    *,
    event_type: str,
    snapshot: CanonicalReportSnapshot,
    gate4_status: str,
    decision: str | None,
) -> str:
    payload = "|".join(
        (
            event_type,
            snapshot.snapshot_id,
            snapshot.snapshot_hash,
            str(snapshot.snapshot_revision),
            gate4_status,
            decision or "",
        )
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _safe_report_checksum(value: str) -> str:
    if value.startswith("sha256:"):
        value = value.removeprefix("sha256:")
    if not re.fullmatch(r"[A-Fa-f0-9]{32,128}", value):
        raise StartupReportRendererUnavailable("startup_audit_append_failed")
    return value


def _utc_now_z() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _source_refs(documents: list[Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for item in documents:
        if not isinstance(item, dict):
            continue
        document_id = item.get("document_id")
        private_name = item.get("private_name")
        content_sha256 = item.get("content_sha256")
        if (
            isinstance(document_id, str)
            and isinstance(private_name, str)
            and isinstance(content_sha256, str)
        ):
            refs.append(
                {
                    "document_id": document_id,
                    "private_name": private_name,
                    "content_sha256": content_sha256,
                }
            )
    return refs


def _revision_invalidation_values(data_revision: int, active_thread_id: str) -> dict[str, Any]:
    return {
        "data_revision": data_revision,
        "active_analysis_thread_id": active_thread_id,
        "analysis_status": "awaiting_start",
        "gate2_status": "not_ready",
        "gate3_status": "not_ready",
        "gate4_status": "not_ready",
        "report_status": "not_ready",
        "gate2_preview": None,
        "gate2_resume_token_digest": None,
        "gate2_resume_token_used": False,
        "canonical_report_snapshot_id": None,
        "canonical_report_snapshot_hash": None,
        "canonical_report_snapshot_revision": None,
        "draft_report_snapshot_id": None,
        "profile_id": None,
        "profile_hash": None,
        "profile_revision": None,
        "primary_profile_id": None,
        "gate3_reviewed": DELETE_RUNTIME_VALUE,
        "gate3_exclusions": DELETE_RUNTIME_VALUE,
        "gate3_exclusion_reasons": DELETE_RUNTIME_VALUE,
        "gate3_recompute_started": DELETE_RUNTIME_VALUE,
        "gate3_report_finalized": DELETE_RUNTIME_VALUE,
        "gate3_affected_nodes": DELETE_RUNTIME_VALUE,
        "gate3_invalidation_chain": DELETE_RUNTIME_VALUE,
        "last_reflexion_contradictions": DELETE_RUNTIME_VALUE,
        "startup_pending_critic_review": DELETE_RUNTIME_VALUE,
        "invalidated_ids": DELETE_RUNTIME_VALUE,
        "gate4_reviewed": DELETE_RUNTIME_VALUE,
        "gate4_last_decision": DELETE_RUNTIME_VALUE,
    }


def _sanitize_reason(value: Any) -> str | None:
    text = _optional_text(value)
    if text is None:
        return None
    safe = "".join(char if char.isalnum() or char in " _-" else " " for char in text)
    return " ".join(safe.split())[:200] or None


def _canonical_report_snapshot(runtime: dict[str, Any]) -> CanonicalReportSnapshot:
    snapshot_id = runtime.get("canonical_report_snapshot_id")
    snapshot_hash = runtime.get("canonical_report_snapshot_hash")
    snapshot_revision = runtime.get("canonical_report_snapshot_revision")
    if (
        not isinstance(snapshot_id, str)
        or not snapshot_id
        or not isinstance(snapshot_hash, str)
        or not snapshot_hash
        or type(snapshot_revision) is not int
    ):
        raise StartupNotFound("report_not_ready")
    return CanonicalReportSnapshot(
        snapshot_id=snapshot_id,
        snapshot_hash=snapshot_hash,
        snapshot_revision=snapshot_revision,
    )


def _has_canonical_report_tuple(runtime: dict[str, Any]) -> bool:
    return (
        isinstance(runtime.get("canonical_report_snapshot_id"), str)
        and bool(runtime.get("canonical_report_snapshot_id"))
        and isinstance(runtime.get("canonical_report_snapshot_hash"), str)
        and bool(runtime.get("canonical_report_snapshot_hash"))
        and type(runtime.get("canonical_report_snapshot_revision")) is int
    )


def _analysis_status(value: Any) -> AnalysisStatus:
    allowed = {
        "awaiting_upload",
        "awaiting_start",
        "gate2_preview_ready",
        "gate3_review_required",
        "analysis_complete_report_pending",
        "failed",
    }
    return str(value) if value in allowed else "awaiting_upload"  # type: ignore[return-value]


def _gate_status(value: Any) -> GateStatus:
    allowed = {"not_ready", "required", "completed"}
    return str(value) if value in allowed else "not_ready"  # type: ignore[return-value]


def _report_status(value: Any) -> ReportStatus:
    if value == "ready":
        return "ready"
    return "pending" if value == "pending" else "not_ready"


def _runtime_report_status(runtime: dict[str, Any]) -> ReportStatus:
    if _has_canonical_report_tuple(runtime):
        return "ready"
    return _report_status(runtime.get("report_status"))


def _workflow_failure_code(result: dict[str, Any]) -> str:
    code = _optional_text(result.get("error_code"))
    if code == "BUDGET_EXCEEDED":
        return "budget_exceeded"
    if code is None or not re.fullmatch(r"[a-z0-9_]{1,64}", code):
        return "workflow_failed"
    return code


def _freeze_status(value: Any) -> FreezeStatus:
    return str(value) if value in {"not_ready", "required", "approved"} else "required"  # type: ignore[return-value]


def _pdf_status(value: Any) -> PdfStatus:
    return str(value) if value in {"not_ready", "freeze_required", "ready"} else "freeze_required"  # type: ignore[return-value]
