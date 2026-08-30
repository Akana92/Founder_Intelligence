from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid4

import pytest

from due_diligence_agent.adapters.local_storage.case_copilot_repositories import (
    LocalCaseAssetRepository,
)
from due_diligence_agent.application.services import case_asset_service
from due_diligence_agent.application.services.case_asset_service import CaseAssetService
from due_diligence_agent.application.services.startup_scenario_service import StartupScenarioService
from due_diligence_agent.application.startup_cases import StartupGateConflict, StartupNotFound
from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import AnalysisMode, CaseStatus, SensitivityClass
from due_diligence_agent.domain.startup.case_intake import CaseValueKind
from due_diligence_agent.domain.startup.scenario import (
    ScenarioInput,
    ScenarioRange,
    StartupScenarioSet,
)

CASE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
CASE_B_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


def test_generate_gtm_launch_pack_is_draft_lineaged_and_replayable(tmp_path) -> None:
    case_repository = _CaseRepository({CASE_ID: 3})
    assumption_repository = _EmptyRepository()
    scenario_repository = _ScenarioRepository()
    public_benchmark_repository = _EmptyRepository()
    scenario_service = StartupScenarioService(
        case_repository=case_repository,
        assumption_repository=assumption_repository,
        scenario_repository=scenario_repository,
        public_benchmark_repository=public_benchmark_repository,
    )
    scenarios = scenario_service.build(
        CASE_ID,
        expected_case_revision=3,
        idempotency_key="scenario-build",
    )
    asset_repository = LocalCaseAssetRepository(
        tmp_path,
        current_revision=lambda case_id: case_repository.get(case_id).data_revision,
    )
    service = CaseAssetService(
        case_repository=case_repository,
        asset_repository=asset_repository,
        scenario_repository=scenario_repository,
        scenario_service=scenario_service,
    )

    draft = service.generate(
        CASE_ID,
        asset_type="gtm_launch_pack",
        selected_scenario_key="optimistic",
        expected_case_revision=3,
        idempotency_key="asset-1",
    )
    replay = service.generate(
        CASE_ID,
        asset_type="gtm_launch_pack",
        selected_scenario_key="optimistic",
        expected_case_revision=3,
        idempotency_key="asset-1",
    )

    assert replay == draft
    assert draft.status == "draft"
    assert draft.is_evidence is False
    assert draft.case_id == CASE_ID
    assert draft.data_revision == 3
    assert draft.scenario_set_id == scenarios.scenario_set_id
    assert draft.selected_scenario_key == "optimistic"
    assert draft.asset_key == "gtm_launch_pack"
    assert draft.draft_version == 1
    expected_headings = (
        "## Executive summary",
        "## Problem / solution / ICP / buyer / purchase trigger",
        "## Value proposition and positioning",
        "## Market, competitors, alternatives and citations",
        "## Business model and public pricing",
        "## Three-scenario unit economics",
        "## Experiments",
        "## Funnel and measurement",
        "## Strengths, weaknesses, risks and counter-thesis",
        "## 7/30/60/90 actions",
        "## Validation backlog",
        "## Provenance, assumptions and limitations",
    )
    assert (
        tuple(line for line in draft.body_markdown.splitlines() if line.startswith("## "))
        == expected_headings
    )
    assert "scenario | mrr | net_burn | runway" in draft.body_markdown
    assert "day_7" in draft.body_markdown
    assert "review_launch_evidence" in draft.body_markdown
    assert "provenance=ai_scenario" in draft.body_markdown
    assert "provenance=source_fact" not in draft.body_markdown
    assert "validation_plan=" in draft.body_markdown
    assert "formula=" in draft.body_markdown
    assert "dependencies=" in draft.body_markdown
    assert "source_refs=" in draft.body_markdown
    assert draft.metadata["scenario_set_id"] == str(scenarios.scenario_set_id)
    assert draft.metadata["selected_scenario_key"] == "optimistic"


