from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from hashlib import sha256
import importlib
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Final, Literal, Protocol, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from due_diligence_agent.adapters.startup.frozen_market_research import (
    FrozenStartupMarketResearchAdapter,
)
from due_diligence_agent.bootstrap.container import (
    build_deterministic_startup_analysis_composer,
    build_startup_profile_query_port,
)
from due_diligence_agent.config import OpenAIStartupSettings
from due_diligence_agent.domain.startup.market import (
    StartupMarketResearchSnapshot,
    StartupResearchPlan,
    StartupResearchSourceMode,
)
from due_diligence_agent.domain.startup.profile import (
    StartupProfile,
    StartupProfileFieldName,
)
from due_diligence_agent.evals.output_root import (
    EVALUATION_OUTPUT_ERROR_CODES,
    prepare_evaluation_output_root,
)


SCHEMA_VERSION: Final[str] = "openai_competitor_smoke_evidence@1"
EVIDENCE_FILENAME: Final[str] = "openai-competitor-smoke-evidence.json"
CASE_ID: Final[str] = "00000000-0000-0000-0000-000000000951"
RUN_ID: Final[str] = "queue5-openai-competitor-run-951"
CORRELATION_ID: Final[str] = "queue5-openai-competitor-correlation-951"
INJECTED_PROFILE_HASH: Final[str] = "sha256:" + "a" * 64
_FIXTURE_PDF: Final[Path] = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "startup_synthetic_v1"
    / "cases"
    / "saas"
    / "pitch.pdf"
)
_MARKET_FIXTURE_ROOT: Final[Path] = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "startup_market_research_v1"
)
MAX_BUDGET_USD: Final[Decimal] = Decimal("0.25")
MAX_OUTPUT_TOKENS: Final[int] = 1200
_CATEGORIES: Final[tuple[str, ...]] = (
    "direct",
    "indirect",
    "substitute",
    "do_nothing",
    "potential_entrant",
)
_SENSITIVE_VALUE_RE: Final[re.Pattern[str]] = re.compile(
    r"((?<![A-Za-z0-9])[A-Za-z]:[\\/]|"
    r"(?i:/Users/|/home/|[\w.+-]+@[\w.-]+\.[a-z]{2,}|"
    r"(?<![A-Za-z0-9_-])sk-(?:proj-)?[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])|"
    r"\bbearer\s+\S+|api[_ -]?key|secret|private|%PDF|pitch\.pdf|"
    r"raw[_ -]?pdf|document[_ -]?text|filename|local[_ -]?path|prompt|"
    r"chain[_ -]?of[_ -]?thought|completion|system\s+instructions))"
)


class _OpenAIClientFactory(Protocol):
    def __call__(self, **kwargs: object) -> object: ...


class _ResponsesClient(Protocol):
    def parse(self, **kwargs: object) -> object: ...


class _ClientWithResponses(Protocol):
    responses: _ResponsesClient


class _OpenAICompetitorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
        populate_by_name=True,
    )

    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )


class SanitizedStartupProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    startup_name: str = Field(min_length=1, max_length=120)
    one_line_description: str = Field(min_length=1, max_length=240)
    problem: str = Field(min_length=1, max_length=240)
    solution: str = Field(min_length=1, max_length=240)
    business_model: str = Field(min_length=1, max_length=120)
    icp: str = Field(min_length=1, max_length=160)
    geography: str = Field(min_length=1, max_length=80)
    stage: str = Field(min_length=1, max_length=80)
    profile_hash: str

    @field_validator("*", mode="before")
    @classmethod
    def normalize_safe_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return " ".join(value.strip().split())


class Gate2Evidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    run_id: str
    status: str
    decision: str
    destination: str
    profile_hash: str
    profile_id: str = ""

    def is_approved(self) -> bool:
        return (
            self.status == "approved"
            and self.decision == "approved"
            and self.destination == "openai.responses"
            and self.case_id != ""
            and self.run_id != ""
        )


class FrozenCompetitorEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: Literal["direct", "indirect", "substitute", "do_nothing", "potential_entrant"]
    label: str = Field(min_length=1, max_length=120)
    evidence_ref: str = Field(min_length=1, max_length=120)
    source_summary: str = Field(min_length=1, max_length=240)
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @field_validator("label", "evidence_ref", "source_summary", mode="before")
    @classmethod
    def normalize_safe_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return " ".join(value.strip().split())


class OpenAICompetitorRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    category: Literal["direct", "indirect", "substitute", "do_nothing", "potential_entrant"]
    name: str = Field(min_length=1, max_length=120)
    icp_overlap: str = Field(min_length=1, max_length=160)
    differentiation: str = Field(min_length=1, max_length=240)
    risk: str = Field(min_length=1, max_length=240)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(min_length=1, max_length=8)
    unknowns: list[str] = Field(default_factory=list, max_length=8)


class OpenAICompetitorSynthesis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    competitors: list[OpenAICompetitorRow] = Field(min_length=5, max_length=10)
    summary: str = Field(min_length=1, max_length=500)
    unknowns: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("competitors")
    @classmethod
    def require_all_categories(
        cls,
        value: list[OpenAICompetitorRow],
    ) -> list[OpenAICompetitorRow]:
        categories = {row.category for row in value}
        missing = set(_CATEGORIES) - categories
        if missing:
            raise ValueError(f"missing competitor categories: {sorted(missing)}")
        return value


@dataclass(frozen=True)
class Queue5OpenAICompetitorSmokeEvidence:
    schema_version: str
    status: str
    credential_present: bool
    execute_live_requested: bool
    live_call_attempted: bool
    live_call_succeeded: bool
    call_count: int
    inference_label: str
    research_label: str
    gate2: Gate2Evidence
    startup_profile: SanitizedStartupProfile
    competitor_evidence_count: int
    lineage: dict[str, str]
    source_summary_hashes: tuple[str, ...]
    transport: dict[str, str]
    result: OpenAICompetitorSynthesis | None
    budget: dict[str, str]
    usage: dict[str, int]
    cost_evidence: dict[str, str]
    privacy: dict[str, object]
    semantic_hash: str
    error_code: str | None = None
    artifact_paths: dict[str, str] = field(default_factory=dict)
    fail_reasons: tuple[str, ...] = ()

    def to_json_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["gate2"] = self.gate2.model_dump(mode="json")
        payload["startup_profile"] = self.startup_profile.model_dump(mode="json")
        payload["result"] = self.result.model_dump(mode="json") if self.result is not None else None
        payload["source_summary_hashes"] = list(self.source_summary_hashes)
        payload["fail_reasons"] = list(self.fail_reasons)
        return payload


