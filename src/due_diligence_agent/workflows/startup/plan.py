from __future__ import annotations

from due_diligence_agent.workflows.shared.plan import AnalysisPlan, PlanStep


STARTUP_NODE_REGISTRY: tuple[str, ...] = (
    "ingest",
    "parse",
    "classify_redact",
    "evidence",
    "claims",
    "document_intelligence",
    "primary_profile",
    "disclosure",
    "profile_enrichment",
    "product_validation",
    "market_research",
    "metrics",
    "financial_analysis",
    "risk_analysis",
    "market_analysis",
    "gtm",
    "critic",
    "arbiter",
    "report",
    "gate4",
)


STARTUP_PLAN_ID = "startup_data_room@1"


def default_startup_plan() -> AnalysisPlan:
    return validate_startup_plan(
        AnalysisPlan(
            objectives=[
                "Assess uploaded startup data-room materials using local deterministic evidence first.",
                "Use external LLM analysis only after explicit startup disclosure approval.",
                "Produce an immutable report snapshot from repository IDs and dependency edges.",
            ],
            steps=[
                PlanStep(
                    task_id=f"startup:{node_name}",
                    node_name=node_name,
                    depends_on=_depends_on(node_name),
                    required_output_schema=f"{node_name}_node_result@1",
                )
                for node_name in STARTUP_NODE_REGISTRY
            ],
            token_budget=18_000,
            max_reflexion_rounds=2,
        )
    )


def validate_startup_plan(plan: AnalysisPlan) -> AnalysisPlan:
    actual = tuple(step.node_name for step in plan.steps)
    if actual != STARTUP_NODE_REGISTRY:
        raise ValueError("startup_plan.registry_mismatch")
    for step in plan.steps:
        if step.node_name not in STARTUP_NODE_REGISTRY:
            raise ValueError(f"startup_plan.unregistered_node:{step.node_name}")
    if plan.max_reflexion_rounds > 2:
        raise ValueError("startup_plan.reflexion_rounds_exceeded")
    _assert_acyclic(plan.steps)
    return plan


def _assert_acyclic(steps: list[PlanStep]) -> None:
    by_id = {step.task_id: step for step in steps}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError(f"startup_plan.depends_on.cycle:{task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in by_id[task_id].depends_on:
            if dependency not in by_id:
                raise ValueError(f"startup_plan.depends_on.unknown:{dependency}")
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for step in steps:
        visit(step.task_id)


def _depends_on(node_name: str) -> list[str]:
    dependencies: dict[str, list[str]] = {
        "ingest": [],
        "parse": ["ingest"],
        "classify_redact": ["parse"],
        "evidence": ["classify_redact"],
        "claims": ["evidence"],
        "document_intelligence": ["claims"],
        "primary_profile": ["document_intelligence"],
        "disclosure": ["primary_profile"],
        "profile_enrichment": ["disclosure"],
        "product_validation": ["profile_enrichment"],
        "market_research": ["product_validation"],
        "metrics": ["product_validation", "evidence"],
        "financial_analysis": ["claims", "metrics"],
        "risk_analysis": ["claims", "metrics", "financial_analysis"],
        "market_analysis": [
            "claims",
            "risk_analysis",
            "market_research",
            "product_validation",
        ],
        "gtm": [
            "profile_enrichment",
            "product_validation",
            "market_research",
            "market_analysis",
        ],
        "critic": [
            "financial_analysis",
            "risk_analysis",
            "market_analysis",
            "gtm",
        ],
        "arbiter": ["critic"],
        "report": ["arbiter"],
        "gate4": ["report"],
    }
    return [f"startup:{dependency}" for dependency in dependencies[node_name]]