def test_generate_rejects_stale_revision_before_write(tmp_path) -> None:
    case_repository = _CaseRepository({CASE_ID: 4})
    scenario_repository = _ScenarioRepository()
    scenario_service = StartupScenarioService(
        case_repository=case_repository,
        assumption_repository=_EmptyRepository(),
        scenario_repository=scenario_repository,
        public_benchmark_repository=_EmptyRepository(),
    )
    scenario_service.build(CASE_ID, expected_case_revision=4, idempotency_key="scenario-build")
    asset_repository = LocalCaseAssetRepository(
        tmp_path,
        current_revision=lambda case_id: case_repository.get(case_id).data_revision,
    )
    service = CaseAssetService(
        case_repository=case_repository,
        asset_repository=asset_repository,
        scenario_repository=scenario_repository,
        scenario_service=scenario_service,
    )

    with pytest.raises(StartupGateConflict, match="case_revision_conflict"):
        service.generate(
            CASE_ID,
            asset_type="gtm_launch_pack",
            selected_scenario_key="base",
            expected_case_revision=3,
            idempotency_key="asset-1",
        )

    assert service.list(CASE_ID) == ()


def test_generate_rebuilds_stale_current_scenario_set_for_expected_revision(tmp_path) -> None:
    revisions = {CASE_ID: 3}
    case_repository = _CaseRepository(revisions)
    scenario_repository = _ScenarioRepository()
    scenario_service = StartupScenarioService(
        case_repository=case_repository,
        assumption_repository=_EmptyRepository(),
        scenario_repository=scenario_repository,
        public_benchmark_repository=_EmptyRepository(),
    )
    stale_scenarios = scenario_service.build(
        CASE_ID,
        expected_case_revision=3,
        idempotency_key="scenario-build-3",
    )
    revisions[CASE_ID] = 4
    service = CaseAssetService(
        case_repository=case_repository,
        asset_repository=LocalCaseAssetRepository(
            tmp_path,
            current_revision=lambda case_id: case_repository.get(case_id).data_revision,
        ),
        scenario_repository=scenario_repository,
        scenario_service=scenario_service,
    )

    draft = service.generate(
        CASE_ID,
        asset_type="gtm_launch_pack",
        selected_scenario_key="base",
        expected_case_revision=4,
        idempotency_key="asset-1",
    )
    current_scenarios = scenario_repository.get_current(CASE_ID)

    assert draft.status == "draft"
    assert draft.data_revision == 4
    assert current_scenarios.data_revision == 4
    assert draft.scenario_set_id == current_scenarios.scenario_set_id
    assert draft.scenario_set_id != stale_scenarios.scenario_set_id
    assert "data_revision=4" in draft.body_markdown
    assert "provenance=ai_scenario" in draft.body_markdown
    assert "provenance=source_fact" not in draft.body_markdown


def test_generate_uses_current_profile_gtm_and_report_when_available(tmp_path) -> None:
    case_repository = _CaseRepository({CASE_ID: 3})
    scenario_repository = _ScenarioRepository()
    scenario_service = StartupScenarioService(
        case_repository=case_repository,
        assumption_repository=_EmptyRepository(),
        scenario_repository=scenario_repository,
        public_benchmark_repository=_EmptyRepository(),
    )
    scenario_service.build(CASE_ID, expected_case_revision=3, idempotency_key="scenario-build")
    service = CaseAssetService(
        case_repository=case_repository,
        asset_repository=LocalCaseAssetRepository(
            tmp_path,
            current_revision=lambda case_id: case_repository.get(case_id).data_revision,
        ),
        scenario_repository=scenario_repository,
        scenario_service=scenario_service,
        profile_repository=_ProfileRepository(data_revision=3),
        gtm_query=_GtmRepository(data_revision=3),
        report_repository=_ReportSnapshotRepository(data_revision=3),
    )

    draft = service.generate(
        CASE_ID,
        asset_type="gtm_launch_pack",
        selected_scenario_key="base",
        expected_case_revision=3,
        idempotency_key="asset-1",
    )

    assert "Problem: Pharmacy stock-outs" in draft.body_markdown
    assert "ICP: Regional pharmacy chains" in draft.body_markdown
    assert "Market: Kazakhstan pharmacy operations from report sections." in draft.body_markdown
    assert "Risk: Store manager adoption risk from report sections." in draft.body_markdown
    assert "day_7: clarify_audience" in draft.body_markdown
    assert "Missing current profile projection" not in draft.body_markdown


