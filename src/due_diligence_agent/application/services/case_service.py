from datetime import UTC, datetime
from uuid import uuid4

from due_diligence_agent.domain.cases.models import DueDiligenceCase
from due_diligence_agent.domain.common import AnalysisMode, CaseStatus, SensitivityClass
from due_diligence_agent.ports.repositories import CaseRepository


class CaseService:
    def __init__(self, case_repository: CaseRepository) -> None:
        self._case_repository = case_repository

    def create_public_case(
        self,
        ticker: str | None = None,
        entity_name: str | None = None,
        *,
        mode: AnalysisMode = AnalysisMode.PUBLIC_COMPANY,
        jurisdiction: str = "US_SEC",
        as_of: datetime | str | None = None,
        base_currency: str = "USD",
    ) -> DueDiligenceCase:
        if mode is not AnalysisMode.PUBLIC_COMPANY:
            raise ValueError("unsupported_mode")
        if isinstance(as_of, str):
            as_of = datetime.fromisoformat(f"{as_of}T00:00:00+00:00")
        normalized_ticker = (ticker or "").strip().upper()
        if not normalized_ticker:
            raise ValueError("ticker_required")
        if jurisdiction != "US_SEC":
            raise ValueError("unsupported_jurisdiction")

        now = datetime.now(UTC)
        case = DueDiligenceCase(
            case_id=uuid4(),
            mode=AnalysisMode.PUBLIC_COMPANY,
            entity_name=(entity_name or normalized_ticker).strip(),
            entity_identifier=normalized_ticker,
            jurisdiction="US_SEC",
            scope=("public_company_stage1a",),
            as_of=as_of or now,
            base_currency=base_currency.strip().upper(),
            privacy_policy="public-company-local@1",
            budget_policy="stage1a-local@1",
            status=CaseStatus.CREATED,
            sensitivity=SensitivityClass.PUBLIC,
            created_at=now,
            updated_at=now,
            workflow_version="public-company-local@1",
        )
        self._case_repository.add(case)
        return case
