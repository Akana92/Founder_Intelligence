from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import create_autospec
from uuid import UUID, uuid4

from docx import Document
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
import pytest

from due_diligence_agent.adapters.local_storage.artifact_store import LocalArtifactStore
from due_diligence_agent.adapters.local_storage.repositories import (
    LocalArtifactRepository,
    LocalApprovalRepository,
    LocalCalculationRepository,
    LocalCaseRepository,
    LocalContradictionDecisionRepository,
    LocalContradictionRepository,
    LocalEvidenceRepository,
    LocalFindingRepository,
    LocalReportRepository,
    LocalReviewRepository,
    LocalStartupClaimRepository,
    LocalStartupProfileRepository,
)
from due_diligence_agent.adapters.local_storage.sqlite_db import SQLiteDatabase
from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.adapters.observability.privacy import StrictTraceSanitizer
from due_diligence_agent.adapters.privacy.rules_redactor import RulesRedactor
from due_diligence_agent.adapters.startup.frozen_market_research import (
    FrozenStartupMarketResearchAdapter,
    StartupMarketFixtureUnavailableError,
)
from due_diligence_agent.application.policies.budget import BudgetGuard
from due_diligence_agent.application.policies.data_egress import DataEgressPolicy
from due_diligence_agent.bootstrap.container import build_deterministic_startup_analysis_composer
from due_diligence_agent.bootstrap.container import build_startup_analysis_composer
from due_diligence_agent.bootstrap.container import _StartupPrivacyWorkflowPort
from due_diligence_agent.bootstrap.container import _StartupProviderWorkflowPort
from due_diligence_agent.domain.approvals.startup_disclosure import (
    ClassifiedDisclosureSnapshot,
    StartupDisclosureApproval,
)
from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import (
    AnalysisMode,
    ArtifactParsingStatus,
    CaseStatus,
    ContradictionStatus,
    FindingSeverity,
    FindingStatus,
    SensitivityClass,
)
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.evidence.startup_claims import (
    ClaimCategory,
    ClaimCriticality,
    StartupClaim,
)
from due_diligence_agent.domain.findings.models import Contradiction, Finding
from due_diligence_agent.domain.reports.models import ReportSnapshot, ReproducibilityManifest
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.domain.startup.market import (
    StartupResearchPlan,
    StartupResearchSourceMode,
)
from due_diligence_agent.application.services.startup_disclosure_service import (
    StartupDisclosureService,
)
from due_diligence_agent.application.services.report_service import ReportService
from due_diligence_agent.application.startup_cases import CanonicalReportSnapshot
from due_diligence_agent.application.services.startup_metric_service import StartupMetricService
from due_diligence_agent.application.services.startup_privacy_service import StartupPrivacyService
from due_diligence_agent.domain.documents.models import TextBlock
from due_diligence_agent.ports.llm import LLMBudgetRequest
from due_diligence_agent.ports.tracing import AuditSpool
from due_diligence_agent.workflows.startup.graph import build_startup_graph
from due_diligence_agent.workflows.startup.plan import (
    STARTUP_NODE_REGISTRY,
    default_startup_plan,
    validate_startup_plan,
)
from due_diligence_agent.workflows.startup.runtime import JsonFileStartupWorkflowRuntimeStore
from due_diligence_agent.workflows.startup.state import CHECKPOINT_STATE_KEYS
from due_diligence_agent.workflows.startup.ports import (
    AuditSpoolNodeAudit,
    MetricContractNodeTracer,
    StartupClaimRepositoryAdapter,
    StartupEvidenceRepositoryAdapter,
    StartupGtmWorkflowAdapter,
    StartupLineageRepositoryAdapter,
    StartupMarketResearchWorkflowAdapter,
    StartupMetricWorkflowAdapter,
    StartupProductValidationWorkflowAdapter,
    StartupReadinessWorkflowAdapter,
    StartupReportRepositoryAdapter,
    StartupReportTraceLineageError,
)
from due_diligence_agent.workflows.startup.runtime import SQLiteStartupWorkflowRuntimeStore


CASE_ID = "00000000-0000-0000-0000-000000000901"
RUN_ID = "run-startup-901"
CORRELATION_ID = "corr-startup-901"
RAW_SENTINEL = "raw cap table secret founder@example.com sk-live-secret"
REVENUE_FACT_ID = "10000000-0000-0000-0000-000000000901"
COGS_FACT_ID = "10000000-0000-0000-0000-000000000902"
CALCULATION_ID = "20000000-0000-0000-0000-000000000901"
FINDING_ID = "30000000-0000-0000-0000-000000000901"
CONTRADICTION_ID = "40000000-0000-0000-0000-000000000901"
REPORT_ID = "50000000-0000-0000-0000-000000000901"
READINESS_SNAPSHOT_ID = "70000000-0000-0000-0000-000000000901"
READINESS_SNAPSHOT_HASH = "sha256:" + "7" * 64
MARKET_RESEARCH_SNAPSHOT_ID = "80000000-0000-0000-0000-000000000901"
MARKET_RESEARCH_SNAPSHOT_HASH = "sha256:" + "8" * 64
DOCUMENT_INTELLIGENCE_SNAPSHOT_ID = "90000000-0000-0000-0000-000000000901"
DOCUMENT_INTELLIGENCE_SNAPSHOT_HASH = "sha256:" + "9" * 64
PRODUCT_VALIDATION_SNAPSHOT_ID = "a0000000-0000-0000-0000-000000000901"
PRODUCT_VALIDATION_SNAPSHOT_HASH = "sha256:" + "a" * 64
GTM_SNAPSHOT_ID = "b0000000-0000-0000-0000-000000000901"
GTM_SNAPSHOT_HASH = "sha256:" + "b" * 64
REBUILT_GTM_SNAPSHOT_ID = "b0000000-0000-0000-0000-000000000902"
REBUILT_GTM_SNAPSHOT_HASH = "sha256:" + "c" * 64
EXPECTED_CHECKPOINT_KEYS = {
    "case_id",
    "run_id",
    "correlation_id",
    "data_revision",
    "plan_id",
    "inventory_id",
    "parsed_artifact_ids",
    "sensitivity_summary_id",
    "approval_ids",
    "evidence_fact_ids",
    "startup_claim_ids",
    "document_intelligence_snapshot_id",
    "document_intelligence_snapshot_hash",
    "document_intelligence_snapshot_revision",
    "primary_profile_id",
    "profile_id",
    "profile_hash",
    "profile_revision",
    "calculation_ids",
    "readiness_snapshot_id",
    "readiness_snapshot_hash",
    "readiness_snapshot_revision",
    "market_research_snapshot_id",
    "market_research_snapshot_hash",
    "market_research_snapshot_revision",
    "product_validation_snapshot_id",
    "product_validation_snapshot_hash",
    "product_validation_snapshot_revision",
    "gtm_snapshot_id",
    "gtm_snapshot_hash",
    "gtm_snapshot_revision",
    "finding_ids",
    "contradiction_ids",
    "critic_issue_ids",
    "critic_issue_codes",
    "arbiter_status",
    "gate4_decision",
    "report_snapshot_id",
    "report_snapshot_hash",
    "report_snapshot_revision",
    "reflexion_round",
    "pending_gate",
    "status",
    "error_code",
}

_OPEN_CHECKPOINT_CONTEXTS: list[Any] = []


@pytest.fixture(autouse=True)
def _close_open_checkpoint_contexts() -> Iterator[None]:
    yield
    while _OPEN_CHECKPOINT_CONTEXTS:
        context = _OPEN_CHECKPOINT_CONTEXTS.pop()
        context.__exit__(None, None, None)


def test_startup_graph_pauses_at_disclosure_and_resumes() -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("case"), deps)
    config = _config("startup-case-1")

    paused = graph.invoke(_case_input(), config)
    assert paused["status"] == "approval_required"
    assert paused["pending_gate"] == "startup_disclosure"
    assert paused["data_revision"] == 1
    assert paused["primary_profile_id"] == "60000000-0000-0000-0000-000000000999"
    assert paused["profile_id"] == paused["primary_profile_id"]
    assert paused["profile_hash"] == "sha256:primary-profile"
    assert paused["profile_revision"] == 1
    assert deps.data_room.calls == ["ingest"]
    assert deps.parser.calls == ["parse"]
    assert deps.evidence.calls == ["extract"]
    assert deps.profile.calls == ["build_primary"]

    gate3 = graph.invoke(Command(resume=_approval("approved")), config)
    assert gate3["status"] == "review_required"
    assert gate3["pending_gate"] == "startup_gate3_review"
    gate4 = graph.invoke(Command(resume=_gate3_decision()), config)
    resumed = graph.invoke(Command(resume=_gate4_decision(result=gate4)), config)

    assert resumed["case_id"] == CASE_ID
    assert resumed["run_id"] == RUN_ID
    assert resumed["correlation_id"] == CORRELATION_ID
    assert resumed["status"] == "completed"
    assert resumed["pending_gate"] is None
    assert resumed["report_snapshot_id"] == REPORT_ID
    assert resumed["report_snapshot_hash"] == "sha256:workflow-report"
    assert resumed["report_snapshot_revision"] == 7
    assert resumed["approval_ids"]
    assert resumed["profile_id"] == "60000000-0000-0000-0000-000000000998"
    assert resumed["profile_hash"] == "sha256:enriched-profile"
    assert deps.report.payloads[-1]["profile_id"] == resumed["profile_id"]
    assert deps.report.payloads[-1]["profile_hash"] == resumed["profile_hash"]
    assert deps.report.payloads[-1]["profile_revision"] == resumed["profile_revision"]
    assert deps.provider.calls == ["financial_analysis", "risk_analysis", "market_analysis"]
    assert deps.profile.calls == ["build_primary", "enrich"]


def test_startup_graph_joins_readiness_and_frozen_research_before_market_and_report() -> None:
    deps = StartupWorkflowFixture()
    run_key = f"startup-intelligence-join-{uuid4().hex}"
    graph = _graph(_test_dir(run_key), deps)
    config = _config(run_key)

    graph.invoke(_case_input(), config)
    graph.invoke(Command(resume=_approval("approved")), config)
    gate4 = graph.invoke(Command(resume=_gate3_decision()), config)
    result = graph.invoke(Command(resume=_gate4_decision(result=gate4)), config)

    assert result["readiness_snapshot_id"] == READINESS_SNAPSHOT_ID
    assert result["readiness_snapshot_hash"] == READINESS_SNAPSHOT_HASH
    assert result["readiness_snapshot_revision"] == 1
    assert result["market_research_snapshot_id"] == MARKET_RESEARCH_SNAPSHOT_ID
    assert result["market_research_snapshot_hash"] == MARKET_RESEARCH_SNAPSHOT_HASH
    assert result["market_research_snapshot_revision"] == 1
    assert deps.readiness.payloads == [
        {
            "case_id": CASE_ID,
            "profile_id": "60000000-0000-0000-0000-000000000998",
            "profile_hash": "sha256:enriched-profile",
            "profile_revision": 1,
            "metric_diagnostics": [],
            "calculation_ids": [CALCULATION_ID],
        }
    ]
    assert deps.market_research.payloads == [
        {
            "case_id": CASE_ID,
            "profile_id": "60000000-0000-0000-0000-000000000998",
            "profile_hash": "sha256:enriched-profile",
            "profile_revision": 1,
        }
    ]
    report_payload = deps.report.payloads[-1]
    assert report_payload["readiness_snapshot_id"] == READINESS_SNAPSHOT_ID
    assert report_payload["readiness_snapshot_hash"] == READINESS_SNAPSHOT_HASH
    assert report_payload["market_research_snapshot_id"] == MARKET_RESEARCH_SNAPSHOT_ID
    assert report_payload["market_research_snapshot_hash"] == MARKET_RESEARCH_SNAPSHOT_HASH
    assert report_payload["gtm_snapshot_id"] == GTM_SNAPSHOT_ID
    assert report_payload["gtm_snapshot_hash"] == GTM_SNAPSHOT_HASH
    assert report_payload["gtm_snapshot_revision"] == 1
    executed = [item["node_name"] for item in result["node_results"]]
    assert "market_research" in executed
    assert executed.index("market_analysis") > executed.index("market_research")
    assert executed.index("market_analysis") > executed.index("risk_analysis")


def test_startup_graph_runs_explicit_document_and_product_validation_roles() -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("explicit-startup-roles"), deps)
    config = _config("explicit-startup-roles")

    paused = graph.invoke(_case_input(raw_payload=RAW_SENTINEL), config)

    assert paused["document_intelligence_snapshot_id"] == DOCUMENT_INTELLIGENCE_SNAPSHOT_ID
    assert paused["document_intelligence_snapshot_hash"] == DOCUMENT_INTELLIGENCE_SNAPSHOT_HASH
    assert paused["document_intelligence_snapshot_revision"] == 1
    assert deps.document_intelligence.payloads == [
        {
            "case_id": CASE_ID,
            "data_revision": 1,
            "inventory_id": "inventory-901",
            "source_document_ids": ["doc-0001"],
            "artifact_ids": ["artifact-pitch-pdf"],
            "parsed_artifact_ids": ["parsed-pitch-pdf"],
            "evidence_fact_ids": [REVENUE_FACT_ID, COGS_FACT_ID],
            "startup_claim_ids": ["claim-market-timing", "claim-unit-economics"],
            "quarantine_reason_codes": [],
        }
    ]

    gate3 = graph.invoke(Command(resume=_approval("approved")), config)

    assert gate3["product_validation_snapshot_id"] == PRODUCT_VALIDATION_SNAPSHOT_ID
    assert gate3["product_validation_snapshot_hash"] == PRODUCT_VALIDATION_SNAPSHOT_HASH
    assert gate3["product_validation_snapshot_revision"] == 1
    assert deps.product_validation.payloads == [
        {
            "case_id": CASE_ID,
            "profile_id": "60000000-0000-0000-0000-000000000998",
            "profile_hash": "sha256:enriched-profile",
            "profile_revision": 1,
            "evidence_fact_ids": [REVENUE_FACT_ID, COGS_FACT_ID],
            "startup_claim_ids": ["claim-market-timing", "claim-unit-economics"],
            "claim_status_by_id": {},
            "contradiction_ids": [],
        }
    ]
    executed = [item["node_name"] for item in gate3["node_results"]]
    assert executed.index("document_intelligence") > executed.index("claims")
    assert executed.index("document_intelligence") < executed.index("primary_profile")
    assert executed.index("product_validation") > executed.index("profile_enrichment")
    assert executed.index("metrics") > executed.index("product_validation")
    assert executed.index("market_research") > executed.index("product_validation")
    assert RAW_SENTINEL not in repr(deps.document_intelligence.payloads)
    assert RAW_SENTINEL not in repr(deps.product_validation.payloads)
    assert "private_name" not in repr(deps.document_intelligence.payloads)
    assert "content_sha256" not in repr(deps.document_intelligence.payloads)


def test_startup_graph_runs_explicit_gtm_role_before_reflexion() -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("explicit-startup-gtm-role"), deps)
    config = _config("explicit-startup-gtm-role")

    graph.invoke(_case_input(raw_payload=RAW_SENTINEL), config)
    gate3 = graph.invoke(Command(resume=_approval("approved")), config)

    assert gate3["gtm_snapshot_id"] == GTM_SNAPSHOT_ID
    assert gate3["gtm_snapshot_hash"] == GTM_SNAPSHOT_HASH
    assert gate3["gtm_snapshot_revision"] == 1
    assert deps.gtm.payloads == [
        {
            "case_id": CASE_ID,
            "profile_id": "60000000-0000-0000-0000-000000000998",
            "profile_hash": "sha256:enriched-profile",
            "profile_revision": 1,
            "product_validation_snapshot_id": PRODUCT_VALIDATION_SNAPSHOT_ID,
            "product_validation_snapshot_hash": PRODUCT_VALIDATION_SNAPSHOT_HASH,
            "product_validation_snapshot_revision": 1,
            "market_research_snapshot_id": MARKET_RESEARCH_SNAPSHOT_ID,
            "market_research_snapshot_hash": MARKET_RESEARCH_SNAPSHOT_HASH,
            "market_research_snapshot_revision": 1,
            "evidence_fact_ids": [REVENUE_FACT_ID, COGS_FACT_ID],
            "finding_ids": ["finding-financial", FINDING_ID, "finding-market"],
            "contradiction_ids": [],
        }
    ]
    executed = [item["node_name"] for item in gate3["node_results"]]
    assert executed.index("gtm") > executed.index("market_analysis")
    assert executed.index("gtm") < executed.index("critic")
    assert executed.index("critic") < executed.index("arbiter")
    assert RAW_SENTINEL not in repr(deps.gtm.payloads)


def test_document_product_and_gtm_role_outputs_survive_restart_without_reprocessing() -> None:
    root = _test_dir("startup-role-restart")
    checkpoint_path = root / "startup-checkpoints.sqlite3"
    durable_path = root / "runtime.json"
    config = _config("startup-role-restart")
    deps = StartupWorkflowFixture(
        runtime_store=JsonFileStartupWorkflowRuntimeStore(durable_path)
    )

    with _sqlite_saver(checkpoint_path) as saver:
        graph = build_startup_graph(deps, checkpointer=saver)
        graph.invoke(_case_input(), config)
        gate3 = graph.invoke(Command(resume=_approval("approved")), config)

    assert gate3["status"] == "review_required"
    restarted_deps = StartupWorkflowFixture(
        runtime_store=JsonFileStartupWorkflowRuntimeStore(durable_path)
    )
    with _sqlite_saver(checkpoint_path) as saver:
        result = build_startup_graph(restarted_deps, checkpointer=saver).invoke(
            Command(resume=_gate3_decision()),
            config,
        )

    assert result["document_intelligence_snapshot_id"] == DOCUMENT_INTELLIGENCE_SNAPSHOT_ID
    assert result["product_validation_snapshot_id"] == PRODUCT_VALIDATION_SNAPSHOT_ID
    assert result["gtm_snapshot_id"] == GTM_SNAPSHOT_ID
    assert restarted_deps.document_intelligence.payloads == []
    assert restarted_deps.product_validation.payloads == []
    assert restarted_deps.gtm.payloads == []


def test_document_and_product_roles_emit_safe_audit_and_trace_events() -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("startup-role-trace"), deps)
    config = _config("startup-role-trace")

    graph.invoke(_case_input(raw_payload=RAW_SENTINEL), config)
    graph.invoke(Command(resume=_approval("approved")), config)

    for node_name, tool in (
        ("document_intelligence", "startup_document_intelligence"),
        ("product_validation", "startup_product_validation"),
        ("gtm", "startup_gtm"),
    ):
        audit = _single_payload(deps.audit.payloads, node_name)
        span = _single_payload(deps.tracer.spans, node_name)
        for payload in (audit, span):
            assert payload["case_id"] == CASE_ID
            assert payload["run_id"] == RUN_ID
            assert payload["correlation_id"] == CORRELATION_ID
            assert payload["attempt"] == 1
            assert payload["retry_count"] == 0
            assert payload["checkpoint_id"].startswith(f"startup-{node_name}-")
            assert payload["tool"] == tool
            assert RAW_SENTINEL not in repr(payload)
            assert "source_refs" not in payload


def test_checkpoint_can_resume_after_process_restart_without_repeating_ingest_or_parse(
) -> None:
    root = _test_dir("restart")
    checkpoint_path = root / "startup-checkpoints.sqlite3"
    durable_path = root / "runtime.json"
    durable = JsonFileStartupWorkflowRuntimeStore(durable_path)
    deps = StartupWorkflowFixture(runtime_store=durable)
    config = _config(f"restart-case-{root.name}")

    with _sqlite_saver(checkpoint_path) as saver:
        build_startup_graph(deps, checkpointer=saver).invoke(_case_input(), config)

    restarted_deps = StartupWorkflowFixture(
        runtime_store=JsonFileStartupWorkflowRuntimeStore(durable_path)
    )

    with _sqlite_saver(checkpoint_path) as saver:
        restarted = build_startup_graph(restarted_deps, checkpointer=saver)
        restarted.invoke(Command(resume=_approval("approved")), config)
        result = restarted.invoke(Command(resume=_gate3_decision()), config)

    assert result["case_id"] == CASE_ID
    assert result["run_id"] == RUN_ID
    assert result["correlation_id"] == CORRELATION_ID
    assert restarted_deps.data_room.calls == []
    assert restarted_deps.parser.calls == []
    assert restarted_deps.provider.calls == ["financial_analysis", "risk_analysis", "market_analysis"]
    assert result["primary_profile_id"] == "60000000-0000-0000-0000-000000000999"
    assert result["profile_hash"] == "sha256:enriched-profile"
    assert restarted_deps.profile.calls == ["enrich"]
    assert restarted_deps.privacy.snapshot is not deps.privacy.snapshot


