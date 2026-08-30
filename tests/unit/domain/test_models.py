from datetime import UTC, datetime
from decimal import Decimal
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
from due_diligence_agent.domain.reports.models import ReportSnapshot, ReproducibilityManifest
from due_diligence_agent.workflows.shared.node_result import NodeResult, NodeStatus


def test_evidence_requires_period_and_unit_for_numeric_value():
    with pytest.raises(ValueError, match="period and unit"):
        EvidenceFact(
            id=uuid4(),
            artifact_id=uuid4(),
            name="revenue",
            value=Decimal("10"),
            value_type="decimal",
            unit=None,
            period=None,
            locator=SourceLocator(kind="sec_fact", value="Revenue"),
            sensitivity=SensitivityClass.PUBLIC,
            confidence=Decimal("1"),
        )


def test_node_result_has_typed_partial_status():
    result = NodeResult[list[str]](
        status=NodeStatus.PARTIAL, data=["fact-1"], warnings=["stale"]
    )
    assert result.status is NodeStatus.PARTIAL
    assert result.data == ["fact-1"]


def test_node_result_default_lists_are_independent():
    first = NodeResult[None](status=NodeStatus.SUCCESS)
    second = NodeResult[None](status=NodeStatus.SUCCESS)

    first.warnings.append("first-only")

    assert second.warnings == []


def test_domain_models_are_immutable_and_reject_naive_timestamps():
    fact = EvidenceFact(
        id=uuid4(),
        artifact_id=uuid4(),
        name="revenue",
        value=Decimal("10"),
        value_type="decimal",
        unit="USD",
        period="FY2025",
        locator=SourceLocator(kind="sec_fact", value="Revenue"),
        sensitivity=SensitivityClass.PUBLIC,
        confidence=Decimal("0.95"),
        retrieved_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )

    with pytest.raises(ValidationError):
        fact.name = "assets"

    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        EvidenceFact(
            id=uuid4(),
            artifact_id=uuid4(),
            name="assets",
            value=Decimal("20"),
            value_type="decimal",
            unit="USD",
            period="FY2025",
            locator=SourceLocator(kind="sec_fact", value="Assets"),
            sensitivity=SensitivityClass.PUBLIC,
            confidence=Decimal("0.90"),
            retrieved_at=datetime(2026, 1, 2, 3, 4, 5),
        )


def test_financial_canonical_values_reject_float_inputs():
    with pytest.raises(ValidationError, match="Decimal"):
        EvidenceFact(
            id=uuid4(),
            artifact_id=uuid4(),
            name="revenue",
            value=10.1,
            value_type="decimal",
            unit="USD",
            period="FY2025",
            locator=SourceLocator(kind="sec_fact", value="Revenue"),
            sensitivity=SensitivityClass.PUBLIC,
            confidence=Decimal("0.90"),
        )

    with pytest.raises(ValidationError, match="Decimal"):
        Calculation(
            id=uuid4(),
            case_id=uuid4(),
            metric_name="revenue_growth",
            formula_version="revenue-growth@1",
            input_fact_ids=[uuid4()],
            value=1.5,
            unit="percent",
            period="FY2025",
            warnings=[],
            calculated_at=datetime(2026, 1, 2, tzinfo=UTC),
            sensitivity=SensitivityClass.PUBLIC,
            version=1,
        )


def test_report_snapshot_contains_manifest_hashes_and_no_raw_source_text():
    snapshot = _make_report_snapshot()

    dumped = snapshot.model_dump()
    assert dumped["reproducibility"]["dependency_lock_hash"] == "sha256:lock"
    assert dumped["content_hashes"] == {"json": "sha256:json", "html": "sha256:html"}
    assert "raw_source_text" not in dumped
    assert "raw_documents" not in dumped


def test_report_snapshot_and_manifest_mapping_fields_are_immutable():
    snapshot = _make_report_snapshot()
    manifest = snapshot.reproducibility

    mapping_fields = [
        (snapshot.source_hashes, "10-k", "sha256:mutated"),
        (snapshot.prompt_versions, "synthesis", "mutated"),
        (snapshot.formula_versions, "revenue_growth", "mutated"),
        (snapshot.model_versions, "analysis", "mutated"),
        (snapshot.content_hashes, "json", "sha256:mutated"),
        (manifest.package_versions, "pydantic", "mutated"),
        (manifest.reasoning_parameters, "effort", "high"),
        (manifest.adapter_versions, "sec", "mutated"),
        (manifest.parser_versions, "xbrl", "mutated"),
        (manifest.deterministic_seeds, "report", 2),
    ]

    for mapping, key, mutated_value in mapping_fields:
        with pytest.raises(TypeError):
            mapping[key] = mutated_value


def test_report_snapshot_mapping_fields_round_trip_as_json_objects():
    snapshot = _make_report_snapshot()

    json_text = snapshot.model_dump_json()
    dumped = json.loads(json_text)
    restored = ReportSnapshot.model_validate_json(json_text)

    assert isinstance(dumped["source_hashes"], dict)
    assert isinstance(dumped["content_hashes"], dict)
    assert isinstance(dumped["reproducibility"]["package_versions"], dict)
    assert isinstance(dumped["reproducibility"]["adapter_versions"], dict)
    assert restored == snapshot
    with pytest.raises(TypeError):
        restored.source_hashes["10-k"] = "sha256:mutated"


def _make_report_snapshot() -> ReportSnapshot:
    manifest = ReproducibilityManifest(
        code_commit="abc123",
        build_id="local",
        dependency_lock_hash="sha256:lock",
        python_version="3.12.0",
        package_versions={"pydantic": "2.13.4"},
        provider_model_id="openai/gpt-5.5",
        model_alias_snapshot="public-analysis@1",
        reasoning_parameters={"effort": "medium"},
        adapter_versions={"sec": "sec-adapter@1"},
        parser_versions={"xbrl": "xbrl-parser@1"},
        embedding_model_version="sentence-transformers/all-MiniLM-L6-v2",
        index_version="faiss@1",
        redaction_policy_version="egress@1",
        locale="en-US",
        timezone="UTC",
        fx_source="none",
        deterministic_seeds={"report": 1},
        configuration_hash="sha256:config",
    )

    return ReportSnapshot(
        id=uuid4(),
        case_id=uuid4(),
        report_hash="sha256:report",
        case_snapshot_hash="sha256:case",
        source_hashes={"10-k": "sha256:filing"},
        as_of=datetime(2026, 6, 30, tzinfo=UTC),
        graph_version="public-graph@1",
        prompt_versions={"synthesis": "prompt@1"},
        formula_versions={"revenue_growth": "formula@1"},
        model_versions={"analysis": "openai/gpt-5.5"},
        trace_ids=["trace-1"],
        json_artifact_ref="artifact://json",
        html_artifact_ref="artifact://html",
        pdf_artifact_ref=None,
        content_hashes={"json": "sha256:json", "html": "sha256:html"},
        reproducibility=manifest,
        sensitivity=SensitivityClass.PUBLIC,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
        version=1,
    )
