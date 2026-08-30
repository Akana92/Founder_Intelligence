from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class EvaluationResult:
    dataset: str
    schema_validity: float
    critical_evidence_coverage: float
    unsupported_critical_claim_rate: float
    numerical_accuracy: float
    unit_period_consistency: float
    retrieval_recall_at_5: float
    privacy_leak_count: int
    trace_completeness: float
    reflexion_max_rounds: int
    budget_violations: int
    offline_latency_minutes: float
    report_completeness: float
    exporter_outage_non_blocking: bool
    checkpoint_recovery: bool
    gate_b_passed: bool
    fail_reasons: tuple[str, ...] = ()
    artifact_paths: dict[str, str] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["fail_reasons"] = list(self.fail_reasons)
        return payload
