from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from due_diligence_agent.workflows.startup.nodes.claims import claims
from due_diligence_agent.workflows.startup.nodes.evidence import evidence
from due_diligence_agent.workflows.startup.runtime import (
    InMemoryStartupWorkflowRuntimeStore,
)


CASE_ID = "00000000-0000-0000-0000-000000000791"
SOURCE_CONTRADICTION_ID = "40000000-0000-0000-0000-000000000791"
SECOND_SOURCE_CONTRADICTION_ID = "40000000-0000-0000-0000-000000000792"
CLAIM_CONTRADICTION_ID = "40000000-0000-0000-0000-000000000793"


def test_evidence_node_carries_ordered_unique_source_contradiction_ids() -> None:
    dependencies = _EvidenceDependencies()

    result = evidence(
        {"case_id": CASE_ID, "parsed_artifact_ids": ["parsed-a", "parsed-b"]},
        dependencies=dependencies,
    )

    assert result == {
        "evidence_fact_ids": ["fact-a", "fact-b"],
        "contradiction_ids": [
            SOURCE_CONTRADICTION_ID,
            SECOND_SOURCE_CONTRADICTION_ID,
        ],
    }


def test_claims_node_unions_source_and_claim_contradictions_and_persists_union() -> None:
    dependencies = _ClaimsDependencies()
    state = {
        "case_id": CASE_ID,
        "evidence_fact_ids": ["fact-a", "fact-b"],
        "contradiction_ids": [
            SOURCE_CONTRADICTION_ID,
            SECOND_SOURCE_CONTRADICTION_ID,
        ],
    }

    result = claims(state, dependencies=dependencies)

    expected_ids = [
        SOURCE_CONTRADICTION_ID,
        SECOND_SOURCE_CONTRADICTION_ID,
        CLAIM_CONTRADICTION_ID,
    ]
    assert result["contradiction_ids"] == expected_ids
    runtime = dependencies.workflow_store.load(CASE_ID)
    assert runtime["contradiction_ids"] == expected_ids
    assert runtime["has_contradictions"] is True


class _EvidencePort:
    def extract(self, *, case_id: str, parsed_artifact_ids: list[str]) -> dict[str, Any]:
        assert case_id == CASE_ID
        assert parsed_artifact_ids == ["parsed-a", "parsed-b"]
        return {
            "evidence_fact_ids": ["fact-a", "fact-b"],
            "contradiction_ids": [
                UUID(SOURCE_CONTRADICTION_ID),
                UUID(SOURCE_CONTRADICTION_ID),
                UUID(SECOND_SOURCE_CONTRADICTION_ID),
            ],
        }


class _LineagePort:
    def derive(self, *, case_id: str, evidence_fact_ids: list[str]) -> dict[str, Any]:
        assert case_id == CASE_ID
        assert evidence_fact_ids == ["fact-a", "fact-b"]
        return {"dependency_edges": {}, "dependency_node_edges": {}}


class _ClaimsPort:
    def extract(self, *, case_id: str, evidence_fact_ids: list[str]) -> dict[str, Any]:
        assert case_id == CASE_ID
        assert evidence_fact_ids == ["fact-a", "fact-b"]
        return {
            "startup_claim_ids": ["claim-a"],
            "contradiction_ids": [
                UUID(SECOND_SOURCE_CONTRADICTION_ID),
                UUID(CLAIM_CONTRADICTION_ID),
                UUID(CLAIM_CONTRADICTION_ID),
            ],
            "claim_status_by_id": {"claim-a": "contradicted"},
            "claim_matrix_summary": [],
        }


@dataclass
class _EvidenceDependencies:
    evidence: _EvidencePort = field(default_factory=_EvidencePort)
    lineage: _LineagePort = field(default_factory=_LineagePort)
    workflow_store: InMemoryStartupWorkflowRuntimeStore = field(
        default_factory=InMemoryStartupWorkflowRuntimeStore
    )


@dataclass
class _ClaimsDependencies:
    claims: _ClaimsPort = field(default_factory=_ClaimsPort)
    workflow_store: InMemoryStartupWorkflowRuntimeStore = field(
        default_factory=InMemoryStartupWorkflowRuntimeStore
    )
