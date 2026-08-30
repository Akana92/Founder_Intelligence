from __future__ import annotations

from typing import Protocol, runtime_checkable

from due_diligence_agent.domain.startup.market import (
    StartupMarketResearchSnapshot,
    StartupResearchPlan,
)


@runtime_checkable
class StartupResearchPort(Protocol):
    def collect(self, plan: StartupResearchPlan) -> StartupMarketResearchSnapshot:
        ...
