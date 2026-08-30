from collections.abc import Iterable
from enum import IntEnum

from due_diligence_agent.domain.evidence.models import EvidenceFact


class SourcePriority(IntEnum):
    MODEL_INFERENCE = 10
    SECONDARY_AGGREGATOR = 20
    LICENSED_METADATA = 30
    MANAGEMENT_NARRATIVE = 40
    SYSTEM_EXPORT = 50
    OFFICIAL_OR_SIGNED = 60


CRITICAL_FINANCIAL_CATEGORIES = frozenset(
    {"valuation", "growth", "liquidity", "debt", "solvency"}
)


class SourcePriorityPolicy:
    def can_support_critical_claim(
        self, facts: Iterable[EvidenceFact], *, category: str
    ) -> bool:
        if _normalize_category(category) not in CRITICAL_FINANCIAL_CATEGORIES:
            return any(True for _ in facts)
        return any(
            fact.source_priority is not None
            and fact.source_priority >= SourcePriority.OFFICIAL_OR_SIGNED
            for fact in facts
        )


def _normalize_category(category: str) -> str:
    return category.strip().lower()