def run_queue5_openai_competitor_smoke(
    output_dir: Path,
    *,
    startup_profile: SanitizedStartupProfile | None = None,
    competitor_evidence: Sequence[FrozenCompetitorEvidence] | None = None,
    gate2_evidence: Gate2Evidence | None = None,
    execute_live: bool = False,
    client_factory: _OpenAIClientFactory | None = None,
) -> Queue5OpenAICompetitorSmokeEvidence:
    output_root = prepare_evaluation_output_root(output_dir)
    profile, competitors, gate2, lineage = _resolve_smoke_inputs(
        output_root,
        startup_profile=startup_profile,
        competitor_evidence=competitor_evidence,
        gate2_evidence=gate2_evidence,
    )
    source_summary_hashes = _source_summary_hashes(competitors)
    credential_present = _openai_key_present()
    fail_reasons: list[str] = []
    result: OpenAICompetitorSynthesis | None = None
    call_count = 0
    live_call_attempted = False
    live_call_succeeded = False
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    payload = _request_payload(profile, competitors, gate2)
    try:
        validate_openai_competitor_payload_privacy(payload)
    except ValueError:
        fail_reasons.append("privacy_validation_failed")
        return _persist_evidence(
            output_root,
            status="blocked_privacy_validation",
            credential_present=credential_present,
            execute_live_requested=execute_live,
            live_call_attempted=False,
            live_call_succeeded=False,
            call_count=0,
            gate2=gate2,
            profile=profile,
            competitor_evidence_count=len(competitors),
            lineage=lineage,
            source_summary_hashes=source_summary_hashes,
            result=None,
            usage=usage,
            fail_reasons=fail_reasons,
            request_payload=payload,
            response_payload=None,
        )

    if not credential_present:
        return _persist_evidence(
            output_root,
            status="skipped_missing_credential",
            credential_present=False,
            execute_live_requested=execute_live,
            live_call_attempted=False,
            live_call_succeeded=False,
            call_count=0,
            gate2=gate2,
            profile=profile,
            competitor_evidence_count=len(competitors),
            lineage=lineage,
            source_summary_hashes=source_summary_hashes,
            result=None,
            usage=usage,
            fail_reasons=fail_reasons,
            request_payload=payload,
            response_payload=None,
        )
    if not execute_live:
        return _persist_evidence(
            output_root,
            status="armed_not_executed",
            credential_present=True,
            execute_live_requested=False,
            live_call_attempted=False,
            live_call_succeeded=False,
            call_count=0,
            gate2=gate2,
            profile=profile,
            competitor_evidence_count=len(competitors),
            lineage=lineage,
            source_summary_hashes=source_summary_hashes,
            result=None,
            usage=usage,
            fail_reasons=fail_reasons,
            request_payload=payload,
            response_payload=None,
        )
    if not gate2.is_approved():
        fail_reasons.append("gate2_not_approved")
        return _persist_evidence(
            output_root,
            status="blocked_gate2_not_approved",
            credential_present=True,
            execute_live_requested=True,
            live_call_attempted=False,
            live_call_succeeded=False,
            call_count=0,
            gate2=gate2,
            profile=profile,
            competitor_evidence_count=len(competitors),
            lineage=lineage,
            source_summary_hashes=source_summary_hashes,
            result=None,
            usage=usage,
            fail_reasons=fail_reasons,
            request_payload=payload,
            response_payload=None,
        )

    settings = OpenAIStartupSettings()
    if settings.per_case_usd_cap > MAX_BUDGET_USD:
        fail_reasons.append("budget_cap_exceeds_bound")
        return _persist_evidence(
            output_root,
            status="blocked_budget_guard",
            credential_present=True,
            execute_live_requested=True,
            live_call_attempted=False,
            live_call_succeeded=False,
            call_count=0,
            gate2=gate2,
            profile=profile,
            competitor_evidence_count=len(competitors),
            lineage=lineage,
            source_summary_hashes=source_summary_hashes,
            result=None,
            usage=usage,
            fail_reasons=fail_reasons,
            request_payload=payload,
            response_payload=None,
        )

    try:
        client = _client_with_responses(
            (client_factory or _default_openai_client_factory(settings.openai_api_key))(
                timeout=min(settings.timeout_seconds, 20.0),
                max_retries=0,
            )
        )
    except Exception:
        fail_reasons.append("client_init_error")
        return _persist_evidence(
            output_root,
            status="partial_fallback",
            credential_present=True,
            execute_live_requested=True,
            live_call_attempted=False,
            live_call_succeeded=False,
            call_count=0,
            gate2=gate2,
            profile=profile,
            competitor_evidence_count=len(competitors),
            lineage=lineage,
            source_summary_hashes=source_summary_hashes,
            result=None,
            usage=usage,
            fail_reasons=fail_reasons,
            request_payload=payload,
            response_payload=None,
            error_code="client_init_error",
        )

    request = _openai_request(settings=settings, gate2=gate2, payload=payload)
    live_call_attempted = True
    call_count = 1
    try:
        response = client.responses.parse(**request)
    except ValidationError:
        fail_reasons.append("parse_error")
        return _persist_evidence(
            output_root,
            status="partial_fallback",
            credential_present=True,
            execute_live_requested=True,
            live_call_attempted=True,
            live_call_succeeded=False,
            call_count=1,
            gate2=gate2,
            profile=profile,
            competitor_evidence_count=len(competitors),
            lineage=lineage,
            source_summary_hashes=source_summary_hashes,
            result=None,
            usage=usage,
            fail_reasons=fail_reasons,
            request_payload=payload,
            response_payload=None,
            error_code="parse_error",
        )
    except TimeoutError:
        fail_reasons.append("timeout")
        return _persist_evidence(
            output_root,
            status="partial_fallback",
            credential_present=True,
            execute_live_requested=True,
            live_call_attempted=True,
            live_call_succeeded=False,
            call_count=1,
            gate2=gate2,
            profile=profile,
            competitor_evidence_count=len(competitors),
            lineage=lineage,
            source_summary_hashes=source_summary_hashes,
            result=None,
            usage=usage,
            fail_reasons=fail_reasons,
            request_payload=payload,
            response_payload=None,
            error_code="timeout",
        )
    except Exception:
        fail_reasons.append("provider_error")
        return _persist_evidence(
            output_root,
            status="partial_fallback",
            credential_present=True,
            execute_live_requested=True,
            live_call_attempted=True,
            live_call_succeeded=False,
            call_count=1,
            gate2=gate2,
            profile=profile,
            competitor_evidence_count=len(competitors),
            lineage=lineage,
            source_summary_hashes=source_summary_hashes,
            result=None,
            usage=usage,
            fail_reasons=fail_reasons,
            request_payload=payload,
            response_payload=None,
            error_code="provider_error",
        )

    try:
        parsed = getattr(response, "output_parsed", None)
        result = (
            parsed
            if isinstance(parsed, OpenAICompetitorSynthesis)
            else OpenAICompetitorSynthesis.model_validate(parsed)
        )
    except (ValidationError, TypeError):
        fail_reasons.append("parse_error")
        return _persist_evidence(
            output_root,
            status="partial_fallback",
            credential_present=True,
            execute_live_requested=True,
            live_call_attempted=True,
            live_call_succeeded=False,
            call_count=1,
            gate2=gate2,
            profile=profile,
            competitor_evidence_count=len(competitors),
            lineage=lineage,
            source_summary_hashes=source_summary_hashes,
            result=None,
            usage=usage,
            fail_reasons=fail_reasons,
            request_payload=payload,
            response_payload=None,
            error_code="parse_error",
        )

    try:
        _validate_result_evidence_refs(result, competitors)
    except ValueError:
        fail_reasons.append("response_validation_error")
        return _persist_evidence(
            output_root,
            status="partial_fallback",
            credential_present=True,
            execute_live_requested=True,
            live_call_attempted=True,
            live_call_succeeded=False,
            call_count=1,
            gate2=gate2,
            profile=profile,
            competitor_evidence_count=len(competitors),
            lineage=lineage,
            source_summary_hashes=source_summary_hashes,
            result=None,
            usage=usage,
            fail_reasons=fail_reasons,
            request_payload=payload,
            response_payload=None,
            error_code="response_validation_error",
        )

    response_payload = result.model_dump(mode="json")
    try:
        validate_openai_competitor_payload_privacy(response_payload)
    except ValueError:
        fail_reasons.append("output_privacy_rejected")
        return _persist_evidence(
            output_root,
            status="partial_fallback",
            credential_present=True,
            execute_live_requested=True,
            live_call_attempted=True,
            live_call_succeeded=False,
            call_count=1,
            gate2=gate2,
            profile=profile,
            competitor_evidence_count=len(competitors),
            lineage=lineage,
            source_summary_hashes=source_summary_hashes,
            result=None,
            usage=usage,
            fail_reasons=fail_reasons,
            request_payload=payload,
            response_payload=None,
            error_code="output_privacy_rejected",
        )

    usage = _usage_from_response(response)
    live_call_succeeded = True

    return _persist_evidence(
        output_root,
        status="pass",
        credential_present=True,
        execute_live_requested=True,
        live_call_attempted=live_call_attempted,
        live_call_succeeded=live_call_succeeded,
        call_count=call_count,
        gate2=gate2,
        profile=profile,
        competitor_evidence_count=len(competitors),
        lineage=lineage,
        source_summary_hashes=source_summary_hashes,
        result=result,
        usage=usage,
        fail_reasons=fail_reasons,
        request_payload=payload,
        response_payload=response_payload,
    )