def test_startup_checkpoint_state_is_id_only_and_never_serializes_raw_payload(
) -> None:
    checkpoint_path = _test_dir("id-only") / "startup-id-only.sqlite3"
    deps = StartupWorkflowFixture()
    with _sqlite_saver(checkpoint_path) as saver:
        graph = build_startup_graph(deps, checkpointer=saver)
        graph.invoke(_case_input(raw_payload=RAW_SENTINEL), _config("id-only-case"))

    checkpoint_bytes = checkpoint_path.read_bytes()
    assert RAW_SENTINEL.encode() not in checkpoint_bytes
    assert b"pitch.pdf" not in checkpoint_bytes
    assert set(CHECKPOINT_STATE_KEYS) == EXPECTED_CHECKPOINT_KEYS
    assert deps.tracer.checkpoint_keys == EXPECTED_CHECKPOINT_KEYS
    runtime = deps.runtime_store.records[CASE_ID]
    assert "sources" not in runtime
    assert "raw_payload_seen" not in runtime
    assert runtime["data_revision"] == 1
    assert runtime["source_document_ids"] == ["doc-0001"]
    assert runtime["source_refs"] == [
        {
            "document_id": "doc-0001",
            "private_name": "doc-0001.pdf",
            "content_sha256": "0" * 64,
        }
    ]
    with _sqlite_saver(checkpoint_path) as saver:
        graph = build_startup_graph(deps, checkpointer=saver)
        graph.invoke(Command(resume=_approval("denied")), _config("id-only-case"))
    assert RAW_SENTINEL.encode() not in checkpoint_path.read_bytes()
    assert b"pitch.pdf" not in checkpoint_path.read_bytes()


def test_startup_graph_rejects_missing_or_invalid_source_refs_before_checkpoint(
) -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("invalid-source-ref"), deps)

    payload = _case_input()
    payload.pop("source_refs")
    with pytest.raises(ValueError, match="startup_source_refs_required"):
        graph.invoke(payload, _config("missing-source-refs"))

    invalid = _case_input(
        source_refs=[
            {
                "document_id": "doc-0001",
                "private_name": "..\\pitch.pdf",
                "content_sha256": "0" * 64,
            }
        ]
    )
    with pytest.raises(ValueError, match="startup_source_ref_private_name_invalid"):
        graph.invoke(invalid, _config("invalid-source-private-name"))

    invalid_hash = _case_input(
        source_refs=[
            {
                "document_id": "doc-0001",
                "private_name": "doc-0001.pdf",
                "content_sha256": "sha256:pending",
            }
        ]
    )
    with pytest.raises(ValueError, match="startup_source_ref_content_sha256_invalid"):
        graph.invoke(invalid_hash, _config("invalid-source-hash"))

    duplicate_hash = _case_input(
        source_refs=[
            {
                "document_id": "doc-0001",
                "private_name": "doc-0001.pdf",
                "content_sha256": "1" * 64,
            },
            {
                "document_id": "doc-0002",
                "private_name": "doc-0002.docx",
                "content_sha256": "1" * 64,
            },
        ]
    )
    with pytest.raises(ValueError, match="startup_source_ref_duplicate"):
        graph.invoke(duplicate_hash, _config("duplicate-source-hash"))


def test_startup_graph_rejects_raw_source_paths_before_checkpoint() -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("raw-source-path"), deps)
    payload = _case_input()
    payload["sources"] = [r"C:\private\pitch.pdf"]

    with pytest.raises(ValueError, match="startup_raw_sources_forbidden"):
        graph.invoke(payload, _config("raw-source-path"))

    invalid_revision = _case_input()
    invalid_revision["data_revision"] = True
    with pytest.raises(ValueError, match="startup_data_revision_invalid"):
        graph.invoke(invalid_revision, _config("invalid-data-revision"))


def test_denied_gate2_runs_local_branch_and_never_calls_external_provider(
) -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("denied"), deps)
    config = _config("denied-case")

    graph.invoke(_case_input(), config)
    gate3 = graph.invoke(Command(resume=_approval("denied")), config)
    assert gate3["status"] == "review_required"
    assert gate3["pending_gate"] == "startup_gate3_review"
    gate4 = graph.invoke(Command(resume=_gate3_decision()), config)
    result = graph.invoke(Command(resume=_gate4_decision(result=gate4)), config)

    assert result["status"] == "completed_with_policy_blocks"
    assert result["pending_gate"] is None
    assert result["profile_id"] == result["primary_profile_id"]
    assert result["profile_hash"] == "sha256:primary-profile"
    assert deps.provider.calls == []
    assert deps.profile.calls == ["build_primary"]
    assert result["finding_ids"] == ["local-finding-risk-gap"]
    blocked_nodes = {
        item["node_name"]: item
        for item in result["node_results"]
        if item["status"] == "blocked"
    }
    assert set(blocked_nodes) >= {"financial_analysis", "risk_analysis", "market_analysis"}
    assert all(
        item["errors"] == ["blocked_by_policy:startup_disclosure"]
        for item in blocked_nodes.values()
    )


def test_each_executed_node_emits_sanitized_audit_event_and_llm_span(
) -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("audit"), deps)
    config = _config("audit-trace-case")

    graph.invoke(_case_input(raw_payload=RAW_SENTINEL), config)
    graph.invoke(Command(resume=_approval("approved")), config)
    result = graph.invoke(Command(resume=_gate3_decision()), config)

    executed = [item["node_name"] for item in result["node_results"]]
    assert deps.audit.events == executed
    assert len(deps.audit.events) == len(set(deps.audit.event_ids))
    dumped_audit = deps.audit.serialized()
    dumped_spans = deps.tracer.serialized()
    assert RAW_SENTINEL not in dumped_audit
    assert RAW_SENTINEL not in dumped_spans
    llm_spans = [span for span in deps.tracer.spans if span["node_name"].endswith("_analysis")]
    assert llm_spans
    assert all(set(span) <= deps.tracer.allowed_keys for span in llm_spans)
    assert all(span["status"] in {"success", "blocked"} for span in llm_spans)


def test_runtime_node_trace_events_include_checkpoint_identity_attempt_latency_and_known_tool(
) -> None:
    deps = StartupWorkflowFixture()
    deps.provider.trace_tool_name = "startup_provider"
    graph = _graph(_test_dir("runtime-trace-contract"), deps)
    config = _config("runtime-trace-contract")

    graph.invoke(_case_input(raw_payload=RAW_SENTINEL), config)
    graph.invoke(Command(resume=_approval("approved")), config)
    graph.invoke(Command(resume=_gate3_decision()), config)

    financial_audit = _single_payload(deps.audit.payloads, "financial_analysis")
    financial_span = _single_payload(deps.tracer.spans, "financial_analysis")
    for payload in (financial_audit, financial_span):
        assert payload["case_id"] == CASE_ID
        assert payload["run_id"] == RUN_ID
        assert payload["correlation_id"] == CORRELATION_ID
        assert payload["attempt"] == 1
        assert payload["retry_count"] == 0
        assert isinstance(payload["latency_ms"], int | float)
        assert payload["latency_ms"] >= 0
        assert payload["checkpoint_id"].startswith("startup-financial_analysis-")
        assert len(payload["checkpoint_hash"]) == 64
        assert payload["tool"] == "startup_provider"
        assert RAW_SENTINEL not in repr(payload)
        assert "source_refs" not in payload


def test_reflexion_stops_by_round_two_when_contradiction_remains_unresolved(
) -> None:
    deps = StartupWorkflowFixture(unresolved_reflexion=True)
    graph = _graph(_test_dir("reflexion"), deps)
    config = _config("reflexion-case")

    graph.invoke(_case_input(), config)
    graph.invoke(Command(resume=_approval("approved")), config)
    result = graph.invoke(Command(resume=_gate3_decision()), config)

    assert result["reflexion_round"] == 2
    assert result["contradiction_ids"] == [CONTRADICTION_ID]
    assert deps.reflexion.critic_calls == [1, 2]
    assert deps.reflexion.arbiter_calls == [1, 2]


def test_reflexion_binds_case_and_selected_findings_to_critic_and_arbiter() -> None:
    deps = StartupWorkflowFixture(unresolved_reflexion=True)
    graph = _graph(_test_dir("reflexion-binding"), deps)
    config = _config("reflexion-binding-case")

    graph.invoke(_case_input(), config)
    graph.invoke(Command(resume=_approval("approved")), config)
    gate4 = graph.invoke(Command(resume=_gate3_decision()), config)
    result = graph.invoke(Command(resume=_gate4_decision(result=gate4)), config)

    assert result["arbiter_status"] == "unresolved"
    assert result["critic_issue_codes"] == ["metric_conflict"]
    assert deps.reflexion.payloads == [
        {
            "case_id": CASE_ID,
            "round_number": 1,
            "finding_ids": ["finding-financial", FINDING_ID, "finding-market"],
            "contradiction_ids": [],
        },
        {
            "case_id": CASE_ID,
            "round_number": 2,
            "finding_ids": ["finding-financial", FINDING_ID, "finding-market"],
            "contradiction_ids": [CONTRADICTION_ID],
        },
    ]


def test_reflexion_exposes_separate_critic_and_arbiter_nodes_in_runtime_trace() -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("reflexion-visible-roles"), deps)
    config = _config("reflexion-visible-roles")

    graph.invoke(_case_input(), config)
    gate3 = graph.invoke(Command(resume=_approval("approved")), config)

    executed = [item["node_name"] for item in gate3["node_results"]]
    assert "critic" in executed
    assert "arbiter" in executed
    assert "reflexion" not in executed
    assert executed.index("critic") > executed.index("gtm")
    assert executed.index("arbiter") > executed.index("critic")

    critic_span = _single_payload(deps.tracer.spans, "critic")
    arbiter_span = _single_payload(deps.tracer.spans, "arbiter")
    assert critic_span["agent_role"] == "critic"
    assert arbiter_span["agent_role"] == "arbiter"
    assert critic_span["tool"] == "startup_critic"
    assert arbiter_span["tool"] == "startup_arbiter"


def test_reflexion_limits_critic_and_arbiter_to_two_trace_rounds() -> None:
    deps = StartupWorkflowFixture(unresolved_reflexion=True)
    graph = _graph(_test_dir("reflexion-visible-round-limit"), deps)
    config = _config("reflexion-visible-round-limit")

    graph.invoke(_case_input(), config)
    gate3 = graph.invoke(Command(resume=_approval("approved")), config)

    assert gate3["reflexion_round"] == 2
    assert [span["node_name"] for span in deps.tracer.spans].count("critic") == 2
    assert [span["node_name"] for span in deps.tracer.spans].count("arbiter") == 2
    assert deps.reflexion.calls == []


def test_report_generation_pauses_at_gate4_freeze_before_final_completion() -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("gate4-freeze-pause"), deps)
    config = _config("gate4-freeze-pause")

    paused = _run_to_gate4_pause(graph, config)

    assert paused["status"] == "approval_required"
    assert paused["pending_gate"] == "startup_gate4_freeze"
    assert paused["report_snapshot_id"] == REPORT_ID
    assert paused["report_snapshot_hash"] == "sha256:workflow-report"
    assert paused["report_snapshot_revision"] == 7
    assert len(deps.report.payloads) == 1


def test_gate4_resume_completes_same_thread_without_rerunning_prior_nodes() -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("gate4-resume-same-thread"), deps)
    config = _config("gate4-resume-same-thread")

    _run_to_gate4_pause(graph, config)
    calls_before_resume = {
        "ingest": list(deps.data_room.calls),
        "parse": list(deps.parser.calls),
        "profile": list(deps.profile.calls),
        "provider": list(deps.provider.calls),
        "reflexion": list(deps.reflexion.calls),
        "report_builds": list(deps.report.payloads),
    }
    completed = graph.invoke(Command(resume=_gate4_decision()), config)

    assert completed["status"] == "completed"
    assert completed["pending_gate"] is None
    assert completed["report_snapshot_id"] == REPORT_ID
    assert completed["report_snapshot_hash"] == "sha256:workflow-report"
    assert completed["report_snapshot_revision"] == 7
    assert deps.report.freeze_payloads == [
        {
            "case_id": CASE_ID,
            "action": "approved",
            "actor": "founder",
            "report_snapshot_id": REPORT_ID,
            "report_snapshot_hash": "sha256:workflow-report",
            "report_snapshot_revision": 7,
        }
    ]
    assert deps.data_room.calls == calls_before_resume["ingest"]
    assert deps.parser.calls == calls_before_resume["parse"]
    assert deps.profile.calls == calls_before_resume["profile"]
    assert deps.provider.calls == calls_before_resume["provider"]
    assert deps.reflexion.calls == calls_before_resume["reflexion"]
    assert deps.report.payloads == calls_before_resume["report_builds"]


def test_gate4_pause_survives_graph_recompile_between_resumes() -> None:
    deps = StartupWorkflowFixture()
    checkpoint_path = _test_dir("gate4-recompiled-resume") / "checkpoints.sqlite3"
    config = _config("gate4-recompiled-resume")

    with _sqlite_saver(checkpoint_path) as saver:
        graph = build_startup_graph(deps, checkpointer=saver)
        graph.invoke(_case_input(), config)
    with _sqlite_saver(checkpoint_path) as saver:
        graph = build_startup_graph(deps, checkpointer=saver)
        gate3 = graph.invoke(Command(resume=_approval("approved")), config)
    assert gate3["status"] == "review_required"
    assert gate3["pending_gate"] == "startup_gate3_review"

    with _sqlite_saver(checkpoint_path) as saver:
        graph = build_startup_graph(deps, checkpointer=saver)
        paused = graph.invoke(Command(resume=_gate3_decision()), config)

    assert paused["status"] == "approval_required"
    assert paused["pending_gate"] == "startup_gate4_freeze"
    assert paused["error_code"] is None
    assert deps.report.freeze_payloads == []

    with _sqlite_saver(checkpoint_path) as saver:
        graph = build_startup_graph(deps, checkpointer=saver)
        completed = graph.invoke(Command(resume=_gate4_decision(result=paused)), config)

    assert completed["status"] == "completed"
    assert completed["pending_gate"] is None
    assert completed["gate4_decision"] == "approved"
    assert len(deps.report.freeze_payloads) == 1


def test_claims_node_persists_normalized_contradiction_signal_for_restart() -> None:
    class ContradictingClaims:
        def extract(self, *, case_id: str, evidence_fact_ids: list[str]) -> dict[str, Any]:
            del case_id, evidence_fact_ids
            return {
                "startup_claim_ids": ["claim-unit-economics"],
                "contradiction_ids": [UUID(CONTRADICTION_ID)],
                "claim_status_by_id": {"claim-unit-economics": "contradicted"},
                "claim_matrix_summary": [],
            }

    durable_store = DurableWorkflowStore()
    deps = StartupWorkflowFixture(runtime_store=durable_store)
    deps.claims = ContradictingClaims()
    graph = _graph(_test_dir("claims-runtime-contradiction"), deps)

    paused = graph.invoke(_case_input(), _config("claims-runtime-contradiction"))

    assert paused["contradiction_ids"] == [CONTRADICTION_ID]
    restarted_runtime = durable_store.load(CASE_ID)
    assert restarted_runtime["contradiction_ids"] == [CONTRADICTION_ID]
    assert restarted_runtime["has_contradictions"] is True
    assert RAW_SENTINEL not in repr(restarted_runtime)


def test_gate3_exclusion_invalidates_dependent_metric_finding_contradiction_and_report(
) -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("gate3"), deps)
    config = _config("gate3-case")

    graph.invoke(_case_input(), config)
    gate3 = graph.invoke(Command(resume=_approval("approved")), config)
    assert gate3["status"] == "review_required"
    assert gate3["pending_gate"] == "startup_gate3_review"
    result = graph.invoke(
        Command(resume=_gate3_decision(exclusions=[{"evidence_fact_id": REVENUE_FACT_ID}])),
        config,
    )

    assert result["calculation_ids"] == []
    assert result["finding_ids"] == ["finding-market"]
    assert result["contradiction_ids"] == []
    assert result["report_snapshot_id"] == "report-recomputed-without-excluded"
    assert result["invalidated_ids"] == [
        REVENUE_FACT_ID,
        CALCULATION_ID,
        "finding-financial",
        FINDING_ID,
        CONTRADICTION_ID,
        REPORT_ID,
        PRODUCT_VALIDATION_SNAPSHOT_ID,
        READINESS_SNAPSHOT_ID,
        GTM_SNAPSHOT_ID,
    ]
    assert deps.metrics.calls == ["calculate", "calculate"]
    assert deps.provider.calls == [
        "financial_analysis",
        "risk_analysis",
        "market_analysis",
        "financial_analysis",
        "risk_analysis",
    ]
    recompute_call = deps.provider.payloads[-1]
    assert recompute_call["case_id"] == CASE_ID
    assert recompute_call["remaining_evidence_fact_ids"] == [COGS_FACT_ID]
    assert FINDING_ID in recompute_call["invalidated_ids"]
    report_call = deps.report.payloads[-1]
    assert report_call["evidence_fact_ids"] == [COGS_FACT_ID]
    assert report_call["calculation_ids"] == []
    assert report_call["finding_ids"] == ["finding-market"]
    assert report_call["contradiction_ids"] == []


def test_financial_risk_and_market_findings_are_merged_without_overwrite() -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("finding-merge"), deps)
    config = _config("finding-merge-case")

    graph.invoke(_case_input(), config)
    graph.invoke(Command(resume=_approval("approved")), config)
    result = graph.invoke(Command(resume=_gate3_decision()), config)

    assert result["finding_ids"] == [
        "finding-financial",
        FINDING_ID,
        "finding-market",
    ]


def test_stale_or_restricted_approval_blocks_provider_with_real_disclosure_semantics() -> None:
    deps = StartupWorkflowFixture(restricted_snapshot=True)
    graph = _graph(_test_dir("restricted-approval"), deps)
    config = _config("restricted-approval-case")

    graph.invoke(_case_input(), config)
    graph.invoke(Command(resume=_approval("approved")), config)
    gate4 = graph.invoke(Command(resume=_gate3_decision()), config)
    result = graph.invoke(Command(resume=_gate4_decision(result=gate4)), config)

    assert deps.provider.calls == []
    assert result["status"] == "completed_with_policy_blocks"


def test_explicit_disclosure_denial_is_local_branch_not_failure() -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("explicit-denial"), deps)
    config = _config("explicit-denial")

    graph.invoke(_case_input(), config)
    graph.invoke(Command(resume=_approval("denied")), config)
    gate4 = graph.invoke(Command(resume=_gate3_decision()), config)
    result = graph.invoke(Command(resume=_gate4_decision(result=gate4)), config)

    assert result["status"] == "completed_with_policy_blocks"
    assert result["error_code"] is None


def test_invalid_disclosure_action_is_typed_failure_not_denial() -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("invalid-disclosure-action"), deps)
    config = _config("invalid-disclosure-action")

    graph.invoke(_case_input(), config)
    result = graph.invoke(Command(resume=_approval("invalid")), config)

    assert result["status"] == "failed"
    assert result["error_code"] == "startup_disclosure_invalid_decision"
    assert deps.provider.calls == []


def test_disclosure_repository_failure_is_typed_failure_not_denial() -> None:
    deps = StartupWorkflowFixture()
    deps.disclosure.fail_with = ValueError("repository unavailable")
    graph = _graph(_test_dir("disclosure-repository-failure"), deps)
    config = _config("disclosure-repository-failure")

    graph.invoke(_case_input(), config)
    result = graph.invoke(Command(resume=_approval("approved")), config)

    assert result["status"] == "failed"
    assert result["error_code"] == "startup_disclosure_decision_failed"
    assert deps.provider.calls == []


def test_disclosure_dependency_uses_real_service_api_shape() -> None:
    deps = StartupWorkflowFixture()
    deps.disclosure = create_autospec(StartupDisclosureService, instance=True)
    snapshot = deps.privacy.snapshot
    approval = StartupDisclosureApproval.from_decision(
        snapshot,
        action="approved",
        actor="founder",
        destination="openai.responses",
        decided_at=deps.clock(),
    )
    deps.disclosure.build_preview.return_value = object()
    deps.disclosure.decide.return_value = approval
    deps.disclosure.resolve_scope.return_value = object()
    graph = _graph(_test_dir("real-disclosure-api"), deps)
    config = _config("real-disclosure-api")

    graph.invoke(_case_input(), config)
    graph.invoke(Command(resume=_approval("approved")), config)
    result = graph.invoke(Command(resume=_gate3_decision()), config)

    assert result["approval_ids"] == [str(approval.id)]
    deps.disclosure.build_preview.assert_called_once_with(snapshot)
    deps.disclosure.decide.assert_called_once()
    deps.disclosure.resolve_scope.assert_called_once_with(snapshot)


