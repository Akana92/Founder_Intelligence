from __future__ import annotations

from pathlib import Path
from typing import cast

from due_diligence_agent.evals.startup_frozen_runtime import run_startup_frozen_runtime_eval


def test_startup_frozen_runtime_surfaces_unsupported_claims_from_uploaded_documents(
    tmp_path: Path,
) -> None:
    result = run_startup_frozen_runtime_eval(
        "startup_synthetic_v1",
        output_dir=tmp_path / "eval",
        repeat_determinism=False,
    )

    unsupported_claim_count = cast("int", result.queue2_assertions["unsupported_claim_count"])
    assert unsupported_claim_count >= 4
    assert {
        case.case_name
        for case in result.cases
        if case.unsupported_claim_count >= 1
    } == {"marketplace", "pre_revenue_service", "saas", "transactional"}
    assert not any(
        "unsupported_claim_runtime_evidence_missing" in reason
        for reason in result.fail_reasons
    )
