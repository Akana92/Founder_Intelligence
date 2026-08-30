from __future__ import annotations

from pathlib import Path
from collections.abc import Callable
from typing import Any, Final

from due_diligence_agent.adapters.documents.no_network_guard import NoNetworkGuard
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.privacy.models import (
    PrivacyDetection,
    PrivacyScanResult,
    counts_for_detections,
    most_restrictive,
    redact_with_detections,
)


POLICY_VERSION: Final[str] = "startup-presidio-local@1"


class PresidioRedactor:
    policy_version = POLICY_VERSION

    def __init__(
        self,
        *,
        local_model_path: Path | None,
        analyzer_factory: Callable[[], object] | None = None,
    ) -> None:
        self._local_model_path = local_model_path
        self._analyzer_factory = analyzer_factory
        self._analyzer: Any | None = None

    def detect(
        self,
        text: str,
        *,
        existing: PrivacyScanResult,
    ) -> PrivacyScanResult:
        analyzer = self._load_analyzer()
        if analyzer is None:
            return PrivacyScanResult(
                detections=existing.detections,
                redacted_text=existing.redacted_text,
                sensitivity=existing.sensitivity,
                available=False,
                reason="presidio_unavailable",
                policy_version=self.policy_version,
            )

        additional = self._detect_with_analyzer(analyzer, text)
        if additional is None:
            return PrivacyScanResult(
                detections=existing.detections,
                category_counts=existing.category_counts,
                redacted_text=existing.redacted_text,
                sensitivity=existing.sensitivity,
                available=False,
                reason="presidio_unavailable",
                policy_version=self.policy_version,
            )
        if additional == "invalid_span":
            return PrivacyScanResult(
                detections=existing.detections,
                category_counts=existing.category_counts,
                redacted_text=existing.redacted_text,
                sensitivity=existing.sensitivity,
                available=False,
                reason="presidio_invalid_span",
                policy_version=self.policy_version,
            )
        detections = tuple([*existing.detections, *additional])
        sensitivity = most_restrictive([existing.sensitivity, *(item.sensitivity for item in detections)])
        return PrivacyScanResult(
            detections=detections,
            category_counts=counts_for_detections(detections),
            redacted_text=redact_with_detections(text, detections),
            sensitivity=sensitivity,
            policy_version=self.policy_version,
        )

    def _load_analyzer(self) -> Any | None:
        if self._local_model_path is None or not self._local_model_path.exists():
            return None
        if self._analyzer is not None:
            return self._analyzer
        if self._analyzer_factory is None:
            return None
        try:
            with NoNetworkGuard():
                self._analyzer = self._analyzer_factory()
        except Exception:
            return None
        return self._analyzer

    @staticmethod
    def _detect_with_analyzer(analyzer: Any, text: str) -> tuple[PrivacyDetection, ...] | str | None:
        try:
            with NoNetworkGuard():
                results = analyzer.analyze(text=text, language="en")
        except Exception:
            return None
        detections: list[PrivacyDetection] = []
        for result in results:
            start = int(result.start)
            end = int(result.end)
            if start < 0 or end <= start or end > len(text):
                return "invalid_span"
            category = _map_entity(str(result.entity_type))
            detections.append(
                PrivacyDetection(
                    category=category,
                    sensitivity=SensitivityClass.RESTRICTED,
                    start=start,
                    end=end,
                    source="presidio",
                )
            )
        return tuple(detections)


def _map_entity(entity_type: str) -> str:
    normalized = entity_type.casefold()
    if "person" in normalized or "name" in normalized:
        return "person_name"
    if "email" in normalized:
        return "email"
    if "phone" in normalized:
        return "phone"
    if "iban" in normalized or "bank" in normalized:
        return "banking"
    return "stable_id"
