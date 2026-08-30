from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from decimal import Decimal
from hashlib import sha256
from typing import Any, cast
from uuid import UUID

from due_diligence_agent.application.policies.data_egress import DisclosureScope
from pydantic import ValidationError
from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.domain.findings.models import Contradiction
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileAnalysisStage,
    StartupProfileEvidenceRef,
    StartupProfileField,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
)
from due_diligence_agent.ports.startup_profile_extraction import (
    StartupProfileBoundedFragment,
    StartupProfileExtractedField,
    StartupProfileExtractorInvalidOutputError,
    StartupProfileExtractionPort,
    StartupProfileExtractionRequest,
    StartupProfileExtractionResponse,
    StartupProfileFragmentInventoryPort,
    StartupProfileSafeRef,
    StartupProfileSpreadsheetFact,
)


class StartupProfileRestrictedContextError(RuntimeError):
    stable_error_code = "STARTUP_PROFILE_RESTRICTED_CONTEXT"


class StartupProfileFragmentValidationError(ValueError):
    stable_error_code = "STARTUP_PROFILE_FRAGMENT_VALIDATION_ERROR"


class StartupProfileService:
    schema_version = "startup-profile-schema@1"
    profile_version = "startup-profile@1"
    extractor_version = "startup-profile-service@1"
    redaction_policy_version = "rules-redactor@1"
    egress_policy_version = "egress@1"

    def __init__(
        self,
        *,
        case_repository: Any,
        artifact_repository: Any,
        parsed_artifact_repository: Any,
        evidence_repository: Any,
        startup_claim_repository: Any,
        contradiction_repository: Any,
        startup_profile_repository: Any,
        deterministic_extractor: StartupProfileExtractionPort,
        external_extractor: StartupProfileExtractionPort | None = None,
        fragment_inventory: StartupProfileFragmentInventoryPort | None = None,
    ) -> None:
        self._case_repository = case_repository
        self._artifact_repository = artifact_repository
        self._parsed_artifact_repository = parsed_artifact_repository
        self._evidence_repository = evidence_repository
        self._startup_claim_repository = startup_claim_repository
        self._contradiction_repository = contradiction_repository
        self._startup_profile_repository = startup_profile_repository
        self._deterministic_extractor = deterministic_extractor
        self._external_extractor = external_extractor
        self._fragment_inventory = fragment_inventory or EmptyStartupProfileFragmentInventory()

    def build_primary(self, case_id: UUID) -> StartupProfile:
        case = self._case(case_id)
        try:
            existing = cast(
                StartupProfile,
                self._startup_profile_repository.get_for_stage(
                    case.case_id,
                    case.data_revision,
                    StartupProfileAnalysisStage.PRIMARY,
                ),
            )
        except KeyError:
            existing = None
        if existing is not None:
            _validate_primary_profile(existing, case=case)
            return existing
        inventory = self._inventory(case_id)
        selected_fragments = _validated_fragments(
            self._fragment_inventory.list_for_case_revision(case.case_id, case.data_revision),
            inventory=inventory,
            redaction_policy_version=self.redaction_policy_version,
        )
        request = self._request(
            case,
            inventory=inventory,
            primary_profile_id=None,
            fragments=selected_fragments,
        )
        try:
            response = _validated_extractor_response(
                self._deterministic_extractor.extract(request, disclosure_scope=None),
                request=request,
            )
        except StartupProfileExtractorInvalidOutputError:
            response = StartupProfileExtractionResponse(
                fields=(),
                gap_codes=("primary_profile_extraction_invalid",),
            )
        profile = self._profile_from_response(
            case,
            inventory=inventory,
            response=response,
            analysis_stage=StartupProfileAnalysisStage.PRIMARY,
            parent_profile_id=None,
        )
        self._startup_profile_repository.add(profile)
        return profile

    def enrich(
        self,
        case_id: UUID,
        primary_profile_id: UUID,
        *,
        disclosure_scope: DisclosureScope | None,
    ) -> StartupProfile:
        primary = cast(StartupProfile, self._startup_profile_repository.get(primary_profile_id))
        case = self._case(case_id)
        _validate_primary_profile(primary, case=case)
        if disclosure_scope is None or self._external_extractor is None:
            return primary
        try:
            existing = cast(
                StartupProfile,
                self._startup_profile_repository.get_for_stage(
                    case.case_id,
                    case.data_revision,
                    StartupProfileAnalysisStage.ENRICHED,
                ),
            )
        except KeyError:
            existing = None
        if existing is not None:
            _validate_enriched_profile(existing, case=case, parent_profile_id=primary.profile_id)
            return existing
        inventory = self._inventory(case_id)
        selected_fragments = _validated_fragments(
            self._fragment_inventory.list_for_case_revision(case.case_id, case.data_revision),
            inventory=inventory,
            redaction_policy_version=self.redaction_policy_version,
        )
        request = self._request(
            case,
            inventory=inventory,
            primary_profile_id=primary_profile_id,
            fragments=selected_fragments,
        )
        if _has_restricted_context(request):
            raise StartupProfileRestrictedContextError("STARTUP_PROFILE_RESTRICTED_CONTEXT")
        try:
            response = _validated_extractor_response(
                self._external_extractor.extract(request, disclosure_scope=disclosure_scope),
                request=request,
            )
        except TimeoutError:
            return self._controlled_enriched_gap(
                case,
                primary=primary,
                gap_code="external_profile_extraction_timeout",
            )
        except StartupProfileExtractorInvalidOutputError:
            return self._controlled_enriched_gap(
                case,
                primary=primary,
                gap_code="external_profile_extraction_invalid",
            )
        merged_fields = dict(primary.fields)
        merged_fields.update(
            _profile_fields_from_response(response, base_fields=primary.fields)
        )
        profile = StartupProfile.build(
            case_id=case.case_id,
            schema_version=self.schema_version,
            profile_version=self.profile_version,
            extractor_version=f"{self.extractor_version}-external",
            analysis_stage=StartupProfileAnalysisStage.ENRICHED,
            parent_profile_id=primary.profile_id,
            data_revision=case.data_revision,
            source_hashes=primary.source_hashes,
            parse_outcomes=primary.parse_outcomes,
            fields=merged_fields,
            gap_codes=tuple(sorted({*primary.gap_codes, *response.gap_codes})),
            contradiction_ids=primary.contradiction_ids,
            case_revision_at=case.updated_at,
        )
        self._startup_profile_repository.add(profile)
        return profile

    def _controlled_enriched_gap(
        self,
        case: DueDiligenceCase,
        *,
        primary: StartupProfile,
        gap_code: str,
    ) -> StartupProfile:
        profile = StartupProfile.build(
            case_id=case.case_id,
            schema_version=self.schema_version,
            profile_version=self.profile_version,
            extractor_version=f"{self.extractor_version}-external",
            analysis_stage=StartupProfileAnalysisStage.ENRICHED,
            parent_profile_id=primary.profile_id,
            data_revision=case.data_revision,
            source_hashes=primary.source_hashes,
            parse_outcomes=primary.parse_outcomes,
            fields=primary.fields,
            gap_codes=tuple(sorted({*primary.gap_codes, gap_code})),
            contradiction_ids=primary.contradiction_ids,
            case_revision_at=case.updated_at,
        )
        self._startup_profile_repository.add(profile)
        return profile

    def _case(self, case_id: UUID) -> DueDiligenceCase:
        return cast(DueDiligenceCase, self._case_repository.get(case_id))

    def _inventory(self, case_id: UUID) -> _ProfileInputInventory:
        parse_results = tuple(sorted(
            self._parsed_artifact_repository.list_for_case(case_id),
            key=lambda item: str(item.artifact_id),
        ))
        artifacts: dict[UUID, Artifact] = {}
        for parsed in parse_results:
            artifacts[parsed.artifact_id] = self._artifact_repository.get(parsed.artifact_id)
        facts = tuple(sorted(
            self._evidence_repository.list_for_case(case_id),
            key=lambda item: (item.name.casefold(), str(item.id)),
        ))
        for fact in facts:
            if fact.artifact_id not in artifacts:
                artifacts[fact.artifact_id] = self._artifact_repository.get(fact.artifact_id)
        claims = tuple(sorted(
            self._startup_claim_repository.list_for_case(case_id),
            key=lambda item: (item.normalized_name.casefold(), str(item.id)),
        ))
        contradictions = tuple(sorted(
            self._contradiction_repository.list_for_case(case_id),
            key=lambda item: str(item.id),
        ))
        return _ProfileInputInventory(
            parse_results=parse_results,
            artifacts=artifacts,
            facts=facts,
            claims=claims,
            contradictions=contradictions,
        )

    def _request(
        self,
        case: DueDiligenceCase,
        *,
        inventory: _ProfileInputInventory,
        primary_profile_id: UUID | None,
        fragments: tuple[StartupProfileBoundedFragment, ...],
    ) -> StartupProfileExtractionRequest:
        spreadsheet_facts = tuple(
            _spreadsheet_fact(fact, artifact=inventory.artifacts[fact.artifact_id])
            for fact in inventory.facts
            if fact.value_type in {"decimal", "integer"}
        )
        return StartupProfileExtractionRequest(
            case_id=case.case_id,
            data_revision=case.data_revision,
            primary_profile_id=primary_profile_id,
            allowed_field_names=tuple(StartupProfileFieldName),
            fragments=fragments,
            spreadsheet_facts=spreadsheet_facts,
            allowed_refs=_allowed_refs(inventory),
            source_hashes=tuple(
                _artifact_hash(artifact)
                for artifact in sorted(inventory.artifacts.values(), key=lambda item: str(item.id))
            ),
            egress_policy_version=self.egress_policy_version,
            redaction_policy_version=self.redaction_policy_version,
        )

    def _profile_from_response(
        self,
        case: DueDiligenceCase,
        *,
        inventory: _ProfileInputInventory,
        response: StartupProfileExtractionResponse,
        analysis_stage: StartupProfileAnalysisStage,
        parent_profile_id: UUID | None,
    ) -> StartupProfile:
        return StartupProfile.build(
            case_id=case.case_id,
            schema_version=self.schema_version,
            profile_version=self.profile_version,
            extractor_version=self.extractor_version,
            analysis_stage=analysis_stage,
            parent_profile_id=parent_profile_id,
            data_revision=case.data_revision,
            source_hashes=_source_hashes(inventory.artifacts.values()),
            parse_outcomes=_parse_outcomes(inventory.parse_results),
            fields=_profile_fields_from_response(response, base_fields=None),
            gap_codes=response.gap_codes,
            contradiction_ids=tuple(item.id for item in inventory.contradictions),
            case_revision_at=case.updated_at,
        )