def test_generate_marks_missing_profile_gtm_and_report_context_explicitly(tmp_path) -> None:
    case_repository = _CaseRepository({CASE_ID: 3})
    scenario_repository = _ScenarioRepository()
    scenario_service = StartupScenarioService(
        case_repository=case_repository,
        assumption_repository=_EmptyRepository(),
        scenario_repository=scenario_repository,
        public_benchmark_repository=_EmptyRepository(),
    )
    scenario_service.build(CASE_ID, expected_case_revision=3, idempotency_key="scenario-build")
    service = CaseAssetService(
        case_repository=case_repository,
        asset_repository=LocalCaseAssetRepository(
            tmp_path,
            current_revision=lambda case_id: case_repository.get(case_id).data_revision,
        ),
        scenario_repository=scenario_repository,
        scenario_service=scenario_service,
    )

    draft = service.generate(
        CASE_ID,
        asset_type="gtm_launch_pack",
        selected_scenario_key="base",
        expected_case_revision=3,
        idempotency_key="asset-1",
    )

    assert "Missing current profile projection" in draft.body_markdown
    assert "Missing current report projection" in draft.body_markdown
    assert "Missing current GTM projection" in draft.body_markdown
    assert "from current case profile/report context" not in draft.body_markdown


def test_get_rejects_cross_case_asset_access(tmp_path) -> None:
    revisions = {CASE_ID: 3, CASE_B_ID: 3}
    case_repository = _CaseRepository(revisions)
    scenario_repository = _ScenarioRepository()
    scenario_service = StartupScenarioService(
        case_repository=case_repository,
        assumption_repository=_EmptyRepository(),
        scenario_repository=scenario_repository,
        public_benchmark_repository=_EmptyRepository(),
    )
    scenario_service.build(CASE_ID, expected_case_revision=3, idempotency_key="scenario-a")
    scenario_service.build(CASE_B_ID, expected_case_revision=3, idempotency_key="scenario-b")
    service = CaseAssetService(
        case_repository=case_repository,
        asset_repository=LocalCaseAssetRepository(
            tmp_path,
            current_revision=lambda case_id: case_repository.get(case_id).data_revision,
        ),
        scenario_repository=scenario_repository,
        scenario_service=scenario_service,
    )
    draft = service.generate(
        CASE_ID,
        asset_type="gtm_launch_pack",
        selected_scenario_key="base",
        expected_case_revision=3,
        idempotency_key="asset-1",
    )

    with pytest.raises(StartupNotFound, match="asset_not_found"):
        service.get(CASE_B_ID, draft.draft_id)


def test_base_assets_use_dedicated_templates_and_weekly_funnel_csv(tmp_path) -> None:
    case_repository = _CaseRepository({CASE_ID: 3})
    scenario_repository = _ScenarioRepository()
    scenario_service = StartupScenarioService(
        case_repository=case_repository,
        assumption_repository=_EmptyRepository(),
        scenario_repository=scenario_repository,
        public_benchmark_repository=_EmptyRepository(),
    )
    scenario_service.build(CASE_ID, expected_case_revision=3, idempotency_key="scenario")
    service = CaseAssetService(
        case_repository=case_repository,
        asset_repository=LocalCaseAssetRepository(
            tmp_path,
            current_revision=lambda case_id: case_repository.get(case_id).data_revision,
        ),
        scenario_repository=scenario_repository,
        scenario_service=scenario_service,
    )

    expectations = {
        "customer_interview_script": ("Pain validation interview script", "Pain questions"),
        "pricing_experiment": ("Pricing hypothesis", "Success criteria"),
        "positioning_map": ("Positioning comparison", "Primary alternative"),
        "weekly_funnel_template": ("Weekly funnel stages and definitions", "Weekly input fields"),
    }
    for asset_type, required in expectations.items():
        draft = service.generate(
            CASE_ID,
            asset_type=asset_type,  # type: ignore[arg-type]
            selected_scenario_key="base",
            expected_case_revision=3,
            idempotency_key=f"asset:{asset_type}",
        )
        for text in required:
            assert text in draft.body_markdown
        assert "## Scenario metric provenance" in draft.body_markdown
        assert "provenance=" in draft.body_markdown
        assert "formula=" in draft.body_markdown
        assert "dependencies=" in draft.body_markdown
        assert "validation_plan=" in draft.body_markdown

    weekly = service.generate(
        CASE_ID,
        asset_type="weekly_funnel_template",
        selected_scenario_key="base",
        expected_case_revision=3,
        idempotency_key="asset:weekly-replay",
    )
    assert service.csv_content(CASE_ID, weekly.draft_id) == (
        "week_start,visitors,signups,qualified_conversations,pilots_started,paid_conversions,notes,source_ref\n"
        ",,,,,,,"
    )


