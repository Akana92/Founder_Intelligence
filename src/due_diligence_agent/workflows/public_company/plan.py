from __future__ import annotations

from due_diligence_agent.workflows.shared.plan import AnalysisPlan, PlanStep


PUBLIC_NODE_REGISTRY: dict[str, str] = {
    "collect_sec": "SecCollectionResult",
    "collect_market": "MarketCollectionResult",
    "collect_news": "NewsCollectionResult",
    "retrieve": "RetrievalResult",
    "calculate": "MetricCalculationResult",
    "financial_analysis": "FindingResult",
    "risk_analysis": "FindingResult",
    "market_analysis": "FindingResult",
    "reflexion": "ReflexionDecision",
    "synthesize": "SynthesisReadiness",
}


def default_public_plan() -> AnalysisPlan:
    return validate_public_plan(
        AnalysisPlan(
            objectives=[
                "collect_public_evidence",
                "calculate_public_metrics",
                "review_public_findings",
            ],
            token_budget=12000,
            max_reflexion_rounds=2,
            steps=[
                PlanStep(
                    task_id="sec",
                    node_name="collect_sec",
                    required_output_schema="SecCollectionResult",
                ),
                PlanStep(
                    task_id="market",
                    node_name="collect_market",
                    required_output_schema="MarketCollectionResult",
                ),
                PlanStep(
                    task_id="news",
                    node_name="collect_news",
                    required_output_schema="NewsCollectionResult",
                ),
                PlanStep(
                    task_id="retrieve",
                    node_name="retrieve",
                    depends_on=["sec"],
                    required_output_schema="RetrievalResult",
                ),
                PlanStep(
                    task_id="calculate",
                    node_name="calculate",
                    depends_on=["sec", "market"],
                    required_output_schema="MetricCalculationResult",
                ),
                PlanStep(
                    task_id="financial",
                    node_name="financial_analysis",
                    depends_on=["calculate"],
                    required_output_schema="FindingResult",
                ),
                PlanStep(
                    task_id="risk",
                    node_name="risk_analysis",
                    depends_on=["financial"],
                    required_output_schema="FindingResult",
                ),
                PlanStep(
                    task_id="market_analysis",
                    node_name="market_analysis",
                    depends_on=["financial"],
                    required_output_schema="FindingResult",
                ),
                PlanStep(
                    task_id="reflexion",
                    node_name="reflexion",
                    depends_on=["risk", "market_analysis"],
                    required_output_schema="ReflexionDecision",
                ),
                PlanStep(
                    task_id="synthesize",
                    node_name="synthesize",
                    depends_on=["reflexion"],
                    required_output_schema="SynthesisReadiness",
                ),
            ],
        )
    )


def validate_public_plan(plan: AnalysisPlan) -> AnalysisPlan:
    task_ids = [step.task_id for step in plan.steps]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("plan.task_id.duplicate")
    known_tasks = set(task_ids)
    for step in plan.steps:
        expected_schema = PUBLIC_NODE_REGISTRY.get(step.node_name)
        if expected_schema is None:
            raise ValueError(f"plan.node.unsupported:{step.node_name}")
        if step.required_output_schema != expected_schema:
            raise ValueError(f"plan.schema.unregistered:{step.required_output_schema}")
        missing = [task_id for task_id in step.depends_on if task_id not in known_tasks]
        if missing:
            raise ValueError(f"plan.depends_on.unknown:{missing[0]}")
    _assert_acyclic(plan.steps)
    return plan


def _assert_acyclic(steps: list[PlanStep]) -> None:
    by_id = {step.task_id: step for step in steps}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError(f"plan.depends_on.cycle:{task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in by_id[task_id].depends_on:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for step in steps:
        visit(step.task_id)
