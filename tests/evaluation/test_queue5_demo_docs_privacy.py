from pathlib import Path

import pytest

from due_diligence_agent.evals import sellable_demo_freeze


PROJECT_ROOT = Path(__file__).parents[2]
DEMO_DOCS = (
    PROJECT_ROOT / "docs" / "demo" / "2026-08-16-sellable-demo-script.md",
    PROJECT_ROOT / "docs" / "demo" / "2026-08-16-capstone-requirement-evidence-map.md",
)


@pytest.mark.parametrize("document_path", DEMO_DOCS, ids=lambda path: path.name)
def test_queue5_demo_documents_pass_packet_privacy_scan(document_path: Path) -> None:
    document = document_path.read_text(encoding="utf-8")

    assert sellable_demo_freeze._privacy_leak_count((document,)) == 0


def test_packet_privacy_scan_allows_policy_prose_about_bearer_tokens() -> None:
    assert sellable_demo_freeze._privacy_leak_count(("reject any bearer token",)) == 0


def test_packet_privacy_scan_rejects_a_plausible_bearer_credential() -> None:
    synthetic_credential = "bearer " + "a" * 32

    assert sellable_demo_freeze._privacy_leak_count((synthetic_credential,)) == 1
