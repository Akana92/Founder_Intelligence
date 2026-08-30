from __future__ import annotations

from hashlib import sha256
import re
from typing import Final
from uuid import NAMESPACE_URL, UUID, uuid5

from due_diligence_agent.adapters.local_storage.artifact_store import LocalArtifactStore
from due_diligence_agent.adapters.observability.privacy import PrimitiveTraceValue, StrictTraceSanitizer
from due_diligence_agent.adapters.privacy.rules_redactor import RulesRedactor
from due_diligence_agent.application.policies.data_egress import (
    DataEgressPolicy,
    EgressDecision,
    EgressFragment,
)
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.documents.models import TextBlock
from due_diligence_agent.domain.documents.tabular import NormalizedTable
from due_diligence_agent.domain.privacy.models import (
    DisclosurePreview,
    PrivacyDetection,
    PrivacyScanResult,
    RedactedContext,
    SensitivitySummary,
    counts_for_detections,
    merge_category_counts,
    most_restrictive,
    safe_field_id,
)


_PUBLIC_SOURCE_REDACTED_STILL_RESTRICTED_CATEGORIES: Final[frozenset[str]] = frozenset(
    {"banking", "secret"}
)


class StartupPrivacyService:
    def __init__(
        self,
        *,
        artifact_store: LocalArtifactStore,
        redactor: RulesRedactor,
        egress_policy: DataEgressPolicy,
        trace_sanitizer: StrictTraceSanitizer,
    ) -> None:
        self.artifact_store = artifact_store
        self._redactor = redactor
        self._egress_policy = egress_policy
        self._trace_sanitizer = trace_sanitizer

    @property
    def policy_version(self) -> str:
        return self._redactor.policy_version

    def classify(
        self,
        item: NormalizedTable | list[TextBlock],
        *,
        source_sensitivity: SensitivityClass = SensitivityClass.RESTRICTED,
    ) -> SensitivitySummary:
        scans = self._scan_item(item, source_sensitivity=source_sensitivity)
        field_classes = self._field_classes(item, scans)
        return SensitivitySummary(
            overall_class=most_restrictive([scan.sensitivity for scan in scans]),
            field_classes=field_classes,
            category_counts=merge_category_counts(scans),
            policy_version=self.policy_version,
        )

    def build_preview(
        self,
        blocks: list[TextBlock],
        *,
        source_sensitivity: SensitivityClass = SensitivityClass.RESTRICTED,
    ) -> DisclosurePreview:
        raw_texts = [self._raw_text_for_block(block) for block in blocks]
        scans = [
            self._scan_text(raw_text, source_sensitivity=source_sensitivity)
            for raw_text in raw_texts
        ]
        quasi_counts = self._quasi_identifier_counts(raw_texts)
        return DisclosurePreview(
            overall_class=most_restrictive([scan.sensitivity for scan in scans]),
            category_counts=merge_category_counts(scans),
            fragment_previews=tuple(self._minimize_preview(scan.redacted_text) for scan in scans),
            quasi_identifier_count=sum(quasi_counts.values()),
            quasi_identifier_counts=quasi_counts,
            policy_version=self.policy_version,
        )

    def redact_context(
        self,
        blocks: list[TextBlock],
        *,
        source_sensitivity: SensitivityClass = SensitivityClass.RESTRICTED,
    ) -> RedactedContext:
        scans = [self._scan_text_block(block, source_sensitivity=source_sensitivity) for block in blocks]
        refs: list[str] = []
        fragment_ids: list[UUID] = []
        residual_sensitivities: list[SensitivityClass] = []
        for block, scan in zip(blocks, scans, strict=True):
            payload = scan.redacted_text.encode("utf-8")
            residual_sensitivity = self._redacted_context_sensitivity(
                scan,
                source_sensitivity=source_sensitivity,
            )
            stored = self.artifact_store.put_bytes(
                payload,
                media_type="text/plain; charset=utf-8",
                artifact_id=block.locator.artifact_id,
                source_snapshot_hash=block.content_hash,
                sensitivity=residual_sensitivity,
            )
            refs.append(stored.content_hash)
            fragment_ids.append(uuid5(NAMESPACE_URL, f"{block.content_hash}:{stored.content_hash}"))
            residual_sensitivities.append(residual_sensitivity)
        content_hash = sha256("|".join(refs).encode("ascii")).hexdigest()
        return RedactedContext(
            fragment_ids=fragment_ids,
            local_text_refs=refs,
            sensitivity=most_restrictive(residual_sensitivities),
            redaction_counts=merge_category_counts(scans),
            content_hash=content_hash,
        )

    def evaluate_external_export(
        self,
        preview: DisclosurePreview,
        *,
        destination: str,
    ) -> EgressDecision:
        if preview.quasi_identifier_count >= 3:
            return EgressDecision(
                allowed=False,
                reason="reidentification_risk",
                policy_version=self._egress_policy.version,
                denied_fragment_ids=("preview",),
            )
        fragment = EgressFragment(
            id=uuid5(NAMESPACE_URL, f"preview:{preview.policy_version}:{destination}"),
            sensitivity=preview.overall_class,
            redacted=True,
            minimized=True,
            redaction_policy_version=preview.policy_version,
        )
        return self._egress_policy.evaluate([fragment], destination=destination)

    def trace_attributes_for_context(
        self,
        context: RedactedContext,
        *,
        status: str,
    ) -> dict[str, PrimitiveTraceValue]:
        attributes: dict[str, str | int] = {
            "redaction_policy_version": self.policy_version,
            "chunk_count": len(context.fragment_ids),
            "status": status,
            "artifact_hash": context.content_hash,
        }
        return self._trace_sanitizer.sanitize_attributes(attributes)

    def egress_fragments_for_context(self, context: RedactedContext) -> tuple[EgressFragment, ...]:
        return tuple(
            EgressFragment(
                id=fragment_id,
                sensitivity=context.sensitivity,
                redacted=True,
                minimized=True,
                redaction_policy_version=self.policy_version,
            )
            for fragment_id in context.fragment_ids
        )

    def _scan_item(
        self,
        item: NormalizedTable | list[TextBlock],
        *,
        source_sensitivity: SensitivityClass,
    ) -> list[PrivacyScanResult]:
        if isinstance(item, NormalizedTable):
            return [
                self._redactor.detect(
                    "" if cell.value is None else str(cell.value),
                    field_name=cell.label,
                    base_sensitivity=source_sensitivity,
                )
                for cell in item.cells
            ]
        return [self._scan_text_block(block, source_sensitivity=source_sensitivity) for block in item]

    def _field_classes(
        self,
        item: NormalizedTable | list[TextBlock],
        scans: list[PrivacyScanResult],
    ) -> dict[str, SensitivityClass]:
        if not isinstance(item, NormalizedTable):
            return {}
        field_classes: dict[str, SensitivityClass] = {}
        for cell, scan in zip(item.cells, scans, strict=True):
            if cell.label is not None:
                field_id = safe_field_id(cell.label)
                field_classes[field_id] = most_restrictive(
                    [field_classes.get(field_id, SensitivityClass.PUBLIC), scan.sensitivity]
                )
        return field_classes

    def _scan_text_block(
        self,
        block: TextBlock,
        *,
        source_sensitivity: SensitivityClass,
    ) -> PrivacyScanResult:
        return self._scan_text(self._raw_text_for_block(block), source_sensitivity=source_sensitivity)

    def _raw_text_for_block(self, block: TextBlock) -> str:
        payload = self.artifact_store.read_bytes(block.text_ref)
        return payload.decode("utf-8")

    def _scan_text(
        self,
        raw_text: str,
        *,
        source_sensitivity: SensitivityClass,
    ) -> PrivacyScanResult:
        if source_sensitivity is not SensitivityClass.PUBLIC:
            return self._whole_fragment_minimized_scan(raw_text, source_sensitivity)
        return self._redactor.detect(raw_text, base_sensitivity=source_sensitivity)

    def _whole_fragment_minimized_scan(
        self,
        raw_text: str,
        source_sensitivity: SensitivityClass,
    ) -> PrivacyScanResult:
        category = f"{source_sensitivity.value}_source"
        detection = PrivacyDetection(
            category=category,
            sensitivity=source_sensitivity,
            start=0,
            end=len(raw_text),
            source="source_sensitivity",
        )
        return PrivacyScanResult(
            detections=(detection,),
            category_counts=counts_for_detections((detection,)),
            redacted_text=f"[REDACTED:{category}:1]",
            sensitivity=source_sensitivity,
            policy_version=self.policy_version,
        )

    @staticmethod
    def _redacted_context_sensitivity(
        scan: PrivacyScanResult,
        *,
        source_sensitivity: SensitivityClass,
    ) -> SensitivityClass:
        if source_sensitivity is not SensitivityClass.PUBLIC:
            return scan.sensitivity
        categories = {detection.category for detection in scan.detections}
        if categories & _PUBLIC_SOURCE_REDACTED_STILL_RESTRICTED_CATEGORIES:
            return SensitivityClass.RESTRICTED
        if categories:
            return SensitivityClass.CONFIDENTIAL
        return scan.sensitivity

    @staticmethod
    def _minimize_preview(text: str) -> str:
        return text[:240]

    @staticmethod
    def _quasi_identifier_counts(raw_texts: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for text in raw_texts:
            lowered = text.casefold()
            if re.search(r"\b(?:20\d{2}|19\d{2})-\d{2}-\d{2}\b", text):
                counts["exact_date"] = counts.get("exact_date", 0) + 1
            if re.search(r"(?i)\b(?:almaty|kazakhstan|brazil|india|singapore|london|berlin|nigeria|kenya)\b", text):
                counts["geography"] = counts.get("geography", 0) + 1
            if re.search(r"(?i)\b(?:cfos?|ctos?|ceos?|founders?|directors?|vp|head of)\b", text):
                counts["role_title"] = counts.get("role_title", 0) + 1
            if any(marker in lowered for marker in ("rare ", "quantum", "stealth", "enterprise tier", "logistics segment")):
                counts["rare_segment"] = counts.get("rare_segment", 0) + 1
            if re.search(r"(?i)\b(?:customer|client|account)\s+(?:segment|cohort|descriptor)\b", text):
                counts["customer_descriptor"] = counts.get("customer_descriptor", 0) + 1
        return counts
