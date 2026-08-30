def test_stage1a_shared_contracts_are_available() -> None:
    from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator
    from due_diligence_agent.domain.evidence.models import EvidenceFact, Calculation
    from due_diligence_agent.domain.reports.models import ReportSnapshot
    from due_diligence_agent.domain.metrics.engine import MetricEngine
    from due_diligence_agent.application.policies.data_egress import DataEgressPolicy
    from due_diligence_agent.workflows.shared.node_result import NodeResult

    assert all([Artifact, SourceLocator, EvidenceFact, Calculation, ReportSnapshot, MetricEngine, DataEgressPolicy, NodeResult])
