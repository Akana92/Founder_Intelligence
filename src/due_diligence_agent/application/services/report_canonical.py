from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import subprocess

from due_diligence_agent.domain.reports.models import ReportSnapshot


STARTUP_REPORT_SECTION_KEYS = (
    "business_idea_summary",
    "problem_solution",
    "market_size",
    "competitors",
    "moat",
    "go_to_market",
    "metrics",
    "financial_assumptions",
    "risks",
    "evidence_gaps",
    "diligence_questions",
    "action_plan",
)
STARTUP_REPORT_SCHEMA = "startup_report_snapshot.v1"
STARTUP_REPORT_TEMPLATE_VERSION = "startup-report-template@1"
PUBLIC_REPORT_SCHEMA = "public_report_snapshot.v1"
PUBLIC_REPORT_TEMPLATE_VERSION = "public-report-template@1"
INTEGRITY_PREIMAGE_CONTRACT = "report_hash excludes artifact hash fields"


def canonical_json(payload: object, *, sort_keys: bool = True) -> bytes:
    return json.dumps(payload, sort_keys=sort_keys, separators=(",", ":"), default=str).encode("utf-8")


def canonical_snapshot_report_json(
    snapshot: ReportSnapshot,
    *,
    schema: str,
    sort_keys: bool = True,
) -> bytes:
    payload = snapshot.model_dump(
        mode="json",
        exclude={"json_artifact_ref", "html_artifact_ref", "pdf_artifact_ref", "content_hashes"},
    )
    payload["schema"] = schema
    payload["integrity_preimage_contract"] = INTEGRITY_PREIMAGE_CONTRACT
    return canonical_json(payload, sort_keys=sort_keys)


def sha256_bytes(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def package_versions(names: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = "not-installed"
    return result


def current_git_commit(project_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"