class _ProfileInputInventory:
    def __init__(
        self,
        *,
        parse_results: tuple[Any, ...],
        artifacts: dict[UUID, Artifact],
        facts: tuple[EvidenceFact, ...],
        claims: tuple[Any, ...],
        contradictions: tuple[Contradiction, ...],
    ) -> None:
        self.parse_results = parse_results
        self.artifacts = artifacts
        self.facts = facts
        self.claims = claims
        self.contradictions = contradictions


class EmptyStartupProfileFragmentInventory:
    def list_for_case_revision(
        self,
        case_id: UUID,
        data_revision: int,
    ) -> tuple[StartupProfileBoundedFragment, ...]:
        del case_id, data_revision
        return ()


def _validated_fragments(
    fragments: Iterable[StartupProfileBoundedFragment],
    *,
    inventory: _ProfileInputInventory,
    redaction_policy_version: str,
) -> tuple[StartupProfileBoundedFragment, ...]:
    selected = tuple(fragments)
    for fragment in selected:
        artifact = inventory.artifacts.get(fragment.artifact_id)
        if artifact is None:
            raise StartupProfileFragmentValidationError("startup_profile_fragment_artifact_not_found")
        if fragment.artifact_hash != _artifact_hash(artifact):
            raise StartupProfileFragmentValidationError("startup_profile_fragment_source_hash_mismatch")
        if fragment.redaction_policy_version != redaction_policy_version:
            raise StartupProfileFragmentValidationError("startup_profile_fragment_redaction_mismatch")
    return selected