def test_runtime_store_persists_only_json_safe_refs_without_domain_objects() -> None:
    path = _test_dir("json-runtime") / "runtime.json"
    store = JsonFileStartupWorkflowRuntimeStore(path)
    deps = StartupWorkflowFixture(runtime_store=store)
    graph = _graph(_test_dir("json-runtime"), deps)

    graph.invoke(_case_input(), _config("json-runtime"))

    payload = path.read_text(encoding="utf-8")
    assert "disclosure_snapshot" in payload
    assert "ClassifiedDisclosureSnapshot" not in payload
    assert "DisclosureScope" not in payload
    reloaded = JsonFileStartupWorkflowRuntimeStore(path).load(CASE_ID)
    assert str(reloaded["disclosure_snapshot"].case_id) == CASE_ID


def test_workflow_adapters_match_real_metric_audit_and_tracer_contracts() -> None:
    metric_service = create_autospec(StartupMetricService, instance=True)
    metric_service.calculate_for_case.return_value = MetricCalculationProbe(CALCULATION_ID)
    metric_adapter = StartupMetricWorkflowAdapter(metric_service)
    calculation = metric_adapter.calculate(
        case_id=CASE_ID,
        evidence_fact_ids=[REVENUE_FACT_ID, COGS_FACT_ID],
    )
    assert calculation["calculation_ids"] == [CALCULATION_ID]
    assert calculation["metric_diagnostics"] == [
        {
            "metric_name": "gross_margin",
            "status": "unknown",
            "warnings": [],
            "input_evidence_ids": [REVENUE_FACT_ID, COGS_FACT_ID],
            "calculation_id": CALCULATION_ID,
        }
    ]
    metric_service.calculate_for_case.assert_called()

    audit_spool = create_autospec(AuditSpool, instance=True)
    audit = AuditSpoolNodeAudit(audit_spool)
    audit.record(
        "metrics",
        NodeResultProbe(),
        {"case_id": CASE_ID, "run_id": RUN_ID, "correlation_id": CORRELATION_ID},
        duration_ms=3,
        checkpoint_id="startup-metrics-000000000001",
        checkpoint_hash="a" * 64,
        tool="python_metrics",
    )
    audit_spool.append.assert_called_once()
    real_spool = JsonlAuditSpool(_test_dir("real-runtime-audit-spool"), max_mb=1)
    AuditSpoolNodeAudit(real_spool).record(
        "financial_analysis",
        NodeResultProbe(),
        {"case_id": CASE_ID, "run_id": RUN_ID, "correlation_id": CORRELATION_ID},
        duration_ms=5,
        checkpoint_id="startup-financial_analysis-000000000001",
        checkpoint_hash="b" * 64,
        tool="startup_provider",
    )
    event = real_spool.read_bounded(max_events=1)[0]
    assert event.attributes["latency_ms"] == 5
    assert event.attributes["checkpoint_id"] == "startup-financial_analysis-000000000001"
    assert event.attributes["checkpoint_hash"] == "b" * 64
    assert event.attributes["tool"] == "startup_provider"

    metric_contract = FakeMetricContract()
    tracer = MetricContractNodeTracer(metric_contract)
    tracer.record(
        node_name="metrics",
        status="success",
        duration_ms=3,
        schema_version="startup_node_span@1",
        fallback_used=False,
        case_id=CASE_ID,
        run_id=RUN_ID,
        correlation_id=CORRELATION_ID,
        retry_count=0,
    )
    assert [item[0] for item in metric_contract.calls] == [
        "node.outcome.count",
        "node.duration.ms",
    ]


def test_workflow_adapters_cover_evidence_claims_and_report_contracts() -> None:
    evidence_repo = RepositoryProbe([IdProbe(REVENUE_FACT_ID), IdProbe(COGS_FACT_ID)])
    evidence = StartupEvidenceRepositoryAdapter(evidence_repo)
    assert evidence.extract(case_id=CASE_ID, parsed_artifact_ids=["parsed"]) == {
        "evidence_fact_ids": [REVENUE_FACT_ID, COGS_FACT_ID],
    }
    assert evidence_repo.calls == [UUID(CASE_ID)]

    claim_repo = RepositoryProbe([IdProbe("claim-1"), IdProbe("claim-2")])
    claims = StartupClaimRepositoryAdapter(claim_repo)
    assert claims.extract(case_id=CASE_ID, evidence_fact_ids=[REVENUE_FACT_ID]) == {
        "startup_claim_ids": ["claim-1", "claim-2"]
    }

    root = _test_dir("report-adapter")
    repos = _local_repositories(root / "report.sqlite3")
    case_id = UUID(CASE_ID)
    artifact_id = uuid4()
    repos["case"].add(_case(case_id))
    repos["artifact"].add(_artifact(case_id, artifact_id))
    repos["evidence"].add(_fact(UUID(REVENUE_FACT_ID), artifact_id, "revenue"))
    report = _startup_report_adapter(repos, root)
    report_result = report.build(
        case_id=CASE_ID,
        **_profile_refs(repos, case_id),
        startup_claim_ids=[],
        evidence_fact_ids=[REVENUE_FACT_ID],
        calculation_ids=[],
        finding_ids=[],
        contradiction_ids=[],
    )
    snapshot = repos["report"].get_snapshot(UUID(str(report_result["report_snapshot_id"])))
    assert report_result == {
        "report_snapshot_id": str(snapshot.id),
        "report_snapshot_hash": snapshot.report_hash,
        "report_snapshot_revision": snapshot.data_revision,
    }
    assert "task10_boundary" not in snapshot.sections
    assert report.current_snapshot(CASE_ID).snapshot_hash == snapshot.report_hash


def test_report_adapter_binds_stable_checkpoint_ids_from_latest_case_run() -> None:
    # Catches: passing trace_ids=() (or random audit event UUIDs) into the report snapshot.
    root = _test_dir("report-trace-lineage")
    repos = _local_repositories(root / "report.sqlite3")
    case_id = UUID(CASE_ID)
    artifact_id = uuid4()
    repos["case"].add(_case(case_id))
    repos["artifact"].add(_artifact(case_id, artifact_id))
    repos["evidence"].add(_fact(UUID(REVENUE_FACT_ID), artifact_id, "revenue"))
    audit_spool = JsonlAuditSpool(root / "audit", max_mb=1)
    audit = AuditSpoolNodeAudit(audit_spool)
    audit.record(
        "metrics",
        NodeResultProbe(),
        {"case_id": CASE_ID, "run_id": "startup-previous-run", "correlation_id": CASE_ID},
        checkpoint_id="startup-metrics-111111111111",
        checkpoint_hash="1" * 64,
    )
    audit.record(
        "risk_analysis",
        NodeResultProbe(),
        {"case_id": CASE_ID, "run_id": RUN_ID, "correlation_id": CORRELATION_ID},
        checkpoint_id="startup-risk_analysis-333333333333",
        checkpoint_hash="3" * 64,
    )
    audit.record(
        "financial_analysis",
        NodeResultProbe(),
        {"case_id": CASE_ID, "run_id": RUN_ID, "correlation_id": CORRELATION_ID},
        checkpoint_id="startup-financial_analysis-222222222222",
        checkpoint_hash="2" * 64,
    )
    audit.record(
        "report",
        NodeResultProbe(),
        {"case_id": CASE_ID, "run_id": RUN_ID, "correlation_id": CORRELATION_ID},
        checkpoint_id="startup-report-444444444444",
        checkpoint_hash="4" * 64,
    )
    report = _startup_report_adapter(repos, root, audit_spool=audit_spool)

    first = report.build(
        case_id=CASE_ID,
        **_profile_refs(repos, case_id),
        startup_claim_ids=[],
        evidence_fact_ids=[REVENUE_FACT_ID],
        calculation_ids=[],
        finding_ids=[],
        contradiction_ids=[],
    )
    first_snapshot = repos["report"].get_snapshot(UUID(str(first["report_snapshot_id"])))
    second = report.build(
        case_id=CASE_ID,
        **_profile_refs(repos, case_id),
        startup_claim_ids=[],
        evidence_fact_ids=[REVENUE_FACT_ID],
        calculation_ids=[],
        finding_ids=[],
        contradiction_ids=[],
    )

    assert first_snapshot.trace_ids == (
        "startup-financial_analysis-222222222222",
        "startup-risk_analysis-333333333333",
    )
    assert second == first
    assert first_snapshot.report_hash == str(first["report_snapshot_hash"])
    assert "startup-metrics-111111111111" not in first_snapshot.trace_ids
    assert RAW_SENTINEL not in repr(first_snapshot.trace_ids)


def test_report_adapter_fails_closed_without_correlatable_checkpoint_trace() -> None:
    # Catches: treating a random audit event UUID (or an empty tuple) as report lineage.
    root = _test_dir("report-trace-lineage-missing")
    repos = _local_repositories(root / "report.sqlite3")
    case_id = UUID(CASE_ID)
    artifact_id = uuid4()
    repos["case"].add(_case(case_id))
    repos["artifact"].add(_artifact(case_id, artifact_id))
    repos["evidence"].add(_fact(UUID(REVENUE_FACT_ID), artifact_id, "revenue"))
    audit_spool = JsonlAuditSpool(root / "audit", max_mb=1)
    AuditSpoolNodeAudit(audit_spool).record(
        "metrics",
        NodeResultProbe(),
        {"case_id": CASE_ID, "run_id": RUN_ID, "correlation_id": CORRELATION_ID},
    )
    report = _startup_report_adapter(repos, root, audit_spool=audit_spool)

    with pytest.raises(
        StartupReportTraceLineageError,
        match="startup_report_trace_lineage_missing",
    ):
        report.build(
            case_id=CASE_ID,
            **_profile_refs(repos, case_id),
            startup_claim_ids=[],
            evidence_fact_ids=[REVENUE_FACT_ID],
            calculation_ids=[],
            finding_ids=[],
            contradiction_ids=[],
        )


def test_report_port_reads_do_not_create_snapshot_before_workflow_build() -> None:
    root = _test_dir("report-read-before-build")
    repos = _local_repositories(root / "report.sqlite3")
    repos["case"].add(_case(UUID(CASE_ID)))
    report = _startup_report_adapter(repos, root)

    try:
        report.current_snapshot(CASE_ID)
    except KeyError as exc:
        assert str(exc).strip("'") == f"report_snapshot_not_found:{CASE_ID}"
    else:
        raise AssertionError("report reads must not create a startup snapshot")

    assert repos["report"].list_for_case(UUID(CASE_ID)) == []


def test_report_port_selects_current_revision_snapshot_deterministically() -> None:
    root = _test_dir("report-current-revision")
    repos = _local_repositories(root / "report.sqlite3")
    case_id = UUID(CASE_ID)
    repos["case"].add(_case(case_id))
    current = _startup_report_snapshot(
        UUID("50000000-0000-0000-0000-000000000902"),
        case_id,
        revision=2,
        report_hash="sha256:current",
    )
    stale = _startup_report_snapshot(
        UUID("50000000-0000-0000-0000-000000000999"),
        case_id,
        revision=1,
        report_hash="sha256:stale",
    )
    repos["report"].add_snapshot(current)
    repos["report"].add_snapshot(stale)
    report = _startup_report_adapter(
        repos,
        root,
        current_data_revision=lambda _case_id: 2,
    )

    assert report.current_snapshot(CASE_ID) == CanonicalReportSnapshot(
        snapshot_id=str(current.id),
        snapshot_hash="sha256:current",
        snapshot_revision=2,
    )


def test_report_port_selects_runtime_bound_current_revision_snapshot() -> None:
    root = _test_dir("report-runtime-bound-current-revision")
    repos = _local_repositories(root / "report.sqlite3")
    case_id = UUID(CASE_ID)
    repos["case"].add(_case(case_id))
    selected = _startup_report_snapshot(
        UUID("50000000-0000-0000-0000-000000000902"),
        case_id,
        revision=2,
        report_hash="sha256:selected",
    )
    same_revision_lexically_later = _startup_report_snapshot(
        UUID("50000000-0000-0000-0000-000000000999"),
        case_id,
        revision=2,
        report_hash="sha256:older",
    )
    repos["report"].add_snapshot(selected)
    repos["report"].add_snapshot(same_revision_lexically_later)
    workflow_store = DurableWorkflowStore()
    workflow_store.save(
        CASE_ID,
        {
            "canonical_report_snapshot_id": str(selected.id),
            "canonical_report_snapshot_hash": selected.report_hash,
            "canonical_report_snapshot_revision": selected.data_revision,
        },
    )
    report = _startup_report_adapter(
        repos,
        root,
        current_data_revision=lambda _case_id: 2,
        workflow_store=workflow_store,
    )

    assert report.current_snapshot(CASE_ID) == CanonicalReportSnapshot(
        snapshot_id=str(selected.id),
        snapshot_hash=selected.report_hash,
        snapshot_revision=2,
    )
    assert report.decide_gate4(
        CASE_ID,
        decision="approved",
        snapshot_hash=selected.report_hash,
        snapshot_revision=2,
    ) == CanonicalReportSnapshot(
        snapshot_id=str(selected.id),
        snapshot_hash=selected.report_hash,
        snapshot_revision=2,
    )


def test_report_port_gate4_decision_freezes_runtime_bound_current_snapshot() -> None:
    root = _test_dir("report-runtime-bound-gate4-freeze")
    repos = _local_repositories(root / "report.sqlite3")
    case_id = UUID(CASE_ID)
    repos["case"].add(_case(case_id))
    selected = _startup_report_snapshot(
        UUID("50000000-0000-0000-0000-000000000902"),
        case_id,
        revision=2,
        report_hash="sha256:selected",
    )
    same_revision_lexically_later = _startup_report_snapshot(
        UUID("50000000-0000-0000-0000-000000000999"),
        case_id,
        revision=2,
        report_hash="sha256:older",
    )
    repos["report"].add_snapshot(selected)
    repos["report"].add_snapshot(same_revision_lexically_later)
    workflow_store = DurableWorkflowStore()
    workflow_store.save(
        CASE_ID,
        {
            "canonical_report_snapshot_id": str(selected.id),
            "canonical_report_snapshot_hash": selected.report_hash,
            "canonical_report_snapshot_revision": selected.data_revision,
        },
    )
    report = _startup_report_adapter(
        repos,
        root,
        current_data_revision=lambda _case_id: 2,
        workflow_store=workflow_store,
    )

    decision = report.decide_gate4(
        CASE_ID,
        decision="approved",
        snapshot_hash=selected.report_hash,
        snapshot_revision=selected.data_revision,
        reason="owner accepted bound report",
    )

    assert decision == CanonicalReportSnapshot(
        snapshot_id=str(selected.id),
        snapshot_hash=selected.report_hash,
        snapshot_revision=2,
    )
    approvals = repos["approval"].list_for_case(case_id)
    assert len(approvals) == 1
    assert approvals[0].subject_id == selected.id
    assert approvals[0].subject_hash == selected.report_hash
    assert report.freeze_status(CASE_ID) == "approved"
    assert report.pdf_status(CASE_ID) == "ready"


@pytest.mark.parametrize(
    ("runtime_update", "error_code"),
    [
        (
            {"canonical_report_snapshot_id": "50000000-0000-0000-0000-000000000902"},
            "startup_report_canonical_identity_incomplete",
        ),
        (
            {
                "canonical_report_snapshot_id": "50000000-0000-0000-0000-000000000902",
                "canonical_report_snapshot_hash": "sha256:wrong",
                "canonical_report_snapshot_revision": 2,
            },
            "startup_report_canonical_hash_mismatch",
        ),
        (
            {
                "canonical_report_snapshot_id": "50000000-0000-0000-0000-000000000902",
                "canonical_report_snapshot_hash": "sha256:selected",
                "canonical_report_snapshot_revision": 1,
            },
            "startup_report_canonical_revision_mismatch",
        ),
    ],
)
def test_report_port_runtime_bound_snapshot_mismatch_fails_closed(
    runtime_update: dict[str, object],
    error_code: str,
) -> None:
    from due_diligence_agent.application.services.startup_report_service import (
        StartupReportProfileBindingError,
    )

    root = _test_dir(f"report-runtime-bound-fail-closed-{uuid4().hex}")
    repos = _local_repositories(root / "report.sqlite3")
    case_id = UUID(CASE_ID)
    repos["case"].add(_case(case_id))
    selected = _startup_report_snapshot(
        UUID("50000000-0000-0000-0000-000000000902"),
        case_id,
        revision=2,
        report_hash="sha256:selected",
    )
    fallback_candidate = _startup_report_snapshot(
        UUID("50000000-0000-0000-0000-000000000999"),
        case_id,
        revision=2,
        report_hash="sha256:fallback",
    )
    repos["report"].add_snapshot(selected)
    repos["report"].add_snapshot(fallback_candidate)
    workflow_store = DurableWorkflowStore()
    workflow_store.save(CASE_ID, runtime_update)
    report = _startup_report_adapter(
        repos,
        root,
        current_data_revision=lambda _case_id: 2,
        workflow_store=workflow_store,
    )

    with pytest.raises(StartupReportProfileBindingError) as exc_info:
        report.current_snapshot(CASE_ID)

    assert str(exc_info.value) == error_code


def test_report_build_uses_exact_selected_lineage_after_gate3_exclusion() -> None:
    selected_root = _test_dir("report-selected-lineage-baseline")
    selected_repos = _local_repositories(selected_root / "report.sqlite3")
    case_id = UUID(CASE_ID)
    selected_ids = _persist_report_lineage(selected_repos, case_id, include_excluded=False)
    selected_report = _startup_report_adapter(selected_repos, selected_root)
    selected_result = selected_report.build(case_id=CASE_ID, **selected_ids)
    selected_snapshot = selected_repos["report"].get_snapshot(
        UUID(str(selected_result["report_snapshot_id"]))
    )

    mixed_root = _test_dir("report-selected-lineage-mixed")
    mixed_repos = _local_repositories(mixed_root / "report.sqlite3")
    mixed_ids = _persist_report_lineage(mixed_repos, case_id, include_excluded=True)
    mixed_report = _startup_report_adapter(mixed_repos, mixed_root)
    mixed_result = mixed_report.build(case_id=CASE_ID, **selected_ids)
    mixed_snapshot = mixed_repos["report"].get_snapshot(
        UUID(str(mixed_result["report_snapshot_id"]))
    )

    assert mixed_snapshot.report_hash == selected_snapshot.report_hash
    assert mixed_snapshot.sections == selected_snapshot.sections
    assert mixed_result["report_snapshot_hash"] == selected_result["report_snapshot_hash"]

    serialized_sections = repr(mixed_snapshot.sections)
    serialized_sources = repr(mixed_snapshot.source_hashes)
    excluded_ids = set(mixed_ids["startup_claim_ids"]) - set(selected_ids["startup_claim_ids"])
    excluded_ids |= set(mixed_ids["evidence_fact_ids"]) - set(selected_ids["evidence_fact_ids"])
    excluded_ids |= set(mixed_ids["calculation_ids"]) - set(selected_ids["calculation_ids"])
    excluded_ids |= set(mixed_ids["finding_ids"]) - set(selected_ids["finding_ids"])
    excluded_ids |= set(mixed_ids["contradiction_ids"]) - set(selected_ids["contradiction_ids"])
    assert excluded_ids
    assert all(item not in serialized_sections for item in excluded_ids)
    assert all(item not in serialized_sources for item in excluded_ids)


def test_startup_provider_adapter_persists_configured_provider_findings() -> None:
    repos = _local_repositories(_test_dir("provider-persistence") / "provider.sqlite3")
    case_id = UUID(CASE_ID)
    artifact_id = uuid4()
    repos["case"].add(_case(case_id))
    repos["artifact"].add(_artifact(case_id, artifact_id))
    repos["evidence"].add(_fact(UUID(REVENUE_FACT_ID), artifact_id, "revenue"))
    finding = _finding(
        UUID(FINDING_ID),
        case_id,
        (UUID(REVENUE_FACT_ID),),
        (),
    )
    provider = _StartupProviderWorkflowPort(
        provider=ProviderFindingProbe(finding),
        finding_repository=repos["finding"],
    )

    result = provider.analyze(
        case_id=CASE_ID,
        node_name="risk_analysis",
        disclosure_scope={"approval_id": "approved"},
        remaining_evidence_fact_ids=[REVENUE_FACT_ID],
        remaining_calculation_ids=[],
        invalidated_ids=[],
    )

    assert result == {"finding_ids": [FINDING_ID]}
    assert [str(item.id) for item in repos["finding"].list_for_case(case_id)] == [FINDING_ID]