def default_frozen_startup_profile() -> SanitizedStartupProfile:
    return SanitizedStartupProfile(
        startup_name="DiligenceFlow",
        one_line_description="AI-assisted investment due diligence workspace",
        problem="Investment teams lose time reconciling startup evidence.",
        solution="A controlled workflow converts approved evidence into diligence reports.",
        business_model="B2B SaaS",
        icp="Seed and Series A investment teams",
        geography="United States",
        stage="pilot-ready",
        profile_hash=INJECTED_PROFILE_HASH,
    )


def default_gate2_evidence() -> Gate2Evidence:
    return Gate2Evidence(
        case_id=CASE_ID,
        run_id=RUN_ID,
        status="approved",
        decision="approved",
        destination="openai.responses",
        profile_hash=INJECTED_PROFILE_HASH,
    )


def default_frozen_competitor_evidence() -> tuple[FrozenCompetitorEvidence, ...]:
    return (
        FrozenCompetitorEvidence(
            category="direct",
            label="Workflow diligence suites",
            evidence_ref="fixture:market:direct",
            source_summary="Frozen source summary names workflow tools for diligence teams.",
            confidence=Decimal("0.71"),
        ),
        FrozenCompetitorEvidence(
            category="indirect",
            label="Spreadsheet analyst workflow",
            evidence_ref="fixture:market:indirect",
            source_summary="Frozen source summary describes spreadsheet-led analyst process.",
            confidence=Decimal("0.62"),
        ),
        FrozenCompetitorEvidence(
            category="substitute",
            label="Consultant-led diligence",
            evidence_ref="fixture:market:substitute",
            source_summary="Frozen source summary describes outsourced diligence projects.",
            confidence=Decimal("0.58"),
        ),
        FrozenCompetitorEvidence(
            category="do_nothing",
            label="Manual memo process",
            evidence_ref="fixture:market:do_nothing",
            source_summary="Frozen source summary describes not adopting new tooling.",
            confidence=Decimal("0.53"),
        ),
        FrozenCompetitorEvidence(
            category="potential_entrant",
            label="CRM intelligence vendor",
            evidence_ref="fixture:market:potential_entrant",
            source_summary="Frozen source summary describes adjacent CRM intelligence products.",
            confidence=Decimal("0.49"),
        ),
    )


