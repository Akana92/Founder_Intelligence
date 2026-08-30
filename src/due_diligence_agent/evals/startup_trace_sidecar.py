from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Final, TypedDict

from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.application.services.startup_trace_query_service import (
    StartupTraceQueryService,
)
from due_diligence_agent.workflows.startup.tracing import startup_agent_role


REQUIRED_PDF_JOURNEY_NODES: Final[frozenset[str]] = frozenset(
    {
        "disclosure",
        "document_intelligence",
        "gtm",
        "market_analysis",
        "market_research",
        "metrics",
        "primary_profile",
        "product_validation",
        "profile_enrichment",
        "critic",
        "arbiter",
        "report",
        "gate4",
    }
)
_SUCCESS_STATUSES: Final[frozenset[str]] = frozenset({"completed", "success"})
_COVERED_POLICY_BLOCK_ERROR_CODES: Final[frozenset[str]] = frozenset(
    {"blocked_by_policy:startup_disclosure"}
)
_SAFE_CHECKSUM_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


class StartupTraceSidecarNode(TypedDict):
    case_id: str
    run_id: str
    node: str
    agent_role: str
    attempt: int | None
    retry_count: int | None
    status: str | None
    error_code: str | None
    duration_ms: float | None
    tool: str | None
    evidence_count: int | None
    fallback_used: str | None
    timeout_ms: float | None


class StartupTraceSidecarLineage(TypedDict):
    decision: str
    gate4_status: str
    report_id: str
    report_revision: int
    report_checksum: str


class StartupTraceSidecarHealth(TypedDict):
    provider: str
    status: str
    error_code: str
    fallback_used: str


class StartupTraceSidecarExporterHealth(TypedDict):
    status: str
    error_code: str
    fallback_used: str


class StartupTraceSidecarUsage(TypedDict):
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cost_usd: str | None


class StartupTraceSidecar(TypedDict):
    schema_version: str
    case_id: str
    run_id: str
    node_rows: list[StartupTraceSidecarNode]
    usage_summary: StartupTraceSidecarUsage
    report_lineage: StartupTraceSidecarLineage
    exporter_health: StartupTraceSidecarExporterHealth | None
    langsmith_health: StartupTraceSidecarHealth


def build_startup_trace_sidecar(
    *,
    audit_spool_root: Path,
    case_id: str,
    run_id: str,
) -> StartupTraceSidecar:
    if not audit_spool_root.is_dir():
        raise ValueError("startup_trace_sidecar_audit_root_missing")

    view = StartupTraceQueryService(JsonlAuditSpool(audit_spool_root)).get_view(
        case_id,
        run_id,
        max_events=200,
    )
    rows = [
        StartupTraceSidecarNode(
            case_id=row.case_id,
            run_id=row.run_id,
            node=row.node,
            agent_role=startup_agent_role(row.node),
            attempt=row.attempt,
            retry_count=row.retry_count,
            status=row.status,
            error_code=row.error_code,
            duration_ms=row.latency_ms,
            tool=row.tool,
            evidence_count=row.evidence_count,
            fallback_used=row.fallback_used,
            timeout_ms=row.timeout_ms,
        )
        for row in view.node_rows
        if row.node is not None
    ]
    if any(row["case_id"] != case_id or row["run_id"] != run_id for row in rows):
        raise ValueError("startup_trace_sidecar_case_mismatch")

    covered_nodes = {
        row["node"]
        for row in rows
        if row["status"] in _SUCCESS_STATUSES
        or (
            row["status"] == "blocked"
            and row["error_code"] in _COVERED_POLICY_BLOCK_ERROR_CODES
        )
    }
    if not REQUIRED_PDF_JOURNEY_NODES.issubset(covered_nodes):
        missing = ",".join(sorted(REQUIRED_PDF_JOURNEY_NODES - covered_nodes))
        raise ValueError(f"startup_trace_sidecar_node_coverage_missing:{missing}")

    lineage = view.report_lineage
    if (
        lineage.decision != "approved"
        or lineage.gate4_status != "completed"
        or not lineage.report_id
        or lineage.report_revision is None
        or lineage.report_revision < 1
        or lineage.report_checksum is None
        or _SAFE_CHECKSUM_RE.fullmatch(lineage.report_checksum) is None
    ):
        raise ValueError("startup_trace_sidecar_lineage_invalid")

    langsmith = view.langsmith_health
    if (
        langsmith is None
        or langsmith.provider != "langsmith"
        or langsmith.status != "disabled"
        or langsmith.error_code != "tracing_disabled"
        or langsmith.fallback_used != "local_audit"
    ):
        raise ValueError("startup_trace_sidecar_langsmith_health_invalid")

    exporter_health: StartupTraceSidecarExporterHealth | None = None
    if view.exporter_health is not None:
        exporter_health = StartupTraceSidecarExporterHealth(
            status=view.exporter_health.status,
            error_code=view.exporter_health.error_code,
            fallback_used=view.exporter_health.fallback_used,
        )

    usage = view.usage_summary
    return StartupTraceSidecar(
        schema_version=view.schema_version,
        case_id=view.case_id,
        run_id=view.run_id,
        node_rows=sorted(
            rows,
            key=lambda row: (
                row["node"],
                row["attempt"] if row["attempt"] is not None else -1,
                row["retry_count"] if row["retry_count"] is not None else -1,
                row["status"] or "",
                row["error_code"] or "",
                row["tool"] or "",
            ),
        ),
        usage_summary=StartupTraceSidecarUsage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cost_usd=str(usage.cost_usd) if usage.cost_usd is not None else None,
        ),
        report_lineage=StartupTraceSidecarLineage(
            decision=lineage.decision,
            gate4_status=lineage.gate4_status,
            report_id=lineage.report_id,
            report_revision=lineage.report_revision,
            report_checksum=lineage.report_checksum,
        ),
        exporter_health=exporter_health,
        langsmith_health=StartupTraceSidecarHealth(
            provider=langsmith.provider,
            status=langsmith.status,
            error_code=langsmith.error_code,
            fallback_used=langsmith.fallback_used,
        ),
    )


def write_startup_trace_sidecar(
    *,
    audit_spool_root: Path,
    case_id: str,
    run_id: str,
    output_path: Path,
) -> Path:
    if output_path.exists():
        raise FileExistsError("startup_trace_sidecar_output_exists")
    if not output_path.parent.is_dir():
        raise ValueError("startup_trace_sidecar_output_parent_missing")
    payload = build_startup_trace_sidecar(
        audit_spool_root=audit_spool_root,
        case_id=case_id,
        run_id=run_id,
    )
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    try:
        with output_path.open("x", encoding="utf-8", newline="\n") as output_file:
            output_file.write(f"{serialized}\n")
    except FileExistsError as exc:
        raise FileExistsError("startup_trace_sidecar_output_exists") from exc
    return output_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="startup-trace-sidecar")
    parser.add_argument("--audit-spool-root", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        write_startup_trace_sidecar(
            audit_spool_root=Path(args.audit_spool_root),
            case_id=args.case_id,
            run_id=args.run_id,
            output_path=Path(args.output),
        )
    except (FileExistsError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("startup_trace_sidecar_unexpected_error", file=sys.stderr)
        return 2
    print("startup_trace_sidecar_written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