def test_startup_provider_adapter_rejects_unpersisted_raw_finding_ids() -> None:
    repos = _local_repositories(_test_dir("provider-raw-id-rejected") / "provider.sqlite3")
    provider = _StartupProviderWorkflowPort(
        provider=ProviderRawIdProbe(FINDING_ID),
        finding_repository=repos["finding"],
    )

    try:
        provider.analyze(
            case_id=CASE_ID,
            node_name="risk_analysis",
            disclosure_scope={"approval_id": "approved"},
            remaining_evidence_fact_ids=[REVENUE_FACT_ID],
            remaining_calculation_ids=[],
            invalidated_ids=[],
        )
    except RuntimeError as exc:
        assert str(exc) == "startup_provider_unpersisted_finding_id"
    else:
        raise AssertionError("unpersisted provider finding id must fail closed")


def test_lineage_adapter_uses_real_model_relations_not_evidence_metadata() -> None:
    repos = _local_repositories(_test_dir("real-lineage") / "lineage.sqlite3")
    case_id = UUID(CASE_ID)
    artifact_id = uuid4()
    repos["case"].add(_case(case_id))
    repos["artifact"].add(_artifact(case_id, artifact_id))
    revenue = _fact(UUID(REVENUE_FACT_ID), artifact_id, "revenue", metadata={"workflow_nodes": "ignored"})
    cogs = _fact(UUID(COGS_FACT_ID), artifact_id, "cogs")
    repos["evidence"].add(revenue)
    repos["evidence"].add(cogs)
    calculation = _calculation(UUID(CALCULATION_ID), case_id, (revenue.id, cogs.id))
    repos["calculation"].add(calculation)
    finding = _finding(UUID(FINDING_ID), case_id, (revenue.id,), (calculation.id,))
    repos["finding"].add(finding)
    contradiction = _contradiction(UUID(CONTRADICTION_ID), case_id, (revenue.id,), (finding.id,))
    repos["contradiction"].add(contradiction)
    report = _report_snapshot(UUID(REPORT_ID), case_id)
    repos["report"].add_snapshot(report)

    lineage = StartupLineageRepositoryAdapter(repos["review"])
    result = lineage.derive(case_id=CASE_ID, evidence_fact_ids=[REVENUE_FACT_ID, COGS_FACT_ID])

    assert result["dependency_edges"] == {
        REVENUE_FACT_ID: [CALCULATION_ID, FINDING_ID, CONTRADICTION_ID, REPORT_ID],
        COGS_FACT_ID: [CALCULATION_ID, REPORT_ID],
        CALCULATION_ID: [FINDING_ID, REPORT_ID],
        FINDING_ID: [CONTRADICTION_ID, REPORT_ID],
        CONTRADICTION_ID: [REPORT_ID],
    }
    assert result["dependency_node_edges"] == {
        REVENUE_FACT_ID: ["product_validation", "metrics", "gtm"],
        COGS_FACT_ID: ["product_validation", "metrics", "gtm"],
        CALCULATION_ID: ["financial_analysis", "risk_analysis"],
        FINDING_ID: ["gtm", "critic", "arbiter"],
        CONTRADICTION_ID: ["gtm", "report"],
    }


def test_gate3_refreshes_real_lineage_after_repositories_create_dependencies() -> None:
    # Catches: deriving dependency edges only in the evidence node. That is a bug because
    # calculation/finding/contradiction/report rows are created later and must still be
    # invalidated when a founder excludes their root evidence fact at Gate 3.
    root = _test_dir("gate3-real-lineage-refresh")
    repos = _local_repositories(root / "lineage.sqlite3")
    deps = StartupWorkflowFixture(
        runtime_store=SQLiteStartupWorkflowRuntimeStore(root / "runtime.sqlite3")
    )
    deps.data_room = RealLineageDataRoom(repos)
    deps.evidence = StartupEvidenceRepositoryAdapter(repos["evidence"])
    deps.lineage = StartupLineageRepositoryAdapter(repos["review"])
    deps.metrics = RealLineageMetrics(repos)
    deps.readiness = StartupReadinessWorkflowAdapter(
        startup_profile_repository=repos["startup_profile"],
        workflow_store=deps.runtime_store,
    )
    deps.market_research = StartupMarketResearchWorkflowAdapter(
        startup_profile_repository=repos["startup_profile"],
        workflow_store=deps.runtime_store,
        research_port=FrozenStartupMarketResearchAdapter.from_fixture_dir(
            Path("tests/fixtures/startup_market_research_v1")
        ),
    )
    deps.product_validation = StartupProductValidationWorkflowAdapter(
        startup_profile_repository=repos["startup_profile"],
        workflow_store=deps.runtime_store,
    )
    deps.gtm = StartupGtmWorkflowAdapter(
        startup_profile_repository=repos["startup_profile"],
        workflow_store=deps.runtime_store,
    )
    deps.provider = RealLineageProvider(repos)
    deps.profile = PersistedProfilePort(repos)
    deps.report = _startup_report_adapter(repos, root, workflow_store=deps.runtime_store)
    graph = _graph(root, deps)
    config = _config("gate3-real-lineage-refresh")

    graph.invoke(_case_input(), config)
    review = graph.invoke(Command(resume=_approval("approved")), config)
    readiness_snapshot_id = str(review["readiness_snapshot_id"])
    product_validation_snapshot_id = str(review["product_validation_snapshot_id"])
    gtm_snapshot_id = str(review["gtm_snapshot_id"])
    result = graph.invoke(
        Command(resume=_gate3_decision(exclusions=[{"evidence_fact_id": REVENUE_FACT_ID}])),
        config,
    )
    result = graph.invoke(Command(resume=_gate4_decision(result=result)), config)

    assert result["status"] == "completed"
    assert result["calculation_ids"] == []
    assert result["finding_ids"] == []
    assert result["contradiction_ids"] == []
    report_snapshot = repos["report"].get_snapshot(UUID(str(result["report_snapshot_id"])))
    assert str(result["gtm_snapshot_id"]) in str(
        report_snapshot.sections["methodology"]
    )
    assert result["invalidated_ids"] == [
        REVENUE_FACT_ID,
        CALCULATION_ID,
        FINDING_ID,
        CONTRADICTION_ID,
        REPORT_ID,
        product_validation_snapshot_id,
        readiness_snapshot_id,
        gtm_snapshot_id,
    ]


def test_sqlite_runtime_store_two_instances_merge_concurrent_json_safe_writes() -> None:
    path = _test_dir("sqlite-runtime") / "runtime.sqlite3"
    first = SQLiteStartupWorkflowRuntimeStore(path)
    second = SQLiteStartupWorkflowRuntimeStore(path)

    first.save(CASE_ID, {"alpha": ["one"], "snapshot": {"id": "safe-ref"}})
    second.save(CASE_ID, {"beta": {"two": 2}})

    assert first.load(CASE_ID) == {
        "alpha": ["one"],
        "snapshot": {"id": "safe-ref"},
        "beta": {"two": 2},
    }


def test_startup_bootstrap_composer_builds_offline_service_to_safe_gate() -> None:
    root = _test_dir("startup-composer")
    source = root / "pitch.pdf"
    source.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")
    service = build_startup_analysis_composer(root)

    result = service.start(
        _composer_case_input(root, source),
        thread_id="startup-composer",
    )

    assert result["status"] == "approval_required"
    assert result["pending_gate"] == "startup_disclosure"


def test_startup_analysis_service_reads_sanitized_langgraph_checkpoint_after_restart(
) -> None:
    root = _test_dir("startup-composer-checkpoint-identity")
    source = root / "pitch.pdf"
    source.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")
    thread_id = "startup-composer-checkpoint-identity"
    service = build_startup_analysis_composer(root)

    service.start(_composer_case_input(root, source), thread_id=thread_id)
    checkpoint = service.checkpoint_identity(thread_id=thread_id)
    restarted_checkpoint = build_startup_analysis_composer(root).checkpoint_identity(
        thread_id=thread_id,
    )

    assert checkpoint == restarted_checkpoint
    assert checkpoint is not None
    assert checkpoint["thread_id"] == thread_id
    assert checkpoint["data_revision"] == 1
    assert len(checkpoint["checkpoint_hash"]) == 64
    assert isinstance(checkpoint["checkpoint_id"], str)
    assert len(checkpoint["checkpoint_id"]) >= 6
    assert "startup-" not in checkpoint["checkpoint_id"]
    assert "run_id" not in checkpoint
    assert "source_refs" not in checkpoint


def test_startup_bootstrap_composer_resumes_approved_gate_without_workflow_unexpected(
) -> None:
    root = _test_dir("startup-composer-approved-resume")
    source = root / "pitch.pdf"
    source.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")
    service = build_startup_analysis_composer(root)

    started = service.start(
        _composer_case_input(root, source),
        thread_id="startup-composer-approved-resume",
    )
    assert started["status"] == "approval_required"
    runtime = service._dependencies.workflow_store.load(CASE_ID)  # noqa: SLF001
    document_artifact = runtime["startup_document_intelligence_artifact"]
    assert document_artifact["schema_version"] == "startup_document_intelligence@1"
    assert document_artifact["snapshot"]["snapshot_id"] == started[
        "document_intelligence_snapshot_id"
    ]
    assert document_artifact["snapshot"]["data_revision"] == 1
    assert "private_name" not in repr(document_artifact)
    assert "content_sha256" not in repr(document_artifact)

    result = service.resume(
        _approval("approved"),
        thread_id="startup-composer-approved-resume",
    )

    assert result["error_code"] != "workflow_unexpected"
    assert result["status"] in {"review_required", "completed_with_policy_blocks"}
    runtime = service._dependencies.workflow_store.load(CASE_ID)  # noqa: SLF001
    product_artifact = runtime["startup_product_validation_artifact"]
    assert product_artifact["schema_version"] == "startup_product_validation@1"
    assert product_artifact["snapshot"]["snapshot_id"] == result[
        "product_validation_snapshot_id"
    ]
    assert [item["name"] for item in product_artifact["snapshot"]["dimensions"]] == [
        "problem_clarity",
        "icp_precision",
        "pain_intensity",
        "urgency",
        "willingness_to_pay",
        "existing_customer_behavior",
        "adoption_risk",
        "validation_evidence",
    ]
    assert "pitch.pdf" not in repr(product_artifact)
    gtm_artifact = runtime["startup_gtm_artifact"]
    assert gtm_artifact["schema_version"] == "startup_gtm@1"
    assert gtm_artifact["snapshot"]["snapshot_id"] == result["gtm_snapshot_id"]
    assert [item["name"] for item in gtm_artifact["snapshot"]["dimensions"]] == [
        "audience",
        "geography",
        "channels",
        "offer",
        "market_context",
        "product_proof",
        "adoption_risk",
    ]
    assert [item["horizon"] for item in gtm_artifact["snapshot"]["launch_plan"]] == [
        "day_7",
        "day_30",
        "day_60",
        "day_90",
    ]
    assert "pitch.pdf" not in repr(gtm_artifact)
    assert "source_url" not in repr(gtm_artifact)


def test_startup_composers_resolve_market_fixture_without_repo_tests_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from due_diligence_agent.bootstrap import container

    root = _test_dir("startup-market-packaged-fixture-composers")
    monkeypatch.setattr(container, "_project_root", lambda: root / "installed-runtime")

    services = [
        container.build_startup_analysis_composer(root / "analysis"),
        container.build_deterministic_startup_analysis_composer(root / "deterministic"),
    ]
    advisor = container.build_startup_advisor_research_service(
        profile_repository=object(),
    )
    research_ports = [
        service._dependencies.market_research._research_port  # noqa: SLF001
        for service in services
    ]
    research_ports.append(advisor._fallback_research_port)  # noqa: SLF001

    for research_port in research_ports:
        snapshot = research_port.collect(
            StartupResearchPlan(
                case_id=UUID(CASE_ID),
                source_mode=StartupResearchSourceMode.FROZEN,
                queries=("packaged startup market fixture",),
            )
        )
        assert snapshot.source_mode is StartupResearchSourceMode.FROZEN
        assert snapshot.competitors
        assert "fallback" not in " ".join(snapshot.labels).casefold()


def test_startup_bootstrap_composer_persists_safe_critic_arbiter_history() -> None:
    root = _test_dir("startup-composer-reflexion-roles")
    source = root / "pitch.pdf"
    source.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")
    service = build_startup_analysis_composer(root)

    service.start(
        _composer_case_input(root, source),
        thread_id="startup-composer-reflexion-roles",
    )
    result = service.resume(
        _approval("approved"),
        thread_id="startup-composer-reflexion-roles",
    )
    runtime = service._dependencies.workflow_store.load(CASE_ID)  # noqa: SLF001
    artifact = runtime["startup_reflexion_artifact"]
    history = runtime["startup_reflexion_history"]

    assert result["arbiter_status"] == "unresolved"
    assert artifact["schema_version"] == "startup_reflexion_roles@1"
    assert artifact["round_number"] == 2
    assert [item["round_number"] for item in history] == [1, 2]
    assert "stale_source" in history[0]["critic"]["issues"][0]["code"]
    assert artifact["arbiter"]["contradiction_ids"] == result["contradiction_ids"]
    assert "source_url" not in repr(history)
    assert "source_label" not in repr(history)
    assert "query" not in repr(history)


def test_startup_bootstrap_gate3_rebuilds_product_validation_without_excluded_fact() -> None:
    root = _test_dir(f"startup-composer-product-validation-gate3-{uuid4().hex}")
    source = root / "pitch.docx"
    source.write_bytes(
        _docx_bytes(
            "Problem: manual reconciliation. ARR 2.4m. Customer count 420 customers."
        )
    )
    service = build_deterministic_startup_analysis_composer(root)
    thread_id = "startup-composer-product-validation-gate3"

    service.start(_composer_case_input(root, source), thread_id=thread_id)
    gate3 = service.resume(_approval("approved"), thread_id=thread_id)
    excluded_fact_id = str(gate3["evidence_fact_ids"][0])
    original_snapshot_id = str(gate3["product_validation_snapshot_id"])
    original_gtm_snapshot_id = str(gate3["gtm_snapshot_id"])

    result = service.resume(
        _gate3_decision(exclusions=[{"evidence_fact_id": excluded_fact_id}]),
        thread_id=thread_id,
    )
    if result.get("pending_gate") == "startup_gate4_freeze":
        result = service.resume(_gate4_decision(result=result), thread_id=thread_id)
    runtime = service._dependencies.workflow_store.load(CASE_ID)  # noqa: SLF001
    product_artifact = runtime["startup_product_validation_artifact"]
    history = runtime["startup_product_validation_history"]
    gtm_artifact = runtime["startup_gtm_artifact"]
    gtm_history = runtime["startup_gtm_history"]

    assert result["status"] == "completed", (
        result.get("error_code"),
        result.get("node_results"),
        runtime.get("warnings"),
    )
    assert result["product_validation_snapshot_id"] != original_snapshot_id
    assert product_artifact["snapshot"]["snapshot_id"] == result[
        "product_validation_snapshot_id"
    ]
    assert len(history) == 2
    assert [item["snapshot_id"] for item in history] == [
        original_snapshot_id,
        result["product_validation_snapshot_id"],
    ]
    assert all(
        excluded_fact_id not in dimension["evidence_fact_ids"]
        for dimension in product_artifact["snapshot"]["dimensions"]
    )
    assert result["gtm_snapshot_id"] != original_gtm_snapshot_id
    assert gtm_artifact["snapshot"]["snapshot_id"] == result["gtm_snapshot_id"]
    assert [item["snapshot_id"] for item in gtm_history] == [
        original_gtm_snapshot_id,
        result["gtm_snapshot_id"],
    ]
    assert all(
        excluded_fact_id not in dimension["evidence_fact_ids"]
        for dimension in gtm_artifact["snapshot"]["dimensions"]
    )


def test_startup_bootstrap_composer_restricted_docx_stays_local_after_approval(
) -> None:
    root = _test_dir("startup-composer-restricted-docx")
    source = root / "pitch.docx"
    source.write_bytes(_docx_bytes("Founder secret Bearer sk-proj-secret-123 cap table"))
    provider = ProviderCallProbe()
    service = build_startup_analysis_composer(root, provider=provider)

    started = service.start(
        _composer_case_input(root, source),
        thread_id="startup-composer-restricted-docx",
    )
    runtime = service._dependencies.workflow_store.load(CASE_ID)  # noqa: SLF001
    snapshot = runtime["disclosure_snapshot"]

    assert started["status"] == "approval_required"
    assert SensitivityClass.RESTRICTED in snapshot.detected_classes
    assert snapshot.category_counts
    if "restricted_source" in snapshot.category_counts:
        assert runtime["privacy_fail_closed_code"] == "startup_privacy_fail_closed"
        assert runtime["privacy_fail_closed_reason"] == "no_parsed_text_blocks"

    gate3 = service.resume(
        _approval("approved"),
        thread_id="startup-composer-restricted-docx",
    )
    assert gate3["status"] == "review_required"
    assert gate3["pending_gate"] == "startup_gate3_review"

    result = service.resume(
        _gate3_decision(),
        thread_id="startup-composer-restricted-docx",
    )
    result = service.resume(
        _gate4_decision(result=result),
        thread_id="startup-composer-restricted-docx",
    )
    assert result["status"] == "completed_with_policy_blocks"
    assert result["approval_ids"] == []
    assert provider.calls == []


def test_startup_bootstrap_composer_approval_scope_allows_confidential_evidence_facts(
) -> None:
    root = _test_dir(f"startup-composer-confidential-scope-{uuid4().hex}")
    source = root / "pitch.docx"
    source.write_bytes(_docx_bytes("ARR 2.4m. Gross margin 72 percent. Runway 18 months."))
    service = build_startup_analysis_composer(root)

    started = service.start(
        _composer_case_input(root, source),
        thread_id="startup-composer-confidential-scope",
    )
    runtime = service._dependencies.workflow_store.load(CASE_ID)  # noqa: SLF001
    snapshot = runtime["disclosure_snapshot"]

    assert started["status"] == "approval_required"
    assert SensitivityClass.CONFIDENTIAL in snapshot.detected_classes
    assert SensitivityClass.RESTRICTED not in snapshot.detected_classes

    service.resume(_approval("approved"), thread_id="startup-composer-confidential-scope")
    scope = service._dependencies.disclosure.resolve_scope(snapshot)  # noqa: SLF001

    assert scope is not None
    assert SensitivityClass.CONFIDENTIAL in scope.allowed_classes


def test_startup_bootstrap_composer_financial_table_numbers_keep_gate2_scope_exportable(
) -> None:
    suffix = uuid4().hex
    root = _test_dir(f"startup-composer-financial-table-scope-{suffix}")
    thread_id = f"startup-composer-financial-table-scope-{suffix}"
    source = root / "smart-university-financials.docx"
    source.write_bytes(
        _docx_bytes(
            "Smart University helps applicants compare university programs and manage admissions.\n"
            "Base case\n"
            "49 0 38 6 33 3\n"
            "mln KZT revenue, mln KZT EBITDA, margin percent.\n"
            "School CAC\n"
            "450 250 600 10 20\n"
            "thousand KZT range and first sales count."
        )
    )
    service = build_startup_analysis_composer(root)

    started = service.start(
        _composer_case_input(root, source),
        thread_id=thread_id,
    )
    runtime = service._dependencies.workflow_store.load(CASE_ID)  # noqa: SLF001
    snapshot = runtime["disclosure_snapshot"]

    assert started["status"] == "approval_required"
    assert "phone" not in snapshot.category_counts
    assert SensitivityClass.RESTRICTED not in snapshot.detected_classes

    service.resume(_approval("approved"), thread_id=thread_id)
    scope = service._dependencies.disclosure.resolve_scope(snapshot)  # noqa: SLF001

    assert scope is not None
    assert SensitivityClass.CONFIDENTIAL in scope.allowed_classes