def _resolve_smoke_inputs(
    output_root: Path,
    *,
    startup_profile: SanitizedStartupProfile | None,
    competitor_evidence: Sequence[FrozenCompetitorEvidence] | None,
    gate2_evidence: Gate2Evidence | None,
) -> tuple[
    SanitizedStartupProfile,
    tuple[FrozenCompetitorEvidence, ...],
    Gate2Evidence,
    dict[str, str],
]:
    if startup_profile is None and competitor_evidence is None and gate2_evidence is None:
        gate2 = _derive_gate2_from_real_frozen_workflow(output_root / "runtime")
        persisted_profile = build_startup_profile_query_port(output_root / "runtime").get(
            UUID(gate2.profile_id)
        )
        profile = _profile_from_persisted(persisted_profile)
        market_snapshot = _frozen_market_snapshot(gate2.case_id)
        competitors = _competitor_evidence_from_market_snapshot(market_snapshot)
        market_source_hashes = ",".join(
            sorted(source.source_hash for source in market_snapshot.sources)
        )
        market_categories = ",".join(
            sorted({competitor.category.value for competitor in market_snapshot.competitors})
        )
        return (
            profile,
            competitors,
            gate2,
            {
                "source": "deterministic_startup_composer",
                "fixture_case": "startup_synthetic_v1/saas",
                "case_id": gate2.case_id,
                "run_id": gate2.run_id,
                "gate2_decision": gate2.decision,
                "profile_hash": gate2.profile_hash,
                "profile_id": gate2.profile_id,
                "market_source_mode": market_snapshot.source_mode.value,
                "market_snapshot_hash": market_snapshot.snapshot_hash,
                "market_source_hashes": market_source_hashes,
                "market_competitor_categories": market_categories,
            },
        )

    profile = startup_profile or default_frozen_startup_profile()
    competitors = tuple(competitor_evidence or default_frozen_competitor_evidence())
    gate2 = gate2_evidence or default_gate2_evidence()
    return (
        profile,
        competitors,
        gate2,
        {
            "source": "injected_test_evidence",
            "case_id": gate2.case_id,
            "run_id": gate2.run_id,
            "gate2_decision": gate2.decision,
            "profile_hash": gate2.profile_hash,
        },
    )


def _derive_gate2_from_real_frozen_workflow(data_dir: Path) -> Gate2Evidence:
    content = _FIXTURE_PDF.read_bytes()
    inbox = data_dir / "inbox" / CASE_ID
    inbox.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(_FIXTURE_PDF, inbox / "doc-0001.pdf")
    service = build_deterministic_startup_analysis_composer(data_dir)
    service.start(
        {
            "case_id": CASE_ID,
            "run_id": RUN_ID,
            "correlation_id": CORRELATION_ID,
            "source_refs": [
                {
                    "document_id": "doc-0001",
                    "private_name": "doc-0001.pdf",
                    "content_sha256": sha256(content).hexdigest(),
                }
            ],
        },
        thread_id=RUN_ID,
    )
    gate3 = service.resume(
        {
            "action": "approved",
            "actor": "founder",
            "destination": "openai.responses",
        },
        thread_id=RUN_ID,
    )
    if gate3.get("status") != "review_required":
        raise ValueError("openai_competitor_gate2_workflow_not_approved")
    return Gate2Evidence(
        case_id=str(gate3["case_id"]),
        run_id=str(gate3["run_id"]),
        status="approved",
        decision="approved",
        destination="openai.responses",
        profile_hash=str(gate3["profile_hash"]),
        profile_id=str(gate3["profile_id"]),
    )