def test_idempotency_rejects_stale_revision_and_new_key_increments_version(tmp_path) -> None:
    revisions = {CASE_ID: 3}
    case_repository = _CaseRepository(revisions)
    scenario_repository = _ScenarioRepository()
    scenario_service = StartupScenarioService(
        case_repository=case_repository,
        assumption_repository=_EmptyRepository(),
        scenario_repository=scenario_repository,
        public_benchmark_repository=_EmptyRepository(),
    )
    scenario_service.build(CASE_ID, expected_case_revision=3, idempotency_key="scenario-3")
    asset_repository = LocalCaseAssetRepository(
        tmp_path,
        current_revision=lambda case_id: case_repository.get(case_id).data_revision,
    )
    service = CaseAssetService(
        case_repository=case_repository,
        asset_repository=asset_repository,
        scenario_repository=scenario_repository,
        scenario_service=scenario_service,
    )
    first = service.generate(
        CASE_ID,
        asset_type="gtm_launch_pack",
        selected_scenario_key="base",
        expected_case_revision=3,
        idempotency_key="asset-1",
    )
    second = service.generate(
        CASE_ID,
        asset_type="gtm_launch_pack",
        selected_scenario_key="base",
        expected_case_revision=3,
        idempotency_key="asset-2",
    )

    assert first.draft_version == 1
    assert second.draft_version == 2

    revisions[CASE_ID] = 4
    scenario_service.build(CASE_ID, expected_case_revision=4, idempotency_key="scenario-4")
    with pytest.raises(StartupGateConflict, match="idempotency_key_conflict"):
        service.generate(
            CASE_ID,
            asset_type="gtm_launch_pack",
            selected_scenario_key="base",
            expected_case_revision=4,
            idempotency_key="asset-1",
        )


def test_restart_safe_list_get_and_idempotent_replay(tmp_path) -> None:
    case_repository = _CaseRepository({CASE_ID: 3})
    scenario_repository = _ScenarioRepository()
    scenario_service = StartupScenarioService(
        case_repository=case_repository,
        assumption_repository=_EmptyRepository(),
        scenario_repository=scenario_repository,
        public_benchmark_repository=_EmptyRepository(),
    )
    scenario_service.build(CASE_ID, expected_case_revision=3, idempotency_key="scenario")
    service = CaseAssetService(
        case_repository=case_repository,
        asset_repository=LocalCaseAssetRepository(
            tmp_path,
            current_revision=lambda case_id: case_repository.get(case_id).data_revision,
        ),
        scenario_repository=scenario_repository,
        scenario_service=scenario_service,
    )
    draft = service.generate(
        CASE_ID,
        asset_type="gtm_launch_pack",
        selected_scenario_key="base",
        expected_case_revision=3,
        idempotency_key="asset-1",
    )
    restarted = CaseAssetService(
        case_repository=case_repository,
        asset_repository=LocalCaseAssetRepository(
            tmp_path,
            current_revision=lambda case_id: case_repository.get(case_id).data_revision,
        ),
        scenario_repository=scenario_repository,
        scenario_service=scenario_service,
    )

    assert restarted.get(CASE_ID, draft.draft_id) == draft
    assert restarted.list(CASE_ID) == (draft,)
    assert (
        restarted.generate(
            CASE_ID,
            asset_type="gtm_launch_pack",
            selected_scenario_key="base",
            expected_case_revision=3,
            idempotency_key="asset-1",
        )
        == draft
    )