def test_startup_bootstrap_composer_public_pdf_redacts_pii_and_gate2_allows_same_revision_scope(
) -> None:
    suffix = uuid4().hex
    root = _test_dir(f"startup-composer-public-pdf-pii-scope-{suffix}")
    thread_id = f"startup-composer-public-pdf-pii-scope-{suffix}"
    source = root / "smart-university-public-pii.pdf"
    _write_text_pdf_fixture(
        source,
        (
            "Smart University helps applicants compare university programs and manage admissions.",
            "Founder contact john@example.com and phone +1 415 555 0199.",
            "Base case MRR 40k KZT and runway 18 months.",
        ),
    )
    service = build_startup_analysis_composer(root)

    started = service.start(
        _composer_case_input(root, source),
        thread_id=thread_id,
    )
    runtime = service._dependencies.workflow_store.load(CASE_ID)  # noqa: SLF001
    snapshot = runtime["disclosure_snapshot"]
    stored_payloads = [
        service._dependencies.privacy._privacy_service.artifact_store.read_bytes(text_ref).decode(  # noqa: SLF001
            "utf-8"
        )
        for text_ref in snapshot.minimized_fragment_refs
    ]

    assert started["status"] == "approval_required"
    assert snapshot.category_counts["email"] == 1
    assert snapshot.category_counts["phone"] == 1
    assert snapshot.overall_class == SensitivityClass.CONFIDENTIAL
    assert SensitivityClass.CONFIDENTIAL in snapshot.detected_classes
    assert SensitivityClass.RESTRICTED not in snapshot.detected_classes
    assert any("[REDACTED:email:1]" in payload for payload in stored_payloads)
    assert any("[REDACTED:phone:1]" in payload for payload in stored_payloads)
    assert all("john@example.com" not in payload for payload in stored_payloads)
    assert all("+1 415 555 0199" not in payload for payload in stored_payloads)

    service.resume(_approval("approved"), thread_id=thread_id)
    scope = service._dependencies.disclosure.resolve_scope(snapshot)  # noqa: SLF001

    assert scope is not None
    assert SensitivityClass.CONFIDENTIAL in scope.allowed_classes


def test_startup_bootstrap_composer_extracts_structured_claims_from_docx_and_persists_after_restart(
) -> None:
    root = _test_dir(f"startup-composer-structured-claims-{uuid4().hex}")
    source = root / "pitch.docx"
    source.write_bytes(
        _docx_bytes(
            "ARR 2.4m. Gross margin 72 percent. Runway 18 months. Customer count 420 customers."
        )
    )
    provider = ProviderStructuredClaimProbe()
    service = build_startup_analysis_composer(root, provider=provider)

    started = service.start(
        _composer_case_input(root, source),
        thread_id="startup-composer-structured-claims",
    )
    assert started["status"] == "approval_required"

    gate3 = service.resume(
        _approval("approved"),
        thread_id="startup-composer-structured-claims",
    )

    assert gate3["status"] == "review_required"
    assert set(provider.observed_evidence_fact_ids) == set(gate3["evidence_fact_ids"])
    restarted = build_startup_analysis_composer(root, provider=ProviderStructuredClaimProbe())
    claim_repo = restarted._dependencies.claims._claim_repository  # noqa: SLF001
    evidence_repo = restarted._dependencies.evidence._evidence_repository  # noqa: SLF001
    claims = claim_repo.list_for_case(UUID(CASE_ID))
    facts = evidence_repo.list_for_case(UUID(CASE_ID))

    assert {claim.normalized_name for claim in claims} == {
        "arr",
        "gross_margin",
        "runway",
        "customer_count",
    }
    assert {claim.normalized_value for claim in claims} == {
        Decimal("2400000"),
        Decimal("72"),
        Decimal("18"),
        Decimal("420"),
    }
    claim_fact_ids = {
        str(fact.id)
        for fact in facts
        if fact.metadata.get("startup_claim_id") is not None
    }
    generic_text_fact_ids = {
        str(fact.id)
        for fact in facts
        if fact.extraction_method == "startup-parsed-document@1"
    }
    assert claim_fact_ids < set(gate3["evidence_fact_ids"])
    assert generic_text_fact_ids
    assert claim_fact_ids | generic_text_fact_ids == set(gate3["evidence_fact_ids"])
    assert all(fact.value_type == "decimal" for fact in facts if str(fact.id) in claim_fact_ids)
    assert all(fact.period == "unknown" for fact in facts if str(fact.id) in claim_fact_ids)
    runtime = restarted._dependencies.workflow_store.load(CASE_ID)  # noqa: SLF001
    assert set(runtime["claim_status_by_id"].values()) == {"unsupported"}
    arr_diagnostic = next(
        item for item in runtime["metric_diagnostics"] if item["metric_name"] == "arr"
    )
    assert arr_diagnostic["status"] == "insufficient_data"
    assert arr_diagnostic["calculation_id"] is None

    repeated = service._dependencies.evidence.extract(  # noqa: SLF001
        case_id=CASE_ID,
        parsed_artifact_ids=[str(item) for item in gate3["parsed_artifact_ids"]],
    )
    repeated_claims = claim_repo.list_for_case(UUID(CASE_ID))
    repeated_facts = evidence_repo.list_for_case(UUID(CASE_ID))
    assert set(repeated["startup_claim_ids"]) == {str(claim.id) for claim in claims}
    assert set(repeated["evidence_fact_ids"]) == claim_fact_ids | generic_text_fact_ids
    assert len(repeated_claims) == len(claims) == 4
    assert len(
        [fact for fact in repeated_facts if fact.metadata.get("startup_claim_id") is not None]
    ) == 4


def test_deterministic_composer_uses_local_provider_after_gate2_approval() -> None:
    root = _test_dir(f"startup-composer-deterministic-{uuid4().hex}")
    source = root / "pitch.docx"
    source.write_bytes(
        _docx_bytes(
            "ARR 2.4m. Gross margin 72 percent. Runway 18 months. Customer count 420 customers."
        )
    )
    service = build_deterministic_startup_analysis_composer(root)
    thread_id = "startup-composer-deterministic"

    started = service.start(
        _composer_case_input(root, source),
        thread_id=thread_id,
    )
    assert started["status"] == "approval_required"
    assert started["pending_gate"] == "startup_disclosure"

    gate3 = service.resume(_approval("approved"), thread_id=thread_id)

    assert gate3["status"] == "review_required"
    assert gate3["pending_gate"] == "startup_gate3_review"
    assert gate3["evidence_fact_ids"]
    provider = service._dependencies.provider._provider  # noqa: SLF001
    assert provider.calls == ["financial_analysis", "risk_analysis", "market_analysis"]
    assert provider.external_calls == []

    gate4 = service.resume(_gate3_decision(), thread_id=thread_id)
    result = service.resume(_gate4_decision(result=gate4), thread_id=thread_id)

    assert result["status"] == "completed"
    audit_events = JsonlAuditSpool(root / "startup-audit-spool").read_bounded(max_events=200)
    provider_events = [
        event
        for event in audit_events
        if event.attributes.get("node_name") == "financial_analysis"
    ]
    assert provider_events
    provider_event = provider_events[-1]
    assert provider_event.attributes["case_id"] == CASE_ID
    assert provider_event.attributes["attempt"] == 1
    assert provider_event.attributes["checkpoint_id"]
    assert provider_event.attributes["checkpoint_hash"]
    assert provider_event.attributes["tool"] == "DeterministicStartupProvider"
    assert RAW_SENTINEL not in repr(provider_event)


def test_startup_claim_adapter_builds_matrix_with_independent_evidence_and_persists_contradictions(
) -> None:
    repos = _local_repositories(_test_dir("claim-matrix") / "claim-matrix.sqlite3")
    case_id = UUID(CASE_ID)
    artifact_id = uuid4()
    repos["case"].add(_case(case_id))
    repos["artifact"].add(_artifact(case_id, artifact_id))
    claim = _startup_claim(
        case_id,
        artifact_id,
        normalized_name="arr",
        normalized_value=Decimal("2400000"),
        unit="USD",
        period="FY2026",
    )
    conflicting_fact = _fact(UUID(REVENUE_FACT_ID), artifact_id, "arr").model_copy(
        update={"value": Decimal("1200000"), "unit": "USD", "period": "FY2026"}
    )
    claim_fact = _fact(UUID(COGS_FACT_ID), artifact_id, "arr", metadata={"startup_claim_id": str(claim.id)}).model_copy(
        update={"value": Decimal("2400000"), "unit": "USD", "period": "FY2026"}
    )
    repos["startup_claim"].add(claim)
    repos["evidence"].add(conflicting_fact)
    repos["evidence"].add(claim_fact)
    adapter = StartupClaimRepositoryAdapter(
        repos["startup_claim"],
        evidence_repository=repos["evidence"],
        calculation_repository=repos["calculation"],
        contradiction_repository=repos["contradiction"],
    )

    result = adapter.extract(
        case_id=CASE_ID,
        evidence_fact_ids=[REVENUE_FACT_ID, COGS_FACT_ID],
    )
    repeated = adapter.extract(
        case_id=CASE_ID,
        evidence_fact_ids=[REVENUE_FACT_ID, COGS_FACT_ID],
    )

    assert result["startup_claim_ids"] == [str(claim.id)]
    assert result["claim_status_by_id"] == {str(claim.id): "contradicted"}
    assert len(result["contradiction_ids"]) == 1
    assert repeated["contradiction_ids"] == result["contradiction_ids"]
    persisted = repos["contradiction"].list_for_case(case_id)
    assert [str(item.id) for item in persisted] == result["contradiction_ids"]
    assert persisted[0].fact_ids == (UUID(REVENUE_FACT_ID),)


def test_startup_metric_adapter_reports_insufficient_claim_facts_without_guessing_slots(
) -> None:
    repos = _local_repositories(_test_dir("metric-diagnostics") / "metric.sqlite3")
    case_id = UUID(CASE_ID)
    artifact_id = uuid4()
    repos["case"].add(_case(case_id))
    repos["artifact"].add(_artifact(case_id, artifact_id))
    claim_fact = _fact(UUID(REVENUE_FACT_ID), artifact_id, "arr", metadata={"startup_claim_id": "claim"}).model_copy(
        update={"value": Decimal("2400000"), "unit": "USD", "period": "unknown"}
    )
    repos["evidence"].add(claim_fact)
    adapter = StartupMetricWorkflowAdapter(
        StartupMetricService(
            evidence_repository=repos["evidence"],
            calculation_repository=repos["calculation"],
            clock=lambda: datetime(2026, 8, 12, tzinfo=UTC),
        ),
        metric_names=("arr", "gross_margin", "runway_months"),
        evidence_repository=repos["evidence"],
    )

    result = adapter.calculate(case_id=CASE_ID, evidence_fact_ids=[REVENUE_FACT_ID])

    assert result["calculation_ids"] == []
    diagnostics = {item["metric_name"]: item for item in result["metric_diagnostics"]}
    assert set(diagnostics) == {"arr", "gross_margin", "runway_months"}
    assert all(item["status"] == "insufficient_data" for item in diagnostics.values())
    assert all(item["calculation_id"] is None for item in diagnostics.values())
    assert diagnostics["arr"]["input_evidence_ids"] == []


def test_startup_metric_adapter_calculates_only_canonical_formula_slots(
) -> None:
    repos = _local_repositories(_test_dir("metric-canonical") / "metric.sqlite3")
    case_id = UUID(CASE_ID)
    artifact_id = uuid4()
    repos["case"].add(_case(case_id))
    repos["artifact"].add(_artifact(case_id, artifact_id))
    revenue = _fact(UUID(REVENUE_FACT_ID), artifact_id, "revenue").model_copy(
        update={"value": Decimal("1000"), "unit": "USD", "period": "2026"}
    )
    cogs = _fact(UUID(COGS_FACT_ID), artifact_id, "cogs").model_copy(
        update={"value": Decimal("400"), "unit": "USD", "period": "2026"}
    )
    repos["evidence"].add(revenue)
    repos["evidence"].add(cogs)
    adapter = StartupMetricWorkflowAdapter(
        StartupMetricService(
            evidence_repository=repos["evidence"],
            calculation_repository=repos["calculation"],
            clock=lambda: datetime(2026, 8, 12, tzinfo=UTC),
        ),
        metric_names=("gross_margin", "arr"),
        evidence_repository=repos["evidence"],
    )

    result = adapter.calculate(
        case_id=CASE_ID,
        evidence_fact_ids=[REVENUE_FACT_ID, COGS_FACT_ID],
    )

    assert len(result["calculation_ids"]) == 1
    calculation = repos["calculation"].list_for_case(case_id)[0]
    assert calculation.metric_name == "gross_margin"
    assert calculation.value == Decimal("0.600000")
    diagnostics = {item["metric_name"]: item for item in result["metric_diagnostics"]}
    assert diagnostics["gross_margin"]["status"] == "calculated"
    assert diagnostics["gross_margin"]["calculation_id"] == result["calculation_ids"][0]
    assert diagnostics["arr"]["status"] == "insufficient_data"


def test_startup_privacy_port_detects_restricted_markers_from_parsed_content(
) -> None:
    artifact_store = LocalArtifactStore(_test_dir("privacy-port-content") / "artifacts")
    artifact_id = uuid4()
    block = _stored_text_block(
        artifact_store,
        artifact_id=artifact_id,
        text="Founder secret Bearer sk-proj-secret-123 cap table",
    )
    privacy = StartupPrivacyService(
        artifact_store=artifact_store,
        redactor=RulesRedactor(),
        egress_policy=DataEgressPolicy(),
        trace_sanitizer=StrictTraceSanitizer(),
    )
    port = _StartupPrivacyWorkflowPort(
        privacy,
        parser=ParsedBlockParserProbe([block]),
    )

    result = port.classify_redact(
        case_id=CASE_ID,
        parsed_artifact_ids=[str(artifact_id)],
    )
    snapshot = result["snapshot"]

    assert isinstance(snapshot, ClassifiedDisclosureSnapshot)
    assert snapshot.overall_class == SensitivityClass.RESTRICTED
    assert snapshot.category_counts["secret"] == 1


def test_unexpected_node_exception_becomes_typed_safe_workflow_failure(
) -> None:
    deps = StartupWorkflowFixture()
    deps.parser.fail_with = RuntimeError(f"parser exploded with {RAW_SENTINEL}")
    graph = _graph(_test_dir("safe-error"), deps)

    result = graph.invoke(_case_input(), _config("safe-error-case"))

    assert result["status"] == "failed"
    assert result["error_code"] == "workflow_unexpected"
    dumped = deps.audit.serialized() + deps.tracer.serialized() + str(result)
    assert RAW_SENTINEL not in dumped


def test_market_fixture_failure_surfaces_stable_safe_code_without_path_or_traceback(
) -> None:
    deps = StartupWorkflowFixture()
    deps.market_research = BrokenMarketFixturePort()
    graph = _graph(_test_dir("market-fixture-safe-error"), deps)
    config = _config("market-fixture-safe-error")

    graph.invoke(_case_input(raw_payload=RAW_SENTINEL), config)
    result = graph.invoke(Command(resume=_approval("approved")), config)

    assert result["status"] == "failed"
    assert result["error_code"] == "startup_market_fixture_unavailable"
    market_result = next(
        item for item in result["node_results"] if item["node_name"] == "market_research"
    )
    assert market_result["status"] == "failed"
    assert market_result["errors"] == ["startup_market_fixture_unavailable"]
    assert market_result["fallback_used"] is None
    dumped = deps.audit.serialized() + deps.tracer.serialized() + str(result)
    assert RAW_SENTINEL not in dumped
    assert "C:\\Users\\Akana" not in dumped
    assert "Traceback" not in dumped


def test_retry_policy_retries_typed_transient_failures_at_most_three_times(
) -> None:
    deps = StartupWorkflowFixture()
    deps.evidence.retryable_failures = 2
    graph = _graph(_test_dir("retry"), deps)
    config = _config("retry-case")

    graph.invoke(_case_input(), config)
    graph.invoke(Command(resume=_approval("approved")), config)
    gate4 = graph.invoke(Command(resume=_gate3_decision()), config)
    result = graph.invoke(Command(resume=_gate4_decision(result=gate4)), config)

    assert result["status"] == "completed"
    assert deps.evidence.calls == ["extract", "extract", "extract"]
    assert deps.audit.events.count("evidence") == 1
    evidence_event = next(item for item in deps.audit.payloads if item["node_name"] == "evidence")
    assert evidence_event["attempt_count"] == 3
    assert evidence_event["retry_count"] == 2
    attempts = [
        span["retry_count"]
        for span in deps.tracer.spans
        if span["node_name"] == "evidence" and span["status"] == "retryable_error"
    ]
    assert attempts == [1, 2]


def test_provider_outage_replans_with_local_market_fallback_and_reaches_gate4_report_path(
) -> None:
    deps = StartupWorkflowFixture()
    deps.provider = OutageProviderProbe()
    graph = _graph(_test_dir("provider-outage-fallback"), deps)
    config = _config("provider-outage-fallback")

    graph.invoke(_case_input(raw_payload=RAW_SENTINEL), config)
    gate3 = graph.invoke(Command(resume=_approval("approved")), config)

    assert gate3["status"] == "review_required"
    assert gate3["pending_gate"] == "startup_gate3_review"

    gate4 = graph.invoke(Command(resume=_gate3_decision()), config)

    assert gate4["status"] == "approval_required"
    assert gate4["pending_gate"] == "startup_gate4_freeze"
    assert gate4["case_id"] == CASE_ID
    assert gate4["report_snapshot_id"] == REPORT_ID
    assert deps.report.payloads[0]["case_id"] == CASE_ID

    result = graph.invoke(Command(resume=_gate4_decision(result=gate4)), config)

    assert result["status"] == "completed"
    assert result["pending_gate"] is None
    assert deps.provider.calls == [
        "financial_analysis",
        "risk_analysis",
        "market_analysis",
        "market_analysis",
        "market_analysis",
    ]
    market_result = next(
        item for item in result["node_results"] if item["node_name"] == "market_analysis"
    )
    assert market_result["status"] == "partial"
    assert market_result["errors"] == ["startup_provider_outage"]
    assert market_result["retry_count"] == 2
    assert market_result["fallback_used"] == "cached_local_market_research"

    market_spans = [
        span for span in deps.tracer.spans if span["node_name"] == "market_analysis"
    ]
    assert [span["status"] for span in market_spans] == [
        "retryable_error",
        "retryable_error",
        "partial",
    ]
    assert market_spans[-1]["tool"] == "startup_provider"
    assert market_spans[-1]["retry_count"] == 2
    assert market_spans[-1]["error_code"] == "startup_provider_outage"
    assert market_spans[-1]["fallback_used"] == "cached_local_market_research"

    market_audit = _single_payload(deps.audit.payloads, "market_analysis")
    assert market_audit["status"] == "partial"
    assert market_audit["errors"] == ["startup_provider_outage"]
    assert market_audit["retry_count"] == 2
    assert market_audit["fallback_used"] == "cached_local_market_research"
    assert RAW_SENTINEL not in deps.audit.serialized()
    assert RAW_SENTINEL not in deps.tracer.serialized()


def test_provider_contract_violation_remains_terminal_without_local_fallback() -> None:
    deps = StartupWorkflowFixture()
    deps.provider = InvalidProviderContractProbe()
    graph = _graph(_test_dir("provider-contract-fail-closed"), deps)
    config = _config("provider-contract-fail-closed")

    graph.invoke(_case_input(raw_payload=RAW_SENTINEL), config)
    result = graph.invoke(Command(resume=_approval("approved")), config)

    assert result["status"] == "failed"
    assert result["error_code"] == "startup_provider_unpersisted_finding_id"
    assert result["pending_gate"] is None
    assert deps.report.payloads == []
    assert deps.provider.calls == [
        "financial_analysis",
        "risk_analysis",
        "market_analysis",
    ]
    market_result = next(
        item for item in result["node_results"] if item["node_name"] == "market_analysis"
    )
    assert market_result["status"] == "failed"
    assert market_result["errors"] == ["startup_provider_unpersisted_finding_id"]
    assert market_result["fallback_used"] is None
    market_trace = _single_payload(deps.tracer.spans, "market_analysis")
    assert market_trace["status"] == "failed"
    assert market_trace["fallback_used"] is None
    assert RAW_SENTINEL not in deps.audit.serialized()
    assert RAW_SENTINEL not in deps.tracer.serialized()