def _profile_from_persisted(profile: StartupProfile) -> SanitizedStartupProfile:
    return SanitizedStartupProfile(
        startup_name=_first_profile_value(profile, StartupProfileFieldName.STARTUP_NAME),
        one_line_description=_first_profile_value(
            profile,
            StartupProfileFieldName.ONE_LINE_DESCRIPTION,
        ),
        problem=_first_profile_value(profile, StartupProfileFieldName.PROBLEM),
        solution=_first_profile_value(profile, StartupProfileFieldName.SOLUTION),
        business_model=_first_profile_value(
            profile,
            StartupProfileFieldName.BUSINESS_MODEL,
        ),
        icp=_first_profile_value(profile, StartupProfileFieldName.ICP),
        geography=_first_profile_value(profile, StartupProfileFieldName.GEOGRAPHY),
        stage=_first_profile_value(profile, StartupProfileFieldName.STAGE),
        profile_hash=profile.profile_hash,
    )


def _first_profile_value(
    profile: StartupProfile,
    field_name: StartupProfileFieldName,
) -> str:
    field = profile.fields[field_name.value]
    if not field.values:
        return "MISSING"
    return field.values[0]


def _frozen_market_snapshot(case_id: str) -> StartupMarketResearchSnapshot:
    return FrozenStartupMarketResearchAdapter.from_fixture_dir(_MARKET_FIXTURE_ROOT).collect(
        StartupResearchPlan(
            case_id=UUID(case_id),
            source_mode=StartupResearchSourceMode.FROZEN,
        )
    )


def _competitor_evidence_from_market_snapshot(
    snapshot: StartupMarketResearchSnapshot,
) -> tuple[FrozenCompetitorEvidence, ...]:
    return tuple(
        FrozenCompetitorEvidence(
            category=competitor.category.value,
            label=competitor.name,
            evidence_ref=f"frozen_market:{competitor.category.value}:{competitor.source_ids[0]}",
            source_summary=(
                f"Frozen market snapshot category={competitor.category.value}; "
                f"status={competitor.status.value}; source_refs="
                + ",".join(str(source_id) for source_id in competitor.source_ids)
            ),
            confidence=competitor.confidence,
        )
        for competitor in snapshot.competitors
    )


def _source_summary_hashes(
    competitors: Sequence[FrozenCompetitorEvidence],
) -> tuple[str, ...]:
    return tuple(
        f"sha256:{sha256(item.source_summary.encode('utf-8')).hexdigest()}" for item in competitors
    )


def _validate_result_evidence_refs(
    result: OpenAICompetitorSynthesis,
    competitors: Sequence[FrozenCompetitorEvidence],
) -> None:
    allowed = {item.evidence_ref for item in competitors}
    for row in result.competitors:
        if not set(row.evidence_refs) <= allowed:
            raise ValueError("openai_competitor_evidence_ref_outside_frozen_set")


def validate_openai_competitor_payload_privacy(payload: Mapping[str, object]) -> None:
    if _privacy_leak_count(payload) != 0:
        raise ValueError("openai_competitor_payload_privacy_rejected")


def _request_payload(
    profile: SanitizedStartupProfile,
    competitor_evidence: Sequence[FrozenCompetitorEvidence],
    gate2: Gate2Evidence,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": gate2.case_id,
        "run_id": gate2.run_id,
        "inference_label": "live_inference",
        "research_label": "not_live_web_research",
        "gate2": gate2.model_dump(mode="json"),
        "startup_profile": profile.model_dump(mode="json"),
        "frozen_competitor_evidence": [
            evidence.model_dump(mode="json") for evidence in competitor_evidence
        ],
        "allowed_categories": list(_CATEGORIES),
        "constraints": {
            "live_web_research": False,
            "deck_bytes_allowed": False,
            "doc_body_allowed": False,
            "machine_paths_allowed": False,
            "single_call": True,
        },
    }


def _openai_request(
    *,
    settings: OpenAIStartupSettings,
    gate2: Gate2Evidence,
    payload: Mapping[str, object],
) -> dict[str, object]:
    return {
        "model": settings.model,
        "instructions": (
            "Produce competitor synthesis using only bounded sanitized StartupProfile "
            "fields and frozen competitor evidence/source summaries. Label the result "
            "as live inference, not live web research."
        ),
        "input": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        "text_format": OpenAICompetitorSynthesis,
        "store": False,
        "metadata": {
            "case_id": gate2.case_id,
            "run_id": gate2.run_id,
            "schema_version": SCHEMA_VERSION,
            "inference_label": "live_inference",
            "research_label": "not_live_web_research",
        },
        "max_output_tokens": min(settings.max_output_tokens, MAX_OUTPUT_TOKENS),
        "timeout": min(settings.timeout_seconds, 20.0),
    }


