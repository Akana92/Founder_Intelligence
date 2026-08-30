def test_gate_a_shared_foundation_contracts_are_importable() -> None:
    from due_diligence_agent.application.policies.budget import BudgetGuard
    from due_diligence_agent.application.policies.data_egress import DataEgressPolicy
    from due_diligence_agent.application.policies.model_routing import ModelRoutingPolicy
    from due_diligence_agent.domain.artifacts.models import Artifact, StoredArtifact
    from due_diligence_agent.domain.evidence.models import Calculation, EvidenceFact
    from due_diligence_agent.domain.reports.models import ReportSnapshot, ReproducibilityManifest
    from due_diligence_agent.ports.llm import CodeInterpreterPort, LLMGatewayPort
    from due_diligence_agent.ports.repositories import ArtifactStore, EvidenceRepository
    from due_diligence_agent.ports.tracing import AuditSpool, TraceSanitizer
    from due_diligence_agent.workflows.shared.node_result import NodeResult

    assert all(
        (
            Artifact,
            StoredArtifact,
            EvidenceFact,
            Calculation,
            ReportSnapshot,
            ReproducibilityManifest,
            ArtifactStore,
            EvidenceRepository,
            AuditSpool,
            TraceSanitizer,
            DataEgressPolicy,
            BudgetGuard,
            ModelRoutingPolicy,
            LLMGatewayPort,
            CodeInterpreterPort,
            NodeResult,
        )
    )