def _validate_primary_profile(primary: StartupProfile, *, case: DueDiligenceCase) -> None:
    if (
        primary.case_id != case.case_id
        or primary.data_revision != case.data_revision
        or primary.analysis_stage is not StartupProfileAnalysisStage.PRIMARY
        or primary.parent_profile_id is not None
    ):
        raise ValueError("startup_profile_primary_mismatch")


def _validate_enriched_profile(
    enriched: StartupProfile,
    *,
    case: DueDiligenceCase,
    parent_profile_id: UUID,
) -> None:
    if (
        enriched.case_id != case.case_id
        or enriched.data_revision != case.data_revision
        or enriched.analysis_stage is not StartupProfileAnalysisStage.ENRICHED
        or enriched.parent_profile_id != parent_profile_id
    ):
        raise ValueError("startup_profile_enriched_mismatch")


def _validated_extractor_response(
    response: StartupProfileExtractionResponse,
    *,
    request: StartupProfileExtractionRequest,
) -> StartupProfileExtractionResponse:
    try:
        return response.validate_against_request(request)
    except (ValueError, ValidationError) as exc:
        raise StartupProfileExtractorInvalidOutputError("startup_profile_extractor_invalid_output") from exc


def _profile_fields_from_response(
    response: StartupProfileExtractionResponse,
    *,
    base_fields: Mapping[str, StartupProfileField] | None,
) -> dict[str, StartupProfileField]:
    fields = {
        name.value: (
            base_fields[name.value]
            if base_fields is not None and name.value in base_fields
            else StartupProfileField(
                name=name,
                status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
                confidence=Decimal("0"),
            )
        )
        for name in StartupProfileFieldName
    }
    for extracted in response.fields:
        fields[extracted.field_name.value] = _profile_field(extracted)
    return fields