def test_generate_uses_production_shaped_profile_gtm_and_report_repositories(tmp_path) -> None:
    case_repository = _CaseRepository({CASE_ID: 3})
    scenario_repository = _ScenarioRepository()
    scenario_service = StartupScenarioService(
        case_repository=case_repository,
        assumption_repository=_EmptyRepository(),
        scenario_repository=scenario_repository,
        public_benchmark_repository=_EmptyRepository(),
    )
    scenario_service.build(CASE_ID, expected_case_revision=3, idempotency_key="scenario")
    service = CaseAssetService(
        case_repository=case_repository,
        asset_repository=LocalCaseAssetRepository(
            tmp_path,
            current_revision=lambda case_id: case_repository.get(case_id).data_revision,
        ),
        scenario_repository=scenario_repository,
        scenario_service=scenario_service,
        profile_repository=_ProfileMappingRepository(data_revision=3),
        gtm_query=_GtmStringRepository(data_revision=3),
        report_repository=_ReportSnapshotRepository(data_revision=3),
    )

    draft = service.generate(
        CASE_ID,
        asset_type="gtm_launch_pack",
        selected_scenario_key="base",
        expected_case_revision=3,
        idempotency_key="asset-1",
    )

    assert "Problem: Pharmacy stock-outs from mapping" in draft.body_markdown
    assert "Market: Kazakhstan pharmacy operations from report sections." in draft.body_markdown
    assert "Risk: Store manager adoption risk from report sections." in draft.body_markdown


def test_gtm_launch_pack_includes_business_plan_appendix_from_semantic_context(
    tmp_path,
) -> None:
    appendix_source = case_asset_service._business_plan_context_appendix.__code__.co_consts
    assert "Smart University" not in repr(appendix_source)
    assert "smart university" not in repr(appendix_source).casefold()

    case_repository = _CaseRepository({CASE_ID: 3})
    scenario_repository = _ScenarioRepository()
    scenario_service = StartupScenarioService(
        case_repository=case_repository,
        assumption_repository=_EmptyRepository(),
        scenario_repository=scenario_repository,
        public_benchmark_repository=_EmptyRepository(),
    )
    scenario_service.build(CASE_ID, expected_case_revision=3, idempotency_key="scenario")
    service = CaseAssetService(
        case_repository=case_repository,
        asset_repository=LocalCaseAssetRepository(
            tmp_path,
            current_revision=lambda case_id: case_repository.get(case_id).data_revision,
        ),
        scenario_repository=scenario_repository,
        scenario_service=scenario_service,
        profile_repository=_SmartUniversityProfileRepository(data_revision=3),
        report_repository=_SmartUniversityReportRepository(data_revision=3),
    )

    draft = service.generate(
        CASE_ID,
        asset_type="gtm_launch_pack",
        selected_scenario_key="base",
        expected_case_revision=3,
        idempotency_key="asset-1",
    )

    assert tuple(line for line in draft.body_markdown.splitlines() if line.startswith("## ")) == (
        "## Executive summary",
        "## Problem / solution / ICP / buyer / purchase trigger",
        "## Value proposition and positioning",
        "## Market, competitors, alternatives and citations",
        "## Business model and public pricing",
        "## Three-scenario unit economics",
        "## Experiments",
        "## Funnel and measurement",
        "## Strengths, weaknesses, risks and counter-thesis",
        "## 7/30/60/90 actions",
        "## Validation backlog",
        "## Provenance, assumptions and limitations",
    )
    required_appendix_markers = (
        "Platform thesis",
        "Pricing/tariff economics",
        "Starter 240 000 KZT/month",
        "Lead/conversion economics",
        "lead-cost examples are public benchmarks only",
        "Rating methodology",
        "B2B pilot plan",
        "Housing decision tree",
        "Tranche plan",
        "Provenance appendix",
        "35.2M KZT platform round",
        "8.0M KZT Housing Management pilot",
        "2027-2031 revenue and EBITDA are forecasts",
        "2027, 2028, 2029, 2030 and 2031",
    )
    for marker in required_appendix_markers:
        assert marker in draft.body_markdown
    assert "### Business-plan context appendix" in draft.body_markdown
    assert "43.2M" not in draft.body_markdown
    assert "provenance=source_fact" not in draft.body_markdown