def _persist_evidence(
    output_root: Path,
    *,
    status: str,
    credential_present: bool,
    execute_live_requested: bool,
    live_call_attempted: bool,
    live_call_succeeded: bool,
    call_count: int,
    gate2: Gate2Evidence,
    profile: SanitizedStartupProfile,
    competitor_evidence_count: int,
    lineage: dict[str, str],
    source_summary_hashes: tuple[str, ...],
    result: OpenAICompetitorSynthesis | None,
    usage: dict[str, int],
    fail_reasons: Sequence[str],
    request_payload: Mapping[str, object],
    response_payload: Mapping[str, object] | None,
    error_code: str | None = None,
) -> Queue5OpenAICompetitorSmokeEvidence:
    privacy = _privacy_proof(request_payload, response_payload)
    settings = OpenAIStartupSettings()
    evidence = Queue5OpenAICompetitorSmokeEvidence(
        schema_version=SCHEMA_VERSION,
        status=status,
        credential_present=credential_present,
        execute_live_requested=execute_live_requested,
        live_call_attempted=live_call_attempted,
        live_call_succeeded=live_call_succeeded,
        call_count=call_count,
        inference_label="live_inference",
        research_label="not_live_web_research",
        gate2=gate2,
        startup_profile=profile,
        competitor_evidence_count=competitor_evidence_count,
        lineage=lineage,
        source_summary_hashes=source_summary_hashes,
        transport={"timeout_seconds": "20.0", "max_retries": "0"},
        result=result,
        budget={
            "max_usd": str(MAX_BUDGET_USD),
            "reserved_usd": str(
                min(settings.per_call_usd_reservation, MAX_BUDGET_USD)
            ),
            "worst_case_usd": str(
                min(settings.per_call_worst_case_usd_cost, MAX_BUDGET_USD)
            ),
            "max_output_tokens": str(MAX_OUTPUT_TOKENS),
        },
        usage=usage,
        cost_evidence=_cost_evidence_from_usage(settings=settings, usage=usage),
        privacy=privacy,
        semantic_hash="",
        error_code=error_code,
        artifact_paths={"evidence": EVIDENCE_FILENAME},
        fail_reasons=tuple(dict.fromkeys(fail_reasons)),
    )
    payload = evidence.to_json_dict()
    payload["semantic_hash"] = _semantic_hash(payload)
    _write_json(output_root / EVIDENCE_FILENAME, payload)
    return _evidence_from_payload(payload)


def _privacy_proof(
    request_payload: Mapping[str, object],
    response_payload: Mapping[str, object] | None,
) -> dict[str, object]:
    unsafe_payload_rejected = False
    try:
        validate_openai_competitor_payload_privacy(
            {
                "source_summary": "%PDF pitch.pdf C:\\secret\\founder@example.com",
                "prompt": "summarize raw document text",
            }
        )
    except ValueError:
        unsafe_payload_rejected = True
    leak_count = _privacy_leak_count(request_payload)
    if response_payload is not None:
        leak_count += _privacy_leak_count(response_payload)
    return {
        "request_payload_checked": True,
        "response_payload_checked": response_payload is not None,
        "unsafe_payload_rejected": unsafe_payload_rejected,
        "privacy_leak_count": leak_count,
    }


