from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from due_diligence_agent.application.policies.source_priority import SourcePriority
from due_diligence_agent.bootstrap.container import (
    _StartupEvidenceFromParsedDocumentsWorkflowPort,
)
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.documents.models import TextBlock
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.domain.findings.models import Contradiction


CASE_ID = UUID("00000000-0000-0000-0000-000000000781")


def test_startup_evidence_port_materializes_conflicts_after_all_facts_are_persisted() -> None:
    facts = (
        _fact(
            fact_id=UUID("20000000-0000-0000-0000-000000000781"),
            artifact_id=UUID("10000000-0000-0000-0000-000000000781"),
            value="720",
        ),
        _fact(
            fact_id=UUID("20000000-0000-0000-0000-000000000782"),
            artifact_id=UUID("10000000-0000-0000-0000-000000000782"),
            value="680",
        ),
    )
    evidence_repository = _EvidenceRepository()
    contradiction_repository = _ContradictionRepository()
    port = _StartupEvidenceFromParsedDocumentsWorkflowPort(
        evidence_repository,
        _ClaimRepository(),
        parser=_Parser(facts),
        contradiction_repository=contradiction_repository,
    )

    result = port.extract(case_id=str(CASE_ID), parsed_artifact_ids=["parsed-a", "parsed-b"])
    repeated = port.extract(case_id=str(CASE_ID), parsed_artifact_ids=["parsed-b", "parsed-a"])

    assert result["evidence_fact_ids"] == [str(fact.id) for fact in facts]
    assert repeated["evidence_fact_ids"] == result["evidence_fact_ids"]
    assert len(contradiction_repository.items) == 1
    assert result["contradiction_ids"] == [str(contradiction_repository.items[0].id)]
    assert repeated["contradiction_ids"] == result["contradiction_ids"]


def test_startup_evidence_port_marks_founder_clarification_as_accepted_source() -> None:
    artifact_id = UUID("10000000-0000-0000-0000-000000000783")
    text = (
        "Revenue Model: Use bank and invoice register for June 2026: recognized MRR is "
        "27.9m KZT; exclude CRM-only free-extension accounts. "
        "[[founder_clarification:accepted_source]]"
    )
    block = _text_block(text=text, artifact_id=artifact_id)
    evidence_repository = _EvidenceRepository()
    claim_repository = _ClaimRepository()
    port = _StartupEvidenceFromParsedDocumentsWorkflowPort(
        evidence_repository,
        claim_repository,
        parser=_Parser((), text_blocks=((block, text),)),
        contradiction_repository=_ContradictionRepository(),
    )

    port.extract(case_id=str(CASE_ID), parsed_artifact_ids=[str(artifact_id)])

    mrr_fact = next(
        fact
        for fact in evidence_repository.list_for_case(CASE_ID)
        if fact.name == "monthly_recurring_revenue"
    )
    assert mrr_fact.value == Decimal("27900000")
    assert mrr_fact.confidence == Decimal("0.95")
    assert mrr_fact.source_priority == SourcePriority.MANAGEMENT_NARRATIVE
    assert mrr_fact.extraction_method == "founder_clarification"
    assert mrr_fact.metadata["founder_clarification"] == "accepted_source"
    assert claim_repository.items


@dataclass(frozen=True)
class _Spreadsheet:
    evidence_facts: tuple[EvidenceFact, ...]


@dataclass(frozen=True)
class _Parsed:
    spreadsheet: _Spreadsheet


class _Parser:
    def __init__(
        self,
        facts: tuple[EvidenceFact, ...],
        *,
        text_blocks: tuple[tuple[TextBlock, str], ...] = (),
    ) -> None:
        self._parsed = _Parsed(_Spreadsheet(facts))
        self._text_blocks = tuple(block for block, _text in text_blocks)
        self._text_by_hash = {block.content_hash: text for block, text in text_blocks}

    def spreadsheets(self, parsed_artifact_ids: list[str]) -> list[_Parsed]:
        del parsed_artifact_ids
        return [self._parsed]

    def text_blocks(self, parsed_artifact_ids: list[str]) -> list[TextBlock]:
        del parsed_artifact_ids
        return list(self._text_blocks)

    def text_for_block(self, block: TextBlock) -> str:
        return self._text_by_hash[block.content_hash]


class _EvidenceRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, EvidenceFact] = {}

    def add(self, fact: EvidenceFact) -> None:
        if fact.id in self.items:
            raise ValueError("evidence_fact_already_exists")
        self.items[fact.id] = fact

    def list_for_case(self, case_id: UUID) -> list[EvidenceFact]:
        assert case_id == CASE_ID
        return list(self.items.values())


class _ClaimRepository:
    def __init__(self) -> None:
        self.items: list[object] = []

    def add(self, claim: object) -> None:
        self.items.append(claim)


class _ContradictionRepository:
    def __init__(self) -> None:
        self.items: list[Contradiction] = []

    def add(self, contradiction: Contradiction) -> None:
        if any(item.id == contradiction.id for item in self.items):
            raise ValueError("contradiction_already_exists")
        self.items.append(contradiction)

    def list_for_case(self, case_id: UUID) -> list[Contradiction]:
        return [item for item in self.items if item.case_id == case_id]


def _fact(*, fact_id: UUID, artifact_id: UUID, value: str) -> EvidenceFact:
    return EvidenceFact(
        id=fact_id,
        artifact_id=artifact_id,
        name="orders",
        value=Decimal(value),
        value_type="decimal",
        unit="count",
        period="2026-07",
        locator=SourceLocator(
            kind="csv_cell",
            value=f"orders!{fact_id}",
            artifact_id=artifact_id,
        ),
        sensitivity=SensitivityClass.CONFIDENTIAL,
        confidence=Decimal("0.80"),
        extraction_method="spreadsheet_parser",
        supporting_text_hash="b" * 64,
    )


def _text_block(*, text: str, artifact_id: UUID) -> TextBlock:
    content_hash = sha256(text.encode("utf-8")).hexdigest()
    return TextBlock(
        text_ref=content_hash,
        content_hash=content_hash,
        char_count=len(text),
        locator=SourceLocator(
            kind="docx_paragraph",
            value="paragraph:1",
            artifact_id=artifact_id,
        ),
        confidence=Decimal("1"),
        verification_status="verified",
    )