def _profile_field(extracted: StartupProfileExtractedField) -> StartupProfileField:
    contradiction_ids = tuple(
        ref.ref_id for ref in extracted.refs if ref.ref_type == "contradiction"
    )
    evidence_refs = tuple(
        _evidence_ref(ref, field_name=extracted.field_name)
        for ref in extracted.refs
        if ref.artifact_id is not None and ref.ref_type != "contradiction"
    )
    dependency_refs: tuple[UUID, ...] = ()
    if extracted.status is StartupProfileFieldStatus.INFERENCE:
        dependency_refs = tuple(ref.ref_id for ref in extracted.refs)
        evidence_refs = ()
    return StartupProfileField(
        name=extracted.field_name,
        status=extracted.status,
        values=extracted.normalized_values,
        confidence=extracted.confidence,
        evidence_refs=evidence_refs,
        dependency_refs=dependency_refs,
        reason_code=extracted.reason_code,
        contradiction_ids=contradiction_ids,
    )


def _evidence_ref(
    ref: StartupProfileSafeRef,
    *,
    field_name: StartupProfileFieldName,
) -> StartupProfileEvidenceRef:
    if ref.artifact_id is None or ref.artifact_hash is None or ref.locator_hash is None:
        raise ValueError("profile evidence refs require artifact and locator hashes")
    return StartupProfileEvidenceRef(
        evidence_id=ref.ref_id,
        fragment_id=ref.ref_id if ref.ref_type == "fragment" else None,
        artifact_id=ref.artifact_id,
        artifact_hash=ref.artifact_hash,
        locator_hash=ref.locator_hash,
        page=ref.page,
        table=ref.table,
        cell=ref.cell,
        field_name=field_name,
        confidence=ref.confidence,
    )


def _spreadsheet_fact(fact: EvidenceFact, *, artifact: Artifact) -> StartupProfileSpreadsheetFact:
    return StartupProfileSpreadsheetFact(
        evidence_fact_id=fact.id,
        artifact_id=fact.artifact_id,
        name=fact.name,
        value_type=fact.value_type,
        normalized_value=_safe_value(fact.value),
        unit=fact.unit,
        period=fact.period,
        confidence=fact.confidence,
        sensitivity=fact.sensitivity,
        artifact_hash=_artifact_hash(artifact),
        locator_hash=_locator_hash(fact.locator),
        table=fact.locator.table,
        cell=fact.locator.cell,
    )


def _allowed_refs(inventory: _ProfileInputInventory) -> tuple[StartupProfileSafeRef, ...]:
    refs: list[StartupProfileSafeRef] = []
    for claim in inventory.claims:
        artifact = inventory.artifacts.get(claim.source_artifact_id)
        if artifact is None:
            continue
        refs.append(
            StartupProfileSafeRef(
                ref_type="claim",
                ref_id=claim.id,
                artifact_id=claim.source_artifact_id,
                artifact_hash=_artifact_hash(artifact),
                locator_hash=_locator_hash(claim.locator),
                confidence=claim.confidence,
            )
        )
    refs.extend(
        StartupProfileSafeRef(ref_type="contradiction", ref_id=item.id)
        for item in inventory.contradictions
    )
    return tuple(refs)


def _source_hashes(artifacts: Iterable[Artifact]) -> dict[str, str]:
    return {
        f"artifact-{artifact.id.hex}": _artifact_hash(artifact)
        for artifact in sorted(artifacts, key=lambda item: str(item.id))
    }


def _parse_outcomes(parse_results: Iterable[Any]) -> dict[str, str]:
    return {
        f"artifact-{item.artifact_id.hex}": str(item.status)
        for item in sorted(parse_results, key=lambda parsed: str(parsed.artifact_id))
    }


def _artifact_hash(artifact: Artifact) -> str:
    return _hash_ref(artifact.source_snapshot_hash or artifact.content_hash)


def _hash_ref(value: str) -> str:
    return value if value.startswith("sha256:") else f"sha256:{value}"


def _locator_hash(locator: SourceLocator) -> str:
    payload = json.dumps(locator.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(payload.encode('utf-8')).hexdigest()}"


def _safe_value(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return " ".join(str(value).split())[:240]


def _has_restricted_context(request: StartupProfileExtractionRequest) -> bool:
    return any(fragment.sensitivity is SensitivityClass.RESTRICTED for fragment in request.fragments) or any(
        fact.sensitivity is SensitivityClass.RESTRICTED for fact in request.spreadsheet_facts
    )