def test_budget_exhaustion_replans_to_local_evidence_before_over_budget_provider_call(
) -> None:
    root = _test_dir("budget-exhaustion")
    budget = BudgetGuard(
        default_token_limit=200,
        default_usd_limit=Decimal("0.02"),
        persistence_path=root / "budget.sqlite3",
    )
    deps = StartupWorkflowFixture()
    provider = BudgetedProviderProbe(budget)
    deps.provider = provider
    graph = _graph(root, deps)
    config = _config("budget-exhaustion")

    graph.invoke(_case_input(raw_payload=RAW_SENTINEL), config)
    gate3 = graph.invoke(Command(resume=_approval("approved")), config)
    gate4 = graph.invoke(Command(resume=_gate3_decision()), config)
    result = graph.invoke(Command(resume=_gate4_decision(result=gate4)), config)

    assert gate3["status"] == "review_required"
    assert gate4["status"] == "approval_required"
    assert result["status"] == "completed"
    assert provider.calls == ["financial_analysis", "risk_analysis"]
    assert deps.report.payloads[0]["case_id"] == CASE_ID
    fallback = next(
        item for item in result["node_results"] if item["node_name"] == "market_analysis"
    )
    assert fallback["status"] == "partial"
    assert fallback["errors"] == ["BUDGET_EXCEEDED"]
    assert fallback["fallback_used"] == "cached_local_market_research"
    assert [record.attempt for record in budget.usage_for_case(UUID(CASE_ID))] == [
        "financial_analysis",
        "risk_analysis",
    ]
    assert budget.reserved_tokens_for_case(UUID(CASE_ID)) == 0

    audit = _single_payload(deps.audit.payloads, "market_analysis")
    trace = _single_payload(deps.tracer.spans, "market_analysis")
    for payload in (audit, trace):
        assert payload["status"] == "partial"
        assert payload["case_id"] == CASE_ID
        assert payload["run_id"] == RUN_ID
        assert payload["correlation_id"] == CORRELATION_ID
        assert payload["attempt"] == 1
        assert payload["retry_count"] == 0
        assert payload["tool"] == "startup_provider"
        assert payload["error_code"] == "BUDGET_EXCEEDED"
        assert payload["fallback_used"] == "cached_local_market_research"
        assert RAW_SENTINEL not in repr(payload)
        assert "source_refs" not in payload
    assert RAW_SENTINEL not in deps.audit.serialized()
    assert RAW_SENTINEL not in deps.tracer.serialized()


def test_budget_exhaustion_restart_resumes_gate4_after_fallback_without_extra_calls(
) -> None:
    root = _test_dir("budget-exhaustion-restart")
    checkpoint_path = root / "checkpoints.sqlite3"
    runtime_path = root / "runtime.json"
    budget_path = root / "budget.sqlite3"
    config = _config("budget-exhaustion-restart")
    first_budget = BudgetGuard(
        default_token_limit=200,
        default_usd_limit=Decimal("0.02"),
        persistence_path=budget_path,
    )
    first_deps = StartupWorkflowFixture(
        runtime_store=JsonFileStartupWorkflowRuntimeStore(runtime_path)
    )
    first_provider = BudgetedProviderProbe(first_budget)
    first_deps.provider = first_provider

    with _sqlite_saver(checkpoint_path) as saver:
        graph = build_startup_graph(first_deps, checkpointer=saver)
        graph.invoke(_case_input(), config)
        gate3 = graph.invoke(Command(resume=_approval("approved")), config)
        gate4 = graph.invoke(Command(resume=_gate3_decision()), config)

    assert gate3["status"] == "review_required"
    assert gate4["status"] == "approval_required"
    assert first_provider.calls == ["financial_analysis", "risk_analysis"]

    restarted_budget = BudgetGuard(
        default_token_limit=200,
        default_usd_limit=Decimal("0.02"),
        persistence_path=budget_path,
    )
    restarted_deps = StartupWorkflowFixture(
        runtime_store=JsonFileStartupWorkflowRuntimeStore(runtime_path)
    )
    restarted_provider = BudgetedProviderProbe(restarted_budget)
    restarted_deps.provider = restarted_provider
    with _sqlite_saver(checkpoint_path) as saver:
        restarted = build_startup_graph(restarted_deps, checkpointer=saver)
        result = restarted.invoke(
            Command(resume=_gate4_decision(result=gate4)),
            config,
        )

    assert result["status"] == "completed"
    fallback = next(
        item for item in result["node_results"] if item["node_name"] == "market_analysis"
    )
    assert fallback["status"] == "partial"
    assert fallback["errors"] == ["BUDGET_EXCEEDED"]
    assert fallback["fallback_used"] == "cached_local_market_research"
    assert restarted_provider.calls == []
    assert len(restarted_budget.usage_for_case(UUID(CASE_ID))) == 2
    assert restarted_budget.reserved_tokens_for_case(UUID(CASE_ID)) == 0


def test_gate3_routes_only_affected_nodes_and_skips_unaffected_market() -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("gate3-routing"), deps)
    config = _config("gate3-routing")

    graph.invoke(_case_input(), config)
    graph.invoke(Command(resume=_approval("approved")), config)
    result = graph.invoke(
        Command(resume=_gate3_decision(exclusions=[{"evidence_fact_id": REVENUE_FACT_ID}])),
        config,
    )

    assert result["invalidated_ids"] == [
        REVENUE_FACT_ID,
        CALCULATION_ID,
        "finding-financial",
        FINDING_ID,
        CONTRADICTION_ID,
        REPORT_ID,
        PRODUCT_VALIDATION_SNAPSHOT_ID,
        READINESS_SNAPSHOT_ID,
        GTM_SNAPSHOT_ID,
    ]
    assert deps.metrics.calls == ["calculate", "calculate"]
    assert [payload["evidence_fact_ids"] for payload in deps.product_validation.payloads] == [
        [REVENUE_FACT_ID, COGS_FACT_ID],
        [COGS_FACT_ID],
    ]
    assert [payload["evidence_fact_ids"] for payload in deps.gtm.payloads] == [
        [REVENUE_FACT_ID, COGS_FACT_ID],
        [COGS_FACT_ID],
    ]
    assert deps.runtime_store.records[CASE_ID]["gate3_affected_nodes"] == [
        "product_validation",
        "metrics",
        "gtm",
        "financial_analysis",
        "risk_analysis",
        "reflexion",
    ]
    assert deps.provider.calls == [
        "financial_analysis",
        "risk_analysis",
        "market_analysis",
        "financial_analysis",
        "risk_analysis",
    ]


def test_gate3_affected_nodes_are_derived_from_dependency_metadata_not_id_shapes() -> None:
    deps = StartupWorkflowFixture()
    deps.evidence.custom_dependency_result = {"evidence_fact_ids": ["fact-alpha", "fact-beta"]}
    deps.lineage.custom_dependency_result = {
        "dependency_edges": {
            "fact-alpha": ["calc-alpha"],
            "calc-alpha": ["finding-alpha"],
            "finding-alpha": ["contradiction-alpha"],
        },
        "dependency_node_edges": {
            "fact-alpha": ["product_validation", "metrics"],
            "calc-alpha": ["financial_analysis"],
            "finding-alpha": ["reflexion"],
        },
    }
    graph = _graph(_test_dir("gate3-metadata-routing"), deps)
    config = _config("gate3-metadata-routing")

    graph.invoke(_case_input(), config)
    graph.invoke(Command(resume=_approval("approved")), config)
    graph.invoke(
        Command(resume=_gate3_decision(exclusions=[{"evidence_fact_id": "fact-alpha"}])),
        config,
    )

    assert deps.runtime_store.records[CASE_ID]["gate3_affected_nodes"] == [
        "product_validation",
        "metrics",
        "financial_analysis",
        "reflexion",
    ]


def test_gate3_no_exclusion_goes_directly_to_report_without_recompute() -> None:
    deps = StartupWorkflowFixture()
    graph = _graph(_test_dir("gate3-no-exclusion"), deps)
    config = _config("gate3-no-exclusion")

    graph.invoke(_case_input(), config)
    graph.invoke(Command(resume=_approval("approved")), config)
    gate4 = graph.invoke(Command(resume=_gate3_decision()), config)
    result = graph.invoke(Command(resume=_gate4_decision(result=gate4)), config)

    assert result["status"] == "completed"
    assert deps.metrics.calls == ["calculate"]
    assert deps.provider.calls == ["financial_analysis", "risk_analysis", "market_analysis"]


def test_retry_policy_does_not_retry_privacy_or_schema_failures() -> None:
    deps = StartupWorkflowFixture()
    deps.privacy.fail_with = WorkflowFixtureError("privacy", retryable=False)
    graph = _graph(_test_dir("case"), deps)

    result = graph.invoke(_case_input(), _config("nonretry-case"))

    assert result["status"] == "failed"
    assert result["error_code"] == "privacy"
    assert deps.privacy.calls == ["classify_redact"]


def test_startup_plan_registry_is_exact_and_closed() -> None:
    assert STARTUP_NODE_REGISTRY == (
        "ingest",
        "parse",
        "classify_redact",
        "evidence",
        "claims",
        "document_intelligence",
        "primary_profile",
        "disclosure",
        "profile_enrichment",
        "product_validation",
        "market_research",
        "metrics",
        "financial_analysis",
        "risk_analysis",
        "market_analysis",
        "gtm",
        "critic",
        "arbiter",
        "report",
        "gate4",
    )


def test_default_startup_plan_is_acyclic_and_has_single_market_synthesis() -> None:
    plan = default_startup_plan()

    assert validate_startup_plan(plan) == plan
    assert [step.node_name for step in plan.steps if "market_analysis" in step.node_name] == [
        "market_analysis"
    ]
    market_step = next(step for step in plan.steps if step.node_name == "market_analysis")
    assert market_step.depends_on == [
        "startup:claims",
        "startup:risk_analysis",
        "startup:market_research",
        "startup:product_validation",
    ]
    gtm_step = next(step for step in plan.steps if step.node_name == "gtm")
    assert gtm_step.depends_on == [
        "startup:profile_enrichment",
        "startup:product_validation",
        "startup:market_research",
        "startup:market_analysis",
    ]
    critic_step = next(step for step in plan.steps if step.node_name == "critic")
    assert "startup:gtm" in critic_step.depends_on
    arbiter_step = next(step for step in plan.steps if step.node_name == "arbiter")
    assert arbiter_step.depends_on == ["startup:critic"]
    gate4_step = next(step for step in plan.steps if step.node_name == "gate4")
    assert gate4_step.depends_on == ["startup:report"]


def _graph(path: Path, deps: "StartupWorkflowFixture") -> Any:
    context = SqliteSaver.from_conn_string(str(path / "checkpoints.sqlite3"))
    saver = context.__enter__()
    _OPEN_CHECKPOINT_CONTEXTS.append(context)
    return build_startup_graph(deps, checkpointer=saver)


def _test_dir(name: str) -> Path:
    path = Path(".tmp-task9-tests") / f"{name}-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _sqlite_saver(path: Path) -> Iterator[SqliteSaver]:
    with SqliteSaver.from_conn_string(str(path)) as saver:
        yield saver


def _config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}


def _single_payload(payloads: list[dict[str, Any]], node_name: str) -> dict[str, Any]:
    matches = [payload for payload in payloads if payload.get("node_name") == node_name]
    assert len(matches) == 1
    return matches[0]


def _case_input(
    *,
    raw_payload: str = RAW_SENTINEL,
    source_refs: list[dict[str, str]] | None = None,
    gate3_exclusions: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "case_id": CASE_ID,
        "run_id": RUN_ID,
        "correlation_id": CORRELATION_ID,
        "source_refs": source_refs
        or [
            {
                "document_id": "doc-0001",
                "private_name": "doc-0001.pdf",
                "content_sha256": "0" * 64,
            }
        ],
        "raw_payload": raw_payload,
    }
    if gate3_exclusions is not None:
        payload["gate3_exclusions"] = gate3_exclusions
    return payload


def _composer_case_input(root: Path, source: Path) -> dict[str, Any]:
    private_name = f"doc-0001{source.suffix.lower() or '.bin'}"
    content = source.read_bytes()
    case_root = root / "inbox" / CASE_ID
    case_root.mkdir(parents=True, exist_ok=True)
    (case_root / private_name).write_bytes(content)
    return _case_input(
        raw_payload="safe local fixture",
        source_refs=[
            {
                "document_id": "doc-0001",
                "private_name": private_name,
                "content_sha256": sha256(content).hexdigest(),
            }
        ],
    )


def test_startup_plan_validator_rejects_cycle() -> None:
    plan = default_startup_plan()
    cyclic = plan.model_copy(
        update={
            "steps": [
                step.model_copy(
                    update={"depends_on": ["startup:report"]}
                )
                if step.task_id == "startup:ingest"
                else step
                for step in plan.steps
            ]
        }
    )

    with pytest.raises(ValueError, match="startup_plan.depends_on.cycle"):
        validate_startup_plan(cyclic)


def _approval(action: str) -> dict[str, str]:
    return {
        "action": action,
        "actor": "founder",
        "destination": "openai.responses",
    }


def _gate3_decision(
    *,
    exclusions: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "action": "approved",
        "exclusions": exclusions or [],
        "gate4_deferred_to": "task10_report_freeze_render_approval",
    }


def _gate4_decision(
    action: str = "approved",
    *,
    result: dict[str, Any] | None = None,
) -> dict[str, object]:
    snapshot = result or {}
    return {
        "action": action,
        "actor": "founder",
        "report_snapshot_id": snapshot.get("report_snapshot_id", REPORT_ID),
        "report_snapshot_hash": snapshot.get(
            "report_snapshot_hash", "sha256:workflow-report"
        ),
        "report_snapshot_revision": snapshot.get("report_snapshot_revision", 7),
    }


def _run_to_gate4_pause(graph: Any, config: dict[str, dict[str, str]]) -> dict[str, Any]:
    graph.invoke(_case_input(), config)
    gate3 = graph.invoke(Command(resume=_approval("approved")), config)
    assert gate3["status"] == "review_required"
    assert gate3["pending_gate"] == "startup_gate3_review"
    return graph.invoke(Command(resume=_gate3_decision()), config)


@dataclass
class StartupWorkflowFixture:
    unresolved_reflexion: bool = False
    restricted_snapshot: bool = False
    runtime_store: "DurableWorkflowStore" = field(default_factory=lambda: DurableWorkflowStore())
    data_room: "FakeDataRoom" = field(default_factory=lambda: FakeDataRoom())
    parser: "FakeParser" = field(default_factory=lambda: FakeParser())
    privacy: "FakePrivacy" = field(default_factory=lambda: FakePrivacy())
    disclosure: "FakeDisclosure" = field(default_factory=lambda: FakeDisclosure())
    evidence: "FakeEvidence" = field(default_factory=lambda: FakeEvidence())
    lineage: "FakeLineage" = field(default_factory=lambda: FakeLineage())
    claims: "FakeClaims" = field(default_factory=lambda: FakeClaims())
    document_intelligence: "FakeDocumentIntelligence" = field(
        default_factory=lambda: FakeDocumentIntelligence()
    )
    profile: "FakeProfile" = field(default_factory=lambda: FakeProfile())
    metrics: "FakeMetrics" = field(default_factory=lambda: FakeMetrics())
    readiness: "FakeReadiness" = field(default_factory=lambda: FakeReadiness())
    market_research: "FakeMarketResearch" = field(default_factory=lambda: FakeMarketResearch())
    product_validation: "FakeProductValidation" = field(
        default_factory=lambda: FakeProductValidation()
    )
    gtm: "FakeGtm" = field(default_factory=lambda: FakeGtm())
    provider: "FakeProvider" = field(default_factory=lambda: FakeProvider())
    reflexion: "FakeReflexion" = field(init=False)
    report: "FakeReport" = field(default_factory=lambda: FakeReport())
    gate3: "FakeGate3" = field(default_factory=lambda: FakeGate3())
    audit: "FakeAudit" = field(default_factory=lambda: FakeAudit())
    tracer: "FakeTracer" = field(default_factory=lambda: FakeTracer())

    def __post_init__(self) -> None:
        self.reflexion = FakeReflexion(unresolved=self.unresolved_reflexion)
        self.privacy.restricted_snapshot = self.restricted_snapshot
        self.workflow_store = self.runtime_store
        self.clock = lambda: datetime(
            2026,
            8,
            12,
            tzinfo=UTC,
        )


class FakeDataRoom:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def ingest(
        self,
        *,
        case_id: str,
        source_refs: list[dict[str, str]],
        data_revision: int,
    ) -> dict[str, Any]:
        del source_refs, data_revision
        self.calls.append("ingest")
        return {"inventory_id": "inventory-901", "artifact_ids": ["artifact-pitch-pdf"]}


class RealLineageDataRoom:
    def __init__(self, repositories: dict[str, Any]) -> None:
        self._repositories = repositories

    def ingest(
        self,
        *,
        case_id: str,
        source_refs: list[dict[str, str]],
        data_revision: int,
    ) -> dict[str, Any]:
        del source_refs, data_revision
        case_uuid = UUID(case_id)
        artifact_id = uuid4()
        self._add_once(self._repositories["case"].add, _case(case_uuid), "case_already_exists")
        self._add_once(
            self._repositories["startup_profile"].add,
            _startup_profile(case_uuid),
            "startup_profile_conflict",
        )
        self._add_once(
            self._repositories["artifact"].add,
            _artifact(case_uuid, artifact_id),
            "artifact_already_exists",
        )
        self._add_once(
            self._repositories["evidence"].add,
            _fact(UUID(REVENUE_FACT_ID), artifact_id, "revenue"),
            "evidence_fact_already_exists",
        )
        self._add_once(
            self._repositories["evidence"].add,
            _fact(UUID(COGS_FACT_ID), artifact_id, "cogs"),
            "evidence_fact_already_exists",
        )
        return {"inventory_id": "inventory-real-lineage", "artifact_ids": [str(artifact_id)]}

    @staticmethod
    def _add_once(add: Any, item: Any, duplicate_code: str) -> None:
        try:
            add(item)
        except ValueError as exc:
            if str(exc) != duplicate_code:
                raise


class FakeParser:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_with: Exception | None = None

    def parse(self, *, case_id: str, inventory_id: str, artifact_ids: list[str]) -> dict[str, Any]:
        self.calls.append("parse")
        if self.fail_with is not None:
            raise self.fail_with
        return {"parsed_artifact_ids": ["parsed-pitch-pdf"]}


class FakePrivacy:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_with: Exception | None = None
        self.restricted_snapshot = False
        self.snapshot = self._snapshot()

    def classify_redact(
        self,
        *,
        case_id: str,
        data_revision: int,
        parsed_artifact_ids: list[str],
        raw_payload: str | None = None,
    ) -> dict[str, Any]:
        assert data_revision == 1
        self.calls.append("classify_redact")
        if self.fail_with is not None:
            raise self.fail_with
        self.snapshot = self._snapshot()
        return {
            "sensitivity_summary_id": "sensitivity-901",
            "snapshot": self.snapshot,
        }

    def _snapshot(self) -> ClassifiedDisclosureSnapshot:
        classes = {
            SensitivityClass.PUBLIC,
            SensitivityClass.INTERNAL,
            SensitivityClass.CONFIDENTIAL,
        }
        overall = SensitivityClass.CONFIDENTIAL
        if self.restricted_snapshot:
            classes.add(SensitivityClass.RESTRICTED)
            overall = SensitivityClass.RESTRICTED
        return ClassifiedDisclosureSnapshot(
            case_id=UUID(CASE_ID),
            detected_classes=frozenset(classes),
            overall_class=overall,
            redaction_policy_version="startup-redaction@1",
            egress_policy_version="data-egress@1",
            data_revision=1,
            content_hash="a" * 64,
            artifact_counts={"pdf": 1},
            mime_counts={"application_pdf": 1},
            category_counts={"confidential_source": 1},
            redacted_fragment_ids=(UUID("60000000-0000-0000-0000-000000000901"),),
            minimized_fragment_refs=("b" * 64,),
            destination="openai.responses",
        )


class FakeDisclosure:
    def __init__(self) -> None:
        self.snapshots: dict[str, ClassifiedDisclosureSnapshot] = {}
        self.fail_with: Exception | None = None

    def build_preview(self, snapshot: ClassifiedDisclosureSnapshot) -> dict[str, Any]:
        self.snapshots[str(snapshot.case_id)] = snapshot
        return {"status": "approval_required", "fragment_count": len(snapshot.redacted_fragment_ids)}

    def decide(
        self,
        snapshot: ClassifiedDisclosureSnapshot,
        *,
        action: str,
        actor: str,
        destination: str,
    ) -> StartupDisclosureApproval:
        if self.fail_with is not None:
            raise self.fail_with
        return StartupDisclosureApproval.from_decision(
            snapshot,
            action="approved" if action == "approved" else "denied",
            actor=actor,
            destination=destination,
            decided_at=datetime(
                2026,
                8,
                12,
                tzinfo=UTC,
            ),
        )

    def resolve_scope(self, snapshot: ClassifiedDisclosureSnapshot) -> dict[str, Any] | None:
        if SensitivityClass.RESTRICTED in snapshot.detected_classes:
            return None
        return {"approval_id": "approval-approved", "destination": snapshot.destination}