def test_business_plan_appendix_uses_cited_public_price_when_private_pricing_is_missing() -> None:
    profile = _SmartUniversityProfileRepository(
        data_revision=3,
        include_pricing=False,
    ).get_current(CASE_ID)
    report = _SmartUniversityReportRepository(data_revision=3).get_current_draft(CASE_ID)
    public_price = ScenarioInput(
        case_id=CASE_ID,
        data_revision=3,
        input_key="monthly_price",
        value_range=ScenarioRange(lower=Decimal(1000), upper=Decimal(2000)),
        unit="KZT",
        period="month",
        provenance=CaseValueKind.PUBLIC_BENCHMARK,
        source_refs=(uuid4(),),
        confidence="medium",
        rationale="Cited public pricing analog.",
        validation_plan="Validate against the founder-specific tariff before external use.",
        acceptance="proposed",
    )
    selected = type(
        "SelectedScenario",
        (),
        {"inputs": MappingProxyType({"monthly_price": public_price})},
    )()

    appendix = case_asset_service._business_plan_context_appendix(
        {"profile": profile, "report": report},
        selected,
    )

    assert "### Business-plan context appendix" in appendix
    assert "Pricing/tariff economics" in appendix
    assert "provenance=public_benchmark" in appendix
    assert "provenance=source_fact" not in appendix


class _CaseRepository:
    def __init__(self, revisions: dict[UUID, int]) -> None:
        self._revisions = revisions

    def get(self, case_id: UUID) -> DueDiligenceCase:
        return DueDiligenceCase(
            case_id=case_id,
            mode=AnalysisMode.STARTUP,
            entity_name=f"Case {case_id}",
            entity_identifier=str(case_id),
            jurisdiction="unknown",
            scope=("startup_case_copilot",),
            as_of=datetime(2026, 8, 22, tzinfo=UTC),
            base_currency="USD",
            privacy_policy="startup_local_private",
            budget_policy="offline_deterministic",
            status=CaseStatus.AWAITING_EVIDENCE,
            sensitivity=SensitivityClass.CONFIDENTIAL,
            created_at=datetime(2026, 8, 22, tzinfo=UTC),
            updated_at=datetime(2026, 8, 22, tzinfo=UTC),
            workflow_version="startup-case-copilot-v1",
            data_revision=self._revisions[case_id],
        )


class _ScenarioRepository:
    def __init__(self) -> None:
        self._current: dict[UUID, StartupScenarioSet] = {}
        self._idempotency: dict[tuple[UUID, str], StartupScenarioSet] = {}

    def save(
        self,
        value: StartupScenarioSet,
        *,
        expected_revision: int,
        idempotency_key: str,
    ) -> StartupScenarioSet:
        key = (value.case_id, idempotency_key)
        existing = self._idempotency.get(key)
        if existing is not None:
            return existing
        if value.data_revision != expected_revision:
            raise ValueError("case_revision_conflict")
        self._current[value.case_id] = value
        self._idempotency[key] = value
        return value

    def get_current(self, case_id: UUID) -> StartupScenarioSet:
        return self._current[case_id]

    def get_by_idempotency(self, case_id: UUID, idempotency_key: str) -> StartupScenarioSet | None:
        return self._idempotency.get((case_id, idempotency_key))


class _EmptyRepository:
    def get_current(self, _case_id: UUID) -> tuple[()]:
        return ()


class _ProfileRepository:
    def __init__(self, *, data_revision: int) -> None:
        self._profile = type(
            "Profile",
            (),
            {
                "data_revision": data_revision,
                "fields": {
                    "problem": type("Field", (), {"values": ("Pharmacy stock-outs",)})(),
                    "solution": type("Field", (), {"values": ("AI replenishment planner",)})(),
                    "icp": type("Field", (), {"values": ("Regional pharmacy chains",)})(),
                    "buyers": type("Field", (), {"values": ("Operations directors",)})(),
                    "pricing_revenue_model": type(
                        "Field", (), {"values": ("Monthly subscription",)}
                    )(),
                    "competitors_mentioned": type(
                        "Field", (), {"values": ("Manual Excel tracking",)}
                    )(),
                },
            },
        )()

    def get_current(self, _case_id: UUID) -> object:
        return self._profile


class _GtmRepository:
    def __init__(self, *, data_revision: int) -> None:
        self._snapshot = type(
            "Gtm",
            (),
            {
                "data_revision": data_revision,
                "launch_plan": (),
            },
        )()

    def get_current(self, _case_id: UUID) -> object:
        return self._snapshot


class _ReportRepository:
    def __init__(self, *, data_revision: int) -> None:
        self._report = type(
            "Report",
            (),
            {
                "data_revision": data_revision,
                "market": "Kazakhstan pharmacy operations",
                "risks": ("Adoption depends on store manager workflow change.",),
            },
        )()

    def get_current(self, _case_id: UUID) -> object:
        return self._report