def _semantic_hash(payload: Mapping[str, object]) -> str:
    canonical = {
        str(key): value for key, value in payload.items() if key not in {"semantic_hash", "usage"}
    }
    if canonical.get("result") is None:
        canonical["result"] = None
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _evidence_from_payload(
    payload: Mapping[str, object],
) -> Queue5OpenAICompetitorSmokeEvidence:
    return Queue5OpenAICompetitorSmokeEvidence(
        schema_version=str(payload["schema_version"]),
        status=str(payload["status"]),
        credential_present=payload.get("credential_present") is True,
        execute_live_requested=payload.get("execute_live_requested") is True,
        live_call_attempted=payload.get("live_call_attempted") is True,
        live_call_succeeded=payload.get("live_call_succeeded") is True,
        call_count=int(cast(int, payload["call_count"])),
        inference_label=str(payload["inference_label"]),
        research_label=str(payload["research_label"]),
        gate2=Gate2Evidence.model_validate(payload["gate2"]),
        startup_profile=SanitizedStartupProfile.model_validate(payload["startup_profile"]),
        competitor_evidence_count=int(cast(int, payload["competitor_evidence_count"])),
        lineage={
            str(key): str(value)
            for key, value in cast(Mapping[str, object], payload["lineage"]).items()
        },
        source_summary_hashes=tuple(
            str(item) for item in cast(list[object], payload["source_summary_hashes"])
        ),
        transport={
            str(key): str(value)
            for key, value in cast(Mapping[str, object], payload["transport"]).items()
        },
        result=(
            OpenAICompetitorSynthesis.model_validate(payload["result"])
            if payload.get("result") is not None
            else None
        ),
        budget={
            str(key): str(value)
            for key, value in cast(Mapping[str, object], payload["budget"]).items()
        },
        usage={
            str(key): int(cast(int, value))
            for key, value in cast(Mapping[str, object], payload["usage"]).items()
        },
        cost_evidence={
            str(key): str(value)
            for key, value in cast(Mapping[str, object], payload["cost_evidence"]).items()
        },
        privacy=dict(cast(Mapping[str, object], payload["privacy"])),
        semantic_hash=str(payload["semantic_hash"]),
        error_code=(
            str(payload["error_code"])
            if payload.get("error_code") is not None
            else None
        ),
        artifact_paths={
            str(key): str(value)
            for key, value in cast(Mapping[str, object], payload["artifact_paths"]).items()
        },
        fail_reasons=tuple(str(item) for item in cast(list[object], payload["fail_reasons"])),
    )


def _usage_from_response(response: object) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if isinstance(usage, Mapping):
        input_tokens = _usage_int(usage.get("input_tokens", usage.get("prompt_tokens")))
        output_tokens = _usage_int(usage.get("output_tokens", usage.get("completion_tokens")))
        total_tokens = _usage_int(usage.get("total_tokens"))
    else:
        input_tokens = _usage_int(
            getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", None))
        )
        output_tokens = _usage_int(
            getattr(usage, "output_tokens", getattr(usage, "completion_tokens", None))
        )
        total_tokens = _usage_int(getattr(usage, "total_tokens", None))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _cost_evidence_from_usage(
    *,
    settings: OpenAIStartupSettings,
    usage: Mapping[str, int],
) -> dict[str, str]:
    input_tokens = Decimal(max(0, int(usage.get("input_tokens", 0))))
    output_tokens = Decimal(max(0, int(usage.get("output_tokens", 0))))
    estimated_cost = (
        input_tokens * settings.input_usd_per_million_tokens
        + output_tokens * settings.output_usd_per_million_tokens
    ) / Decimal(1_000_000)
    return {
        "currency": "USD",
        "pricing_model": settings.priced_model,
        "calculation": "estimated_from_observed_usage",
        "input_usd_per_million_tokens": str(settings.input_usd_per_million_tokens),
        "output_usd_per_million_tokens": str(settings.output_usd_per_million_tokens),
        "actual_or_estimated_usd": str(estimated_cost.quantize(Decimal("0.000001"))),
    }


def _usage_int(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int | float | str):
        return max(0, int(value))
    return 0


def _privacy_leak_count(value: object) -> int:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return len(_SENSITIVE_VALUE_RE.findall(serialized))


def _client_with_responses(client: object) -> _ClientWithResponses:
    return cast(_ClientWithResponses, client)


def _default_openai_client_factory(api_key: SecretStr | None) -> _OpenAIClientFactory:
    def create_client(**kwargs: object) -> object:
        module = importlib.import_module("openai")
        if api_key is not None:
            kwargs = {**kwargs, "api_key": api_key.get_secret_value()}
        return module.OpenAI(**kwargs)

    return create_client


def _openai_key_present() -> bool:
    settings = _OpenAICompetitorSettings()
    secret = settings.openai_api_key
    if secret is None:
        return False
    return bool(secret.get_secret_value())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="queue5-openai-competitor-smoke")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--execute-live", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_queue5_openai_competitor_smoke(
            Path(args.output_dir),
            execute_live=bool(args.execute_live),
        )
    except ValueError as exc:
        if str(exc) in EVALUATION_OUTPUT_ERROR_CODES:
            print(str(exc), file=sys.stderr)
            return 2
        raise
    print(json.dumps(result.to_json_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