class FakeEvidence:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.retryable_failures = 0
        self.custom_dependency_result: dict[str, Any] | None = None

    def extract(self, *, case_id: str, parsed_artifact_ids: list[str]) -> dict[str, Any]:
        self.calls.append("extract")
        if self.retryable_failures:
            self.retryable_failures -= 1
            raise WorkflowFixtureError("temporary_evidence_timeout", retryable=True)
        if self.custom_dependency_result is not None:
            return self.custom_dependency_result
        return {
            "evidence_fact_ids": [REVENUE_FACT_ID, COGS_FACT_ID],
        }


class FakeLineage:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.custom_dependency_result: dict[str, Any] | None = None

    def derive(self, *, case_id: str, evidence_fact_ids: list[str]) -> dict[str, Any]:
        self.calls.append("derive")
        if self.custom_dependency_result is not None:
            return self.custom_dependency_result
        return {
            "dependency_edges": {
                REVENUE_FACT_ID: [CALCULATION_ID],
                CALCULATION_ID: ["finding-financial", FINDING_ID],
                FINDING_ID: [CONTRADICTION_ID],
                CONTRADICTION_ID: [REPORT_ID],
            },
            "dependency_node_edges": {
                REVENUE_FACT_ID: ["product_validation", "metrics", "gtm"],
                CALCULATION_ID: ["financial_analysis", "risk_analysis"],
                FINDING_ID: ["gtm", "reflexion"],
            },
        }


class FakeClaims:
    def extract(self, *, case_id: str, evidence_fact_ids: list[str]) -> dict[str, Any]:
        return {"startup_claim_ids": ["claim-market-timing", "claim-unit-economics"]}


class FakeDocumentIntelligence:
    trace_tool_name = "startup_document_intelligence"

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def analyze(self, **payload: Any) -> dict[str, str | int]:
        self.payloads.append(dict(payload))
        return {
            "document_intelligence_snapshot_id": DOCUMENT_INTELLIGENCE_SNAPSHOT_ID,
            "document_intelligence_snapshot_hash": DOCUMENT_INTELLIGENCE_SNAPSHOT_HASH,
            "document_intelligence_snapshot_revision": int(payload["data_revision"]),
        }


@dataclass(frozen=True)
class FakeProfileRecord:
    profile_id: UUID
    profile_hash: str
    data_revision: int


class FakeProfile:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def build_primary(self, *, case_id: UUID) -> FakeProfileRecord:
        assert str(case_id) == CASE_ID
        self.calls.append("build_primary")
        return FakeProfileRecord(
            profile_id=UUID("60000000-0000-0000-0000-000000000999"),
            profile_hash="sha256:primary-profile",
            data_revision=1,
        )

    def enrich(
        self,
        *,
        case_id: UUID,
        primary_profile_id: UUID,
        disclosure_scope: object | None,
    ) -> FakeProfileRecord:
        assert str(case_id) == CASE_ID
        assert str(primary_profile_id) == "60000000-0000-0000-0000-000000000999"
        assert disclosure_scope is not None
        self.calls.append("enrich")
        return FakeProfileRecord(
            profile_id=UUID("60000000-0000-0000-0000-000000000998"),
            profile_hash="sha256:enriched-profile",
            data_revision=1,
        )


class PersistedProfilePort:
    def __init__(self, repositories: dict[str, Any]) -> None:
        self._repositories = repositories

    def build_primary(self, *, case_id: UUID) -> StartupProfile:
        return self._repositories["startup_profile"].get_current(case_id)

    def enrich(
        self,
        *,
        case_id: UUID,
        primary_profile_id: UUID,
        disclosure_scope: object | None,
    ) -> StartupProfile:
        del primary_profile_id, disclosure_scope
        return self._repositories["startup_profile"].get_current(case_id)


class FakeMetrics:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def calculate(self, *, case_id: str, evidence_fact_ids: list[str]) -> dict[str, Any]:
        self.calls.append("calculate")
        if REVENUE_FACT_ID not in evidence_fact_ids:
            return {"calculation_ids": []}
        return {"calculation_ids": [CALCULATION_ID]}

    def recalculate_affected(
        self,
        *,
        case_id: str,
        remaining_evidence_fact_ids: list[str],
        invalidated_ids: list[str],
    ) -> dict[str, Any]:
        self.calls.append("calculate:affected_only")
        return {"calculation_ids": []}


class FakeReadiness:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def evaluate(
        self,
        *,
        case_id: str,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
        metric_diagnostics: list[dict[str, Any]],
        calculation_ids: list[str],
    ) -> dict[str, str | int]:
        self.payloads.append(
            {
                "case_id": case_id,
                "profile_id": profile_id,
                "profile_hash": profile_hash,
                "profile_revision": profile_revision,
                "metric_diagnostics": metric_diagnostics,
                "calculation_ids": calculation_ids,
            }
        )
        return {
            "readiness_snapshot_id": READINESS_SNAPSHOT_ID,
            "readiness_snapshot_hash": READINESS_SNAPSHOT_HASH,
            "readiness_snapshot_revision": profile_revision,
        }


class FakeMarketResearch:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def research(
        self,
        *,
        case_id: str,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
    ) -> dict[str, str | int]:
        self.payloads.append(
            {
                "case_id": case_id,
                "profile_id": profile_id,
                "profile_hash": profile_hash,
                "profile_revision": profile_revision,
            }
        )
        return {
            "market_research_snapshot_id": MARKET_RESEARCH_SNAPSHOT_ID,
            "market_research_snapshot_hash": MARKET_RESEARCH_SNAPSHOT_HASH,
            "market_research_snapshot_revision": profile_revision,
        }


class BrokenMarketFixturePort:
    trace_tool_name = "startup_market_research"

    def research(
        self,
        *,
        case_id: str,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
    ) -> dict[str, str | int]:
        del case_id, profile_id, profile_hash, profile_revision
        cause = ValueError(
            "fixture missing at C:\\Users\\Akana\\repo\\tests\\fixtures\\startup_market_research_v1\n"
            f"Traceback: {RAW_SENTINEL}"
        )
        raise StartupMarketFixtureUnavailableError() from cause


class RealLineageMetrics:
    def __init__(self, repositories: dict[str, Any]) -> None:
        self._repositories = repositories

    def calculate(self, *, case_id: str, evidence_fact_ids: list[str]) -> dict[str, Any]:
        if REVENUE_FACT_ID not in evidence_fact_ids:
            return {"calculation_ids": []}
        calculation = _calculation(
            UUID(CALCULATION_ID),
            UUID(case_id),
            (UUID(REVENUE_FACT_ID), UUID(COGS_FACT_ID)),
        )
        RealLineageDataRoom._add_once(
            self._repositories["calculation"].add,
            calculation,
            "calculation_already_exists",
        )
        return {"calculation_ids": [CALCULATION_ID]}


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.payloads: list[dict[str, Any]] = []

    def analyze(
        self,
        *,
        case_id: str,
        node_name: str,
        disclosure_scope: object | None,
        remaining_evidence_fact_ids: list[str],
        remaining_calculation_ids: list[str],
        invalidated_ids: list[str],
    ) -> dict[str, Any]:
        if disclosure_scope is None:
            raise AssertionError("provider called without disclosure scope")
        self.calls.append(node_name)
        self.payloads.append(
            {
                "case_id": case_id,
                "node_name": node_name,
                "remaining_evidence_fact_ids": remaining_evidence_fact_ids,
                "remaining_calculation_ids": remaining_calculation_ids,
                "invalidated_ids": invalidated_ids,
            }
        )
        if node_name in {"financial_analysis", "risk_analysis"} and REVENUE_FACT_ID not in remaining_evidence_fact_ids:
            return {"finding_ids": []}
        return {
            "finding_ids": {
                "financial_analysis": ["finding-financial"],
                "risk_analysis": [FINDING_ID],
                "market_analysis": ["finding-market"],
            }[node_name]
        }


class FakeProductValidation:
    trace_tool_name = "startup_product_validation"

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def evaluate(self, **payload: Any) -> dict[str, str | int]:
        self.payloads.append(dict(payload))
        return {
            "product_validation_snapshot_id": PRODUCT_VALIDATION_SNAPSHOT_ID,
            "product_validation_snapshot_hash": PRODUCT_VALIDATION_SNAPSHOT_HASH,
            "product_validation_snapshot_revision": int(payload["profile_revision"]),
        }


class FakeGtm:
    trace_tool_name = "startup_gtm"

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def evaluate(self, **payload: Any) -> dict[str, str | int]:
        self.payloads.append(dict(payload))
        rebuilt = REVENUE_FACT_ID not in payload["evidence_fact_ids"]
        return {
            "gtm_snapshot_id": REBUILT_GTM_SNAPSHOT_ID if rebuilt else GTM_SNAPSHOT_ID,
            "gtm_snapshot_hash": REBUILT_GTM_SNAPSHOT_HASH if rebuilt else GTM_SNAPSHOT_HASH,
            "gtm_snapshot_revision": int(payload["profile_revision"]),
        }


class BudgetedProviderProbe(FakeProvider):
    trace_tool_name = "startup_provider"

    def __init__(self, budget: BudgetGuard) -> None:
        super().__init__()
        self._budget = budget

    def analyze(
        self,
        *,
        case_id: str,
        node_name: str,
        disclosure_scope: object | None,
        remaining_evidence_fact_ids: list[str],
        remaining_calculation_ids: list[str],
        invalidated_ids: list[str],
    ) -> dict[str, Any]:
        reservation = self._budget.reserve(
            LLMBudgetRequest(
                case_id=UUID(case_id),
                worst_case_tokens=100,
                worst_case_usd_cost=Decimal("0.01"),
            ),
            attempt=node_name,
        )
        result = super().analyze(
            case_id=case_id,
            node_name=node_name,
            disclosure_scope=disclosure_scope,
            remaining_evidence_fact_ids=remaining_evidence_fact_ids,
            remaining_calculation_ids=remaining_calculation_ids,
            invalidated_ids=invalidated_ids,
        )
        self._budget.reconcile(reservation, usage=None)
        return result


class OutageProviderProbe(FakeProvider):
    trace_tool_name = "startup_provider"

    def analyze(
        self,
        *,
        case_id: str,
        node_name: str,
        disclosure_scope: object | None,
        remaining_evidence_fact_ids: list[str],
        remaining_calculation_ids: list[str],
        invalidated_ids: list[str],
    ) -> dict[str, Any]:
        if node_name == "market_analysis":
            self.calls.append(node_name)
            raise WorkflowFixtureError("startup_provider_outage", retryable=True)
        return super().analyze(
            case_id=case_id,
            node_name=node_name,
            disclosure_scope=disclosure_scope,
            remaining_evidence_fact_ids=remaining_evidence_fact_ids,
            remaining_calculation_ids=remaining_calculation_ids,
            invalidated_ids=invalidated_ids,
        )


class InvalidProviderContractProbe(FakeProvider):
    trace_tool_name = "startup_provider"

    def analyze(
        self,
        *,
        case_id: str,
        node_name: str,
        disclosure_scope: object | None,
        remaining_evidence_fact_ids: list[str],
        remaining_calculation_ids: list[str],
        invalidated_ids: list[str],
    ) -> dict[str, Any]:
        if node_name == "market_analysis":
            self.calls.append(node_name)
            raise WorkflowFixtureError(
                "startup_provider_unpersisted_finding_id",
                retryable=False,
            )
        return super().analyze(
            case_id=case_id,
            node_name=node_name,
            disclosure_scope=disclosure_scope,
            remaining_evidence_fact_ids=remaining_evidence_fact_ids,
            remaining_calculation_ids=remaining_calculation_ids,
            invalidated_ids=invalidated_ids,
        )


class RealLineageProvider:
    def __init__(self, repositories: dict[str, Any]) -> None:
        self._repositories = repositories

    def analyze(
        self,
        *,
        case_id: str,
        node_name: str,
        disclosure_scope: object | None,
        remaining_evidence_fact_ids: list[str],
        remaining_calculation_ids: list[str],
        invalidated_ids: list[str],
    ) -> dict[str, Any]:
        del disclosure_scope, invalidated_ids
        case_uuid = UUID(case_id)
        if (
            node_name != "risk_analysis"
            or REVENUE_FACT_ID not in remaining_evidence_fact_ids
            or CALCULATION_ID not in remaining_calculation_ids
        ):
            return {"finding_ids": []}
        finding = _finding(
            UUID(FINDING_ID),
            case_uuid,
            (UUID(REVENUE_FACT_ID),),
            (UUID(CALCULATION_ID),),
        )
        RealLineageDataRoom._add_once(
            self._repositories["finding"].add,
            finding,
            "finding_already_exists",
        )
        contradiction = _contradiction(
            UUID(CONTRADICTION_ID),
            case_uuid,
            (UUID(REVENUE_FACT_ID),),
            (UUID(FINDING_ID),),
        )
        RealLineageDataRoom._add_once(
            self._repositories["contradiction"].add,
            contradiction,
            "contradiction_already_exists",
        )
        RealLineageDataRoom._add_once(
            self._repositories["report"].add_snapshot,
            _report_snapshot(UUID(REPORT_ID), case_uuid),
            "report_snapshot_already_exists",
        )
        return {"finding_ids": [FINDING_ID]}


class FakeReflexion:
    critic_trace_tool_name = "startup_critic"
    arbiter_trace_tool_name = "startup_arbiter"

    def __init__(self, *, unresolved: bool) -> None:
        self.unresolved = unresolved
        self.calls: list[str] = []
        self.critic_calls: list[int] = []
        self.arbiter_calls: list[int] = []
        self.payloads: list[dict[str, Any]] = []

    def review_critic(
        self,
        *,
        case_id: str | None = None,
        round_number: int,
        finding_ids: list[str] | None = None,
        contradiction_ids: list[str],
    ) -> dict[str, Any]:
        self.critic_calls.append(round_number)
        self.payloads.append(
            {
                "case_id": case_id,
                "round_number": round_number,
                "finding_ids": list(finding_ids or []),
                "contradiction_ids": list(contradiction_ids),
            }
        )
        if self.unresolved:
            return {
                "critic_issue_codes": ["metric_conflict"],
                "critic_issue_ids": ["critic-issue-metric-conflict"],
            }
        return {"critic_issue_codes": [], "critic_issue_ids": []}

    def arbitrate(self, *, case_id: str, round_number: int) -> dict[str, Any]:
        del case_id
        self.arbiter_calls.append(round_number)
        if self.unresolved:
            return {
                "contradiction_ids": [CONTRADICTION_ID],
                "progress": round_number == 1,
                "arbiter_status": "revision_required" if round_number == 1 else "unresolved",
                "critic_issue_codes": ["metric_conflict"],
                "critic_issue_ids": ["critic-issue-metric-conflict"],
            }
        return {
            "contradiction_ids": [],
            "progress": False,
            "arbiter_status": "accepted",
            "critic_issue_codes": [],
            "critic_issue_ids": [],
        }


class RealLineageReflexion:
    def __init__(self, repositories: dict[str, Any]) -> None:
        self._repositories = repositories

    def review(self, *, round_number: int, contradiction_ids: list[str]) -> dict[str, Any]:
        del round_number, contradiction_ids
        contradiction = _contradiction(
            UUID(CONTRADICTION_ID),
            UUID(CASE_ID),
            (UUID(REVENUE_FACT_ID),),
            (UUID(FINDING_ID),),
        )
        RealLineageDataRoom._add_once(
            self._repositories["contradiction"].add,
            contradiction,
            "contradiction_already_exists",
        )
        RealLineageDataRoom._add_once(
            self._repositories["report"].add_snapshot,
            _report_snapshot(UUID(REPORT_ID), UUID(CASE_ID)),
            "report_already_exists",
        )
        return {"contradiction_ids": [CONTRADICTION_ID], "progress": False}


class FakeGate3:
    def apply_exclusions(
        self,
        *,
        exclusions: list[dict[str, str]],
        dependency_edges: dict[str, list[str]],
        calculation_ids: list[str],
        finding_ids: list[str],
        contradiction_ids: list[str],
        report_snapshot_id: str | None,
    ) -> dict[str, Any]:
        if not exclusions:
            return {}
        calculation_result = {"calculation_ids": []}
        return {
            **calculation_result,
            "finding_ids": ["finding-unaffected-market"],
            "contradiction_ids": [],
            "report_snapshot_id": None,
            "invalidated_ids": [
                REVENUE_FACT_ID,
                CALCULATION_ID,
                FINDING_ID,
                CONTRADICTION_ID,
                REPORT_ID,
            ],
        }


class FakeReport:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.freeze_payloads: list[dict[str, Any]] = []

    def build(
        self,
        *,
        case_id: str,
        profile_id: str,
        profile_hash: str,
        profile_revision: int,
        readiness_snapshot_id: str,
        readiness_snapshot_hash: str,
        readiness_snapshot_revision: int,
        market_research_snapshot_id: str,
        market_research_snapshot_hash: str,
        market_research_snapshot_revision: int,
        gtm_snapshot_id: str,
        gtm_snapshot_hash: str,
        gtm_snapshot_revision: int,
        startup_claim_ids: list[str],
        evidence_fact_ids: list[str],
        calculation_ids: list[str],
        finding_ids: list[str],
        contradiction_ids: list[str],
    ) -> dict[str, Any]:
        self.payloads.append(
            {
                "case_id": case_id,
                "profile_id": profile_id,
                "profile_hash": profile_hash,
                "profile_revision": profile_revision,
                "readiness_snapshot_id": readiness_snapshot_id,
                "readiness_snapshot_hash": readiness_snapshot_hash,
                "readiness_snapshot_revision": readiness_snapshot_revision,
                "market_research_snapshot_id": market_research_snapshot_id,
                "market_research_snapshot_hash": market_research_snapshot_hash,
                "market_research_snapshot_revision": market_research_snapshot_revision,
                "gtm_snapshot_id": gtm_snapshot_id,
                "gtm_snapshot_hash": gtm_snapshot_hash,
                "gtm_snapshot_revision": gtm_snapshot_revision,
                "startup_claim_ids": startup_claim_ids,
                "evidence_fact_ids": evidence_fact_ids,
                "calculation_ids": calculation_ids,
                "finding_ids": finding_ids,
                "contradiction_ids": contradiction_ids,
            }
        )
        return {
            "report_snapshot_id": "report-recomputed-without-excluded"
            if not calculation_ids
            else REPORT_ID,
            "report_snapshot_hash": "sha256:workflow-report",
            "report_snapshot_revision": 7,
        }

    def decide_gate4(
        self,
        case_id: str,
        *,
        decision: str,
        snapshot_hash: str,
        snapshot_revision: int,
        reason: str | None = None,
    ) -> CanonicalReportSnapshot:
        del reason
        payload = {
            "case_id": case_id,
            "action": decision,
            "actor": "founder",
            "report_snapshot_id": REPORT_ID,
            "report_snapshot_hash": snapshot_hash,
            "report_snapshot_revision": snapshot_revision,
        }
        self.freeze_payloads.append(payload)
        return CanonicalReportSnapshot(REPORT_ID, snapshot_hash, snapshot_revision)


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.event_ids: list[str] = []
        self.payloads: list[dict[str, Any]] = []

    def record(
        self,
        node_name: str,
        result: Any,
        state: dict[str, Any],
        *,
        attempt_count: int = 1,
        retry_count: int = 0,
        duration_ms: int | float | None = None,
        checkpoint_id: str | None = None,
        checkpoint_hash: str | None = None,
        tool: str | None = None,
    ) -> None:
        self.events.append(node_name)
        self.event_ids.append(f"{node_name}-{len(self.event_ids)}")
        self.payloads.append(
            {
                "node_name": node_name,
                "status": getattr(getattr(result, "status", None), "value", str(result)),
                "data_refs": list(getattr(result, "data_refs", [])),
                "errors": list(getattr(result, "errors", [])),
                "case_id": state.get("case_id"),
                "run_id": state.get("run_id"),
                "correlation_id": state.get("correlation_id"),
                "error_code": state.get("error_code")
                or next(iter(getattr(result, "errors", [])), None),
                "attempt": attempt_count,
                "attempt_count": attempt_count,
                "retry_count": retry_count,
                "latency_ms": duration_ms,
                "checkpoint_id": checkpoint_id,
                "checkpoint_hash": checkpoint_hash,
                "tool": tool,
                "fallback_used": getattr(result, "fallback_used", None),
            }
        )

    def serialized(self) -> str:
        return repr(self.payloads)


class FakeTracer:
    allowed_keys = {
        "node_name",
        "agent_role",
        "workflow_type",
        "status",
        "duration_ms",
        "schema_version",
        "fallback_used",
        "case_id",
        "run_id",
        "correlation_id",
        "retry_count",
        "attempt",
        "latency_ms",
        "checkpoint_id",
        "checkpoint_hash",
        "gate",
        "gate_status",
        "report_id",
        "report_revision",
        "report_checksum",
        "tool",
    }

    def __init__(self) -> None:
        self.spans: list[dict[str, Any]] = []
        self.checkpoint_keys: set[str] = set()

    def record(self, **attributes: Any) -> None:
        self.spans.append(attributes)

    def record_checkpoint_keys(self, keys: set[str]) -> None:
        self.checkpoint_keys = set(keys)

    def serialized(self) -> str:
        return repr(self.spans)