class _ProfileMappingRepository:
    def __init__(self, *, data_revision: int) -> None:
        def field(*values: str) -> object:
            return type("Field", (), {"values": values})()

        self._profile = type(
            "Profile",
            (),
            {
                "data_revision": data_revision,
                "fields": MappingProxyType(
                    {
                        "problem": field("Pharmacy stock-outs from mapping"),
                        "solution": field("AI replenishment planner"),
                        "icp": field("Regional pharmacy chains"),
                        "buyers": field("Operations directors"),
                        "pricing_revenue_model": field("Monthly subscription"),
                        "competitors_mentioned": field("Manual Excel tracking"),
                    }
                ),
            },
        )()

    def get_current(self, _case_id: UUID) -> object:
        return self._profile


class _GtmStringRepository:
    def __init__(self, *, data_revision: int) -> None:
        self._snapshot = type(
            "Gtm",
            (),
            {
                "data_revision": data_revision,
                "launch_plan": (),
            },
        )()

    def get_current(self, case_id: str) -> object:
        assert isinstance(case_id, str)
        return self._snapshot


class _ReportSnapshotRepository:
    def __init__(self, *, data_revision: int) -> None:
        self._report = type(
            "ReportSnapshot",
            (),
            {
                "data_revision": data_revision,
                "version": 1,
                "sections": MappingProxyType(
                    {
                        "market_size": MappingProxyType(
                            {
                                "summary_ru": "Kazakhstan pharmacy operations from report sections.",
                            }
                        ),
                        "risks": MappingProxyType(
                            {
                                "summary_ru": "Store manager adoption risk from report sections.",
                            }
                        ),
                    }
                ),
            },
        )()

    def get_current_draft(self, _case_id: UUID) -> object:
        return self._report


class _SmartUniversityProfileRepository:
    def __init__(self, *, data_revision: int, include_pricing: bool = True) -> None:
        def field(*values: str) -> object:
            return type("Field", (), {"values": values})()

        pricing_values = (
            ("Starter 240 000 KZT/month; tariff economics remain assumptions.",)
            if include_pricing
            else ()
        )
        self._profile = type(
            "Profile",
            (),
            {
                "data_revision": data_revision,
                "fields": MappingProxyType(
                    {
                        "problem": field(
                            "Students and parents need trusted university program discovery."
                        ),
                        "solution": field(
                            "AI-powered platform for university program discovery; "
                            "Housing Management vertical is a separate later gate."
                        ),
                        "icp": field("Kazakhstan universities and education agents"),
                        "buyers": field("university admissions and agent partnership teams"),
                        "pricing_revenue_model": field(*pricing_values),
                        "competitors_mentioned": field("manual agents and aggregator portals"),
                        "assumptions": field(
                            "rating methodology combines program fit and affordability; "
                            "35.2M KZT platform round is separate from "
                            "8.0M KZT Housing Management pilot; "
                            "2027-2031 revenue and EBITDA are forecasts."
                        ),
                        "weaknesses": field(
                            "privacy consent, rating appeals, anti-fraud and Housing "
                            "legal/fire/sanitary gates."
                        ),
                    }
                ),
            },
        )()

    def get_current(self, _case_id: UUID) -> object:
        return self._profile


class _SmartUniversityReportRepository:
    def __init__(self, *, data_revision: int) -> None:
        self._report = type(
            "ReportSnapshot",
            (),
            {
                "data_revision": data_revision,
                "version": 1,
                "sections": MappingProxyType(
                    {
                        "market_size": MappingProxyType(
                            {
                                "summary_ru": (
                                    "TAM = students applying abroad * serviceable "
                                    "platform fee; lead-cost examples are public "
                                    "benchmarks only."
                                ),
                            }
                        ),
                        "risks": MappingProxyType(
                            {
                                "summary_ru": (
                                    "commercial traction, data freshness/SLA, rating "
                                    "anti-fraud and appeals, privacy/legal/tax, and "
                                    "housing legal/fire/sanitary gates."
                                ),
                            }
                        ),
                    }
                ),
            },
        )()

    def get_current_draft(self, _case_id: UUID) -> object:
        return self._report