class WorkflowFixtureError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(f"{code}:{RAW_SENTINEL}")
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class MetricCalculationProbe:
    calculation_id: str


class NodeResultProbe:
    status = type("StatusProbe", (), {"value": "success"})()
    data_refs = [CALCULATION_ID]
    errors: list[str] = []
    warnings: list[str] = []
    fallback_used = False


class FakeMetricContract:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | float, dict[str, object | None]]] = []

    def record(
        self,
        name: str,
        value: int | float,
        attributes: dict[str, object | None],
    ) -> None:
        self.calls.append((name, value, attributes))


@dataclass(frozen=True)
class IdProbe:
    id: str
    value_type: str = "decimal"
    metadata: dict[str, object] | None = None


class RepositoryProbe:
    def __init__(self, records: list[IdProbe]) -> None:
        self._records = records
        self.calls: list[UUID] = []

    def list_for_case(self, case_id: UUID) -> list[IdProbe]:
        self.calls.append(case_id)
        return list(self._records)


class ReportDraftRepositoryProbe:
    def __init__(self) -> None:
        self.snapshots: list[ReportSnapshot] = []

    def add_snapshot(self, snapshot: ReportSnapshot) -> None:
        self.snapshots.append(snapshot)


class ProviderFindingProbe:
    def __init__(self, finding: Finding) -> None:
        self.finding = finding

    def analyze(
        self,
        *,
        case_id: str,
        node_name: str,
        disclosure_scope: object | None,
        remaining_evidence_fact_ids: list[str],
        remaining_calculation_ids: list[str],
        invalidated_ids: list[str],
    ) -> dict[str, Any]:
        del case_id, node_name, disclosure_scope, remaining_evidence_fact_ids, remaining_calculation_ids, invalidated_ids
        return {"findings": [self.finding]}


class ProviderStructuredClaimProbe:
    def __init__(self) -> None:
        self.observed_evidence_fact_ids: list[str] = []

    def analyze(
        self,
        *,
        case_id: str,
        node_name: str,
        disclosure_scope: object | None,
        remaining_evidence_fact_ids: list[str],
        remaining_calculation_ids: list[str],
        invalidated_ids: list[str],
    ) -> dict[str, Any]:
        del disclosure_scope, remaining_calculation_ids, invalidated_ids
        self.observed_evidence_fact_ids = list(remaining_evidence_fact_ids)
        if not remaining_evidence_fact_ids:
            return {"finding_ids": []}
        return {
            "findings": [
                _finding(
                    uuid4(),
                    UUID(case_id),
                    (UUID(remaining_evidence_fact_ids[0]),),
                    (),
                ).model_copy(update={"author_node": node_name})
            ]
        }


class ProviderCallProbe:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def analyze(
        self,
        *,
        case_id: str,
        node_name: str,
        disclosure_scope: object | None,
        remaining_evidence_fact_ids: list[str],
        remaining_calculation_ids: list[str],
        invalidated_ids: list[str],
    ) -> dict[str, Any]:
        del case_id, disclosure_scope, remaining_evidence_fact_ids, remaining_calculation_ids, invalidated_ids
        self.calls.append(node_name)
        return {"finding_ids": ["provider-should-not-run"]}


class ProviderRawIdProbe:
    def __init__(self, finding_id: str) -> None:
        self.finding_id = finding_id

    def analyze(
        self,
        *,
        case_id: str,
        node_name: str,
        disclosure_scope: object | None,
        remaining_evidence_fact_ids: list[str],
        remaining_calculation_ids: list[str],
        invalidated_ids: list[str],
    ) -> dict[str, Any]:
        del case_id, node_name, disclosure_scope, remaining_evidence_fact_ids, remaining_calculation_ids, invalidated_ids
        return {"finding_ids": [self.finding_id]}


class ParsedBlockParserProbe:
    def __init__(self, blocks: list[TextBlock]) -> None:
        self._blocks = blocks

    def text_blocks(self, parsed_artifact_ids: list[str]) -> list[TextBlock]:
        del parsed_artifact_ids
        return list(self._blocks)


class DurableWorkflowStore:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}

    def load(self, case_id: str) -> dict[str, Any]:
        return dict(self.records.get(case_id, {}))

    def save(self, case_id: str, values: dict[str, Any]) -> None:
        current = dict(self.records.get(case_id, {}))
        current.update(values)
        self.records[case_id] = current


def _local_repositories(path: Path) -> dict[str, Any]:
    database = SQLiteDatabase(path)
    artifact_repository = LocalArtifactRepository(database)
    evidence_repository = LocalEvidenceRepository(database)
    calculation_repository = LocalCalculationRepository(database)
    finding_repository = LocalFindingRepository(database)
    contradiction_repository = LocalContradictionRepository(database)
    approval_repository = LocalApprovalRepository(database)
    decision_repository = LocalContradictionDecisionRepository(database)
    report_repository = LocalReportRepository(database)
    startup_claim_repository = LocalStartupClaimRepository(database)
    startup_profile_repository = LocalStartupProfileRepository(database)
    return {
        "database": database,
        "case": LocalCaseRepository(database),
        "artifact": artifact_repository,
        "evidence": evidence_repository,
        "calculation": calculation_repository,
        "finding": finding_repository,
        "startup_claim": startup_claim_repository,
        "startup_profile": startup_profile_repository,
        "contradiction": contradiction_repository,
        "approval": approval_repository,
        "report": report_repository,
        "review": LocalReviewRepository(
            artifact_repository=artifact_repository,
            evidence_repository=evidence_repository,
            calculation_repository=calculation_repository,
            finding_repository=finding_repository,
            contradiction_repository=contradiction_repository,
            report_repository=report_repository,
            approval_repository=approval_repository,
            decision_repository=decision_repository,
        ),
    }


def _startup_report_adapter(
    repos: dict[str, Any],
    root: Path,
    *,
    current_data_revision: Any | None = None,
    workflow_store: Any | None = None,
    audit_spool: AuditSpool | None = None,
) -> StartupReportRepositoryAdapter:
    revision = current_data_revision or repos["review"].current_data_revision
    _seed_report_profile_if_case_exists(repos)
    if audit_spool is None:
        seeded_spool = JsonlAuditSpool(root / "report-test-audit", max_mb=1)
        AuditSpoolNodeAudit(seeded_spool).record(
            "fixture",
            NodeResultProbe(),
            {
                "case_id": CASE_ID,
                "run_id": "startup-test-report",
                "correlation_id": CORRELATION_ID,
            },
            checkpoint_id="startup-fixture-000000000001",
            checkpoint_hash="f" * 64,
        )
        audit_spool = seeded_spool
    report_service = ReportService(
        approval_repository=repos["approval"],
        current_data_revision=revision,
        report_repository=repos["report"],
    )
    return StartupReportRepositoryAdapter(
        case_repository=repos["case"],
        startup_claim_repository=repos["startup_claim"],
        evidence_repository=repos["evidence"],
        calculation_repository=repos["calculation"],
        finding_repository=repos["finding"],
        contradiction_repository=repos["contradiction"],
        startup_profile_repository=repos["startup_profile"],
        report_repository=repos["report"],
        approval_repository=repos["approval"],
        current_data_revision=revision,
        report_service=report_service,
        output_dir=root / "reports",
        workflow_store=workflow_store,
        audit_spool=audit_spool,
    )


def _seed_report_profile_if_case_exists(repos: dict[str, Any]) -> None:
    case_id = UUID(CASE_ID)
    try:
        case = repos["case"].get(case_id)
    except KeyError:
        return
    if repos["startup_profile"].list_for_case(case_id):
        return
    repos["startup_profile"].add(
        _startup_profile(
            case_id,
            data_revision=case.data_revision,
            case_revision_at=case.updated_at,
        )
    )


def _profile_refs(repos: dict[str, Any], case_id: UUID) -> dict[str, str | int]:
    profile = repos["startup_profile"].get_current(case_id)
    return {
        "profile_id": str(profile.profile_id),
        "profile_hash": profile.profile_hash,
        "profile_revision": profile.data_revision,
    }


def _persist_report_lineage(
    repos: dict[str, Any],
    case_id: UUID,
    *,
    include_excluded: bool,
) -> dict[str, str | int | list[str]]:
    artifact_id = uuid4()
    selected_fact_id = UUID(REVENUE_FACT_ID)
    selected_calculation_id = UUID(CALCULATION_ID)
    selected_finding_id = UUID(FINDING_ID)
    selected_contradiction_id = UUID(CONTRADICTION_ID)
    selected_claim_id = UUID("60000000-0000-0000-0000-000000000901")
    repos["case"].add(_case(case_id))
    _seed_report_profile_if_case_exists(repos)
    repos["artifact"].add(_artifact(case_id, artifact_id))
    selected_claim = _startup_claim(
        case_id,
        artifact_id,
        normalized_name="arr",
        normalized_value=Decimal("100.00"),
        unit="USD",
        period="FY2026",
    ).model_copy(update={"id": selected_claim_id})
    repos["startup_claim"].add(selected_claim)
    repos["evidence"].add(_fact(selected_fact_id, artifact_id, "arr"))
    repos["calculation"].add(
        _calculation(selected_calculation_id, case_id, (selected_fact_id,))
    )
    repos["finding"].add(
        _finding(
            selected_finding_id,
            case_id,
            (selected_fact_id,),
            (selected_calculation_id,),
        )
    )
    repos["contradiction"].add(
        _contradiction(
            selected_contradiction_id,
            case_id,
            (selected_fact_id,),
            (selected_finding_id,),
        )
    )
    ids: dict[str, Any] = {
        **_profile_refs(repos, case_id),
        "startup_claim_ids": [str(selected_claim_id)],
        "evidence_fact_ids": [str(selected_fact_id)],
        "calculation_ids": [str(selected_calculation_id)],
        "finding_ids": [str(selected_finding_id)],
        "contradiction_ids": [str(selected_contradiction_id)],
    }
    if not include_excluded:
        return ids

    excluded_fact_id = UUID(COGS_FACT_ID)
    excluded_calculation_id = UUID("20000000-0000-0000-0000-000000000902")
    excluded_finding_id = UUID("30000000-0000-0000-0000-000000000902")
    excluded_contradiction_id = UUID("40000000-0000-0000-0000-000000000902")
    excluded_claim_id = UUID("60000000-0000-0000-0000-000000000902")
    excluded_claim = _startup_claim(
        case_id,
        artifact_id,
        normalized_name="runway",
        normalized_value=Decimal("18.00"),
        unit="months",
        period="FY2026",
    ).model_copy(update={"id": excluded_claim_id})
    repos["startup_claim"].add(excluded_claim)
    repos["evidence"].add(_fact(excluded_fact_id, artifact_id, "runway"))
    repos["calculation"].add(
        _calculation(excluded_calculation_id, case_id, (excluded_fact_id,)).model_copy(
            update={"metric_name": "burn_multiple"}
        )
    )
    repos["finding"].add(
        _finding(
            excluded_finding_id,
            case_id,
            (excluded_fact_id,),
            (excluded_calculation_id,),
        ).model_copy(update={"claim": "Excluded runway concern must not affect report."})
    )
    repos["contradiction"].add(
        _contradiction(
            excluded_contradiction_id,
            case_id,
            (excluded_fact_id,),
            (excluded_finding_id,),
        ).model_copy(update={"conflict_type": "excluded_conflict"})
    )
    return {
        **ids,
        "startup_claim_ids": [*ids["startup_claim_ids"], str(excluded_claim_id)],
        "evidence_fact_ids": [*ids["evidence_fact_ids"], str(excluded_fact_id)],
        "calculation_ids": [*ids["calculation_ids"], str(excluded_calculation_id)],
        "finding_ids": [*ids["finding_ids"], str(excluded_finding_id)],
        "contradiction_ids": [*ids["contradiction_ids"], str(excluded_contradiction_id)],
    }


def _case(case_id: UUID) -> DueDiligenceCase:
    now = datetime(2026, 8, 12, tzinfo=UTC)
    return DueDiligenceCase(
        case_id=case_id,
        mode=AnalysisMode.STARTUP,
        entity_name="FounderCo",
        entity_identifier="founderco",
        jurisdiction="US",
        scope=("startup",),
        as_of=now,
        base_currency="USD",
        privacy_policy="startup-local@1",
        budget_policy="stage1b-local@1",
        status=CaseStatus.CREATED,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=now,
        updated_at=now,
        workflow_version="startup-task9@1",
    )


def _startup_profile(
    case_id: UUID,
    *,
    data_revision: int = 1,
    case_revision_at: datetime | None = None,
) -> StartupProfile:
    now = case_revision_at or datetime(2026, 8, 12, tzinfo=UTC)
    return StartupProfile.build(
        case_id=case_id,
        schema_version="startup-profile-schema@1",
        profile_version="startup-profile@1",
        extractor_version="test-profile@1",
        analysis_stage=StartupProfileAnalysisStage.PRIMARY,
        parent_profile_id=None,
        data_revision=data_revision,
        source_hashes={str(case_id): "sha256:" + "c" * 64},
        parse_outcomes={str(case_id): "parsed"},
        fields={
            field.value: StartupProfileField(
                name=field,
                status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
                confidence=Decimal("0"),
                reason_code="test_fixture",
            )
            for field in StartupProfileFieldName
        },
        gap_codes=("test_fixture_profile",),
        contradiction_ids=(),
        case_revision_at=now,
    )


def _artifact(case_id: UUID, artifact_id: UUID) -> Artifact:
    return Artifact(
        id=artifact_id,
        case_id=case_id,
        content_hash="a" * 64,
        mime_type="application/pdf",
        source="startup-dataroom",
        source_url=None,
        normalized_query=(),
        retrieved_at=datetime(2026, 8, 12, tzinfo=UTC),
        published_at=None,
        filing_acceptance_at=None,
        effective_at=None,
        source_snapshot_hash="b" * 64,
        storage_ref="artifact://pitch",
        parsing_status=ArtifactParsingStatus.PARSED,
        sensitivity=SensitivityClass.CONFIDENTIAL,
    )


def _fact(fact_id: UUID, artifact_id: UUID, name: str, *, metadata: dict[str, str] | None = None) -> EvidenceFact:
    return EvidenceFact(
        id=fact_id,
        artifact_id=artifact_id,
        name=name,
        value=Decimal("100.00"),
        value_type="decimal",
        unit="USD",
        period="FY2026",
        locator=SourceLocator(kind="startup_fact", value=name, artifact_id=artifact_id),
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=Decimal("0.90"),
        source_priority=1,
        extraction_method="startup-parser",
        supporting_text_hash="sha256:" + "c" * 64,
        source_freshness_at=datetime(2026, 8, 12, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 12, tzinfo=UTC),
        metadata=metadata or {},
    )


def _calculation(calculation_id: UUID, case_id: UUID, input_fact_ids: tuple[UUID, ...]) -> Calculation:
    return Calculation(
        id=calculation_id,
        case_id=case_id,
        metric_name="gross_margin",
        formula_version="startup-gross-margin@1",
        input_fact_ids=input_fact_ids,
        value=Decimal("0.400000"),
        unit="ratio",
        period="FY2026",
        warnings=(),
        calculated_at=datetime(2026, 8, 12, tzinfo=UTC),
        sensitivity=SensitivityClass.CONFIDENTIAL,
    )


def _startup_claim(
    case_id: UUID,
    artifact_id: UUID,
    *,
    normalized_name: str,
    normalized_value: Decimal,
    unit: str,
    period: str,
) -> StartupClaim:
    return StartupClaim(
        id=uuid4(),
        case_id=case_id,
        text_ref="d" * 64,
        text_hash="d" * 64,
        category=ClaimCategory(normalized_name),
        source_artifact_id=artifact_id,
        locator=SourceLocator(kind="startup_claim", value=normalized_name, artifact_id=artifact_id),
        criticality=ClaimCriticality.CRITICAL,
        evidence_query=f"{normalized_name} {period}",
        normalized_name=normalized_name,
        normalized_value=normalized_value,
        unit=unit,
        period=period,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=Decimal("0.80"),
        extracted_at=datetime(2026, 8, 12, tzinfo=UTC),
    )


def _finding(
    finding_id: UUID,
    case_id: UUID,
    fact_ids: tuple[UUID, ...],
    calculation_ids: tuple[UUID, ...],
) -> Finding:
    return Finding(
        id=finding_id,
        case_id=case_id,
        category="financial",
        severity=FindingSeverity.HIGH,
        claim="Unit economics depend on excluded revenue fact.",
        evidence_fact_ids=fact_ids,
        calculation_ids=calculation_ids,
        confidence=Decimal("0.80"),
        status=FindingStatus.VERIFIED,
        counter_evidence_fact_ids=(),
        author_node="financial_analysis",
        author_model="startup-provider@fixture",
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=datetime(2026, 8, 12, tzinfo=UTC),
    )


def _contradiction(
    contradiction_id: UUID,
    case_id: UUID,
    fact_ids: tuple[UUID, ...],
    finding_ids: tuple[UUID, ...],
) -> Contradiction:
    return Contradiction(
        id=contradiction_id,
        case_id=case_id,
        conflict_type="metric_vs_claim",
        fact_ids=fact_ids,
        finding_ids=finding_ids,
        explanation="Excluded fact invalidates finding support.",
        severity=FindingSeverity.MEDIUM,
        status=ContradictionStatus.OPEN,
        recommended_resolution="exclude dependent outputs",
        resolved_by_approval_id=None,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        detected_at=datetime(2026, 8, 12, tzinfo=UTC),
    )


def _report_snapshot(report_id: UUID, case_id: UUID) -> ReportSnapshot:
    return ReportSnapshot(
        id=report_id,
        case_id=case_id,
        report_hash="sha256:report",
        case_snapshot_hash="sha256:case",
        source_hashes={},
        as_of=datetime(2026, 8, 12, tzinfo=UTC),
        graph_version="startup-task9@1",
        prompt_versions={},
        formula_versions={},
        model_versions={},
        trace_ids=(),
        sections={"draft": True},
        json_artifact_ref="startup-report-draft://existing",
        html_artifact_ref=None,
        pdf_artifact_ref=None,
        content_hashes={"json": "sha256:json"},
        reproducibility=ReproducibilityManifest(
            code_commit="task9",
            build_id="test",
            dependency_lock_hash="sha256:lock",
            python_version="3.12",
            package_versions={},
            provider_model_id="none",
            model_alias_snapshot="startup-task9@1",
            reasoning_parameters={},
            adapter_versions={},
            parser_versions={},
            embedding_model_version=None,
            index_version=None,
            redaction_policy_version="startup-redaction@1",
            locale="en-US",
            timezone="UTC",
            fx_source=None,
            deterministic_seeds={},
            configuration_hash="sha256:config",
        ),
        sensitivity=SensitivityClass.CONFIDENTIAL,
        created_at=datetime(2026, 8, 12, tzinfo=UTC),
    )


def _startup_report_snapshot(
    report_id: UUID,
    case_id: UUID,
    *,
    revision: int,
    report_hash: str,
) -> ReportSnapshot:
    return _report_snapshot(report_id, case_id).model_copy(
        update={
            "report_hash": report_hash,
            "prompt_versions": {"report": "startup-report-template@1"},
            "data_revision": revision,
        }
    )


def _docx_bytes(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def _write_text_pdf_fixture(path: Path, lines: tuple[str, ...]) -> None:
    import pymupdf

    document = pymupdf.open()
    try:
        page = document.new_page()
        for line_number, line in enumerate(lines):
            page.insert_text(
                pymupdf.Point(36, 50 + line_number * 28),
                line,
                fontname="helv",
                fontsize=10,
            )
        document.save(path)
    finally:
        document.close()


def _stored_text_block(
    artifact_store: LocalArtifactStore,
    *,
    artifact_id: UUID,
    text: str,
) -> TextBlock:
    stored = artifact_store.put_bytes(
        text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        artifact_id=artifact_id,
        source_snapshot_hash="f" * 64,
        sensitivity=SensitivityClass.CONFIDENTIAL,
    )
    return TextBlock(
        text_ref=stored.content_hash,
        content_hash=stored.content_hash,
        char_count=len(text),
        locator=SourceLocator(kind="test_text", value="paragraph:1", artifact_id=artifact_id),
        confidence=Decimal("1"),
        verification_status="verified",
    )
