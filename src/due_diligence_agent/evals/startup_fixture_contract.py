from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from stat import S_ISREG
from typing import NoReturn, cast


MANIFEST_SCHEMA = "startup_synthetic_fixture_manifest@1"
EXPECTED_CONTRACTS_SCHEMA = "startup_synthetic_expected_contracts@1"
EXPECTED_CONTRACT_VERSION = "queue2-wave2@1"
SUPPORTED_DATASET = "startup_synthetic_v1"
REQUIRED_NETWORK_POLICY = "no_external_network"
REQUIRED_PRIVACY_POLICY = "synthetic_no_secrets_no_emails_no_local_paths"
SUPPORTED_FORMATS = frozenset({"pdf", "docx", "png", "jpeg", "csv", "xlsx", "safe_zip"})
REQUIRED_PROFILE_FIELDS = frozenset(
    {
        "problem",
        "solution",
        "customer_segment",
        "business_model",
        "traction",
        "market",
        "competition",
        "financials",
    }
)
ALLOWED_PROFILE_STATUSES = frozenset(
    {"source_fact", "insufficient_data", "contradicted", "inferred", "partial"}
)
ALLOWED_EVIDENCE_STATUSES = frozenset(
    {"supported", "gap", "conflicting", "requires_research", "partial"}
)
ALLOWED_COMPETITOR_CATEGORIES = frozenset(
    {"direct", "indirect", "potential_entrant", "substitute", "do_nothing"}
)
ALLOWED_READINESS_STATUSES = frozenset(
    {"ready_for_first_sales", "needs_validation", "not_ready"}
)
ALLOWED_MARKET_SIZING_STATUSES = frozenset(
    {"calculated", "partial", "insufficient_data"}
)
REQUIRED_REPORT_SECTIONS = frozenset(
    {"summary", "readiness", "metrics", "market_research", "risks", "next_questions", "traceability"}
)
REQUIRED_TRACE_LINEAGE = frozenset(
    {
        "input_documents",
        "profile_fields",
        "metrics",
        "readiness",
        "research_sources",
        "competitors",
        "market_sizing",
        "risks",
        "report_sections",
    }
)
CASE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def validate_startup_fixture_contract(
    fixture_root: Path,
    *,
    dataset: str,
) -> tuple[str, ...]:
    try:
        root = fixture_root.resolve()
    except (OSError, RuntimeError):
        _fail("startup_fixture_path_unsafe")
    manifest = _read_json_file(
        root / "manifest.json",
        error_code="startup_fixture_manifest_invalid",
    )
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        _fail("startup_fixture_schema_invalid")
    if manifest.get("dataset") != dataset or dataset != SUPPORTED_DATASET:
        _fail("startup_fixture_dataset_invalid")
    if (
        manifest.get("network_policy") != REQUIRED_NETWORK_POLICY
        or manifest.get("privacy_policy") != REQUIRED_PRIVACY_POLICY
    ):
        _fail("startup_fixture_policy_invalid")

    as_of = _non_empty_string(
        manifest.get("as_of"),
        error_code="startup_fixture_manifest_invalid",
    )
    active_formats = frozenset(
        _string_sequence(
            manifest.get("active_format_matrix"),
            error_code="startup_fixture_manifest_invalid",
        )
    )
    if active_formats != SUPPORTED_FORMATS:
        _fail("startup_fixture_manifest_invalid")
    max_total_bytes = _positive_int(
        manifest.get("max_total_fixture_bytes"),
        error_code="startup_fixture_total_byte_cap_invalid",
    )
    cases = _mapping(manifest.get("cases"), error_code="startup_fixture_cases_missing")
    if not cases:
        _fail("startup_fixture_cases_missing")
    case_names = tuple(sorted(cases))
    if any(CASE_NAME_RE.fullmatch(case_name) is None for case_name in case_names):
        _fail("startup_fixture_case_name_invalid")

    expected_entry = _mapping(
        manifest.get("expected_contracts"),
        error_code="startup_fixture_expected_contracts_invalid",
    )
    seen_paths: set[Path] = set()
    expected_path, total_bytes = _verify_file_entry(
        root,
        expected_entry,
        seen_paths=seen_paths,
        total_bytes=0,
        max_total_bytes=max_total_bytes,
    )
    expected_contracts = _read_json_file(
        expected_path,
        error_code="startup_fixture_expected_contracts_invalid",
    )
    _validate_expected_contracts(
        expected_contracts,
        dataset=dataset,
        case_names=case_names,
        as_of=as_of,
    )

    observed_formats: set[str] = set()
    for case_name in case_names:
        case = _mapping(cases[case_name], error_code="startup_fixture_manifest_invalid")
        case_formats = frozenset(
            _string_sequence(
                case.get("formats"),
                error_code="startup_fixture_manifest_invalid",
            )
        )
        if not case_formats or not case_formats <= active_formats:
            _fail("startup_fixture_manifest_invalid")
        observed_formats.update(case_formats)
        case_root = _case_root(root, case_name)
        files = _mapping(case.get("files"), error_code="startup_fixture_manifest_invalid")
        if not files:
            _fail("startup_fixture_manifest_invalid")
        declared_case_paths: set[Path] = set()
        for manifest_path in sorted(files):
            entry = _mapping(files[manifest_path], error_code="startup_fixture_manifest_invalid")
            path, total_bytes = _verify_file_entry(
                root,
                entry,
                seen_paths=seen_paths,
                total_bytes=total_bytes,
                max_total_bytes=max_total_bytes,
                allowed_root=case_root,
            )
            if entry.get("path") != manifest_path or entry.get("format") not in case_formats:
                _fail("startup_fixture_manifest_invalid")
            declared_case_paths.add(path)
        if _case_files(case_root) != declared_case_paths:
            _fail("startup_fixture_case_inventory_mismatch")
    if observed_formats != active_formats:
        _fail("startup_fixture_manifest_invalid")

    return case_names


def _validate_expected_contracts(
    expected_contracts: dict[str, object],
    *,
    dataset: str,
    case_names: tuple[str, ...],
    as_of: str,
) -> None:
    error_code = "startup_fixture_expected_contracts_invalid"
    if (
        expected_contracts.get("schema_version") != EXPECTED_CONTRACTS_SCHEMA
        or expected_contracts.get("dataset") != dataset
        or expected_contracts.get("contract_version") != EXPECTED_CONTRACT_VERSION
    ):
        _fail(error_code)
    expected_cases = _mapping(expected_contracts.get("cases"), error_code=error_code)
    if set(expected_cases) != set(case_names):
        _fail(error_code)
    if (
        frozenset(
            _string_sequence(expected_contracts.get("report_sections"), error_code=error_code)
        )
        != REQUIRED_REPORT_SECTIONS
    ):
        _fail(error_code)
    trace_contract = _mapping(expected_contracts.get("trace_contract"), error_code=error_code)
    if any(
        trace_contract.get(field) is not True
        for field in (
            "requires_case_run_filtering",
            "requires_report_lineage",
            "requires_sanitized_usage",
        )
    ):
        _fail(error_code)

    for case_name in case_names:
        case = _mapping(expected_cases[case_name], error_code=error_code)
        profile_fields = _mapping(case.get("profile_fields"), error_code=error_code)
        if not REQUIRED_PROFILE_FIELDS <= set(profile_fields):
            _fail(error_code)
        for field_name in REQUIRED_PROFILE_FIELDS:
            field = _mapping(profile_fields[field_name], error_code=error_code)
            if (
                field.get("status") not in ALLOWED_PROFILE_STATUSES
                or field.get("expected_evidence_status") not in ALLOWED_EVIDENCE_STATUSES
            ):
                _fail(error_code)
        competitor_categories = frozenset(
            _string_sequence(case.get("competitor_categories"), error_code=error_code)
        )
        if (
            not competitor_categories
            or not competitor_categories <= ALLOWED_COMPETITOR_CATEGORIES
        ):
            _fail(error_code)
        for list_field in (
            "expected_contradictions",
            "expected_gap_codes",
            "expected_unsupported_claims",
            "expected_metric_pack",
        ):
            _string_sequence(case.get(list_field), error_code=error_code)

        readiness = _mapping(case.get("readiness"), error_code=error_code)
        if readiness.get("status") not in ALLOWED_READINESS_STATUSES:
            _fail(error_code)
        blocking_questions = _string_sequence(
            readiness.get("blocking_questions"),
            error_code=error_code,
        )
        if len(blocking_questions) > 3:
            _fail(error_code)

        market_research = _mapping(case.get("market_research"), error_code=error_code)
        if (
            market_research.get("source_mode") != "frozen"
            or market_research.get("as_of") != as_of
            or market_research.get("market_sizing_status")
            not in ALLOWED_MARKET_SIZING_STATUSES
        ):
            _fail(error_code)
        _string_sequence(market_research.get("source_ids"), error_code=error_code)
        if (
            frozenset(
                _string_sequence(case.get("trace_to_report_lineage"), error_code=error_code)
            )
            != REQUIRED_TRACE_LINEAGE
        ):
            _fail(error_code)


def _verify_file_entry(
    root: Path,
    entry: dict[str, object],
    *,
    seen_paths: set[Path],
    total_bytes: int,
    max_total_bytes: int,
    allowed_root: Path | None = None,
) -> tuple[Path, int]:
    path = _resolve_declared_path(root, entry.get("path"))
    if allowed_root is not None:
        try:
            path.relative_to(allowed_root)
        except ValueError:
            _fail("startup_fixture_case_path_invalid")
    if path in seen_paths:
        _fail("startup_fixture_manifest_invalid")
    seen_paths.add(path)
    declared_bytes = _non_negative_int(
        entry.get("bytes"),
        error_code="startup_fixture_bytes_invalid",
    )
    try:
        file_stat = path.stat()
    except FileNotFoundError:
        _fail("startup_fixture_file_missing")
    except OSError:
        _fail("startup_fixture_file_unreadable")
    if not S_ISREG(file_stat.st_mode):
        _fail("startup_fixture_file_missing")
    if file_stat.st_size != declared_bytes:
        _fail("startup_fixture_bytes_mismatch")
    updated_total_bytes = total_bytes + file_stat.st_size
    _enforce_total_byte_cap(updated_total_bytes, max_total_bytes)

    declared_sha256 = entry.get("sha256")
    if not isinstance(declared_sha256, str) or SHA256_RE.fullmatch(declared_sha256) is None:
        _fail("startup_fixture_sha256_invalid")
    if _stream_sha256(path) != declared_sha256:
        _fail("startup_fixture_sha256_mismatch")
    return path, updated_total_bytes


def _stream_sha256(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(64 * 1024):
                digest.update(chunk)
    except OSError:
        _fail("startup_fixture_file_unreadable")
    return digest.hexdigest()


def _resolve_declared_path(root: Path, raw_path: object) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        _fail("startup_fixture_manifest_invalid")
    relative_path = Path(raw_path)
    if relative_path.is_absolute():
        _fail("startup_fixture_path_unsafe")
    try:
        resolved = (root / relative_path).resolve()
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        _fail("startup_fixture_path_unsafe")
    if resolved == root:
        _fail("startup_fixture_path_unsafe")
    return resolved


def _case_root(root: Path, case_name: str) -> Path:
    case_root = _resolve_declared_path(root, f"cases/{case_name}")
    try:
        if not case_root.is_dir():
            _fail("startup_fixture_file_missing")
    except OSError:
        _fail("startup_fixture_file_unreadable")
    return case_root


def _case_files(case_root: Path) -> set[Path]:
    try:
        return {path.resolve() for path in case_root.rglob("*") if path.is_file()}
    except (OSError, RuntimeError):
        _fail("startup_fixture_file_unreadable")


def _read_json_file(path: Path, *, error_code: str) -> dict[str, object]:
    try:
        payload = path.read_bytes()
    except OSError:
        _fail(error_code)
    return _read_json_payload(payload, error_code=error_code)


def _read_json_payload(payload: bytes, *, error_code: str) -> dict[str, object]:
    try:
        value = cast(object, json.loads(payload.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail(error_code)
    return _mapping(value, error_code=error_code)


def _mapping(value: object, *, error_code: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        _fail(error_code)
    return cast(dict[str, object], value)


def _string_sequence(value: object, *, error_code: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        _fail(error_code)
    result = cast(tuple[str, ...], tuple(value))
    if len(set(result)) != len(result):
        _fail(error_code)
    return result


def _non_empty_string(value: object, *, error_code: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(error_code)
    return value


def _positive_int(value: object, *, error_code: str) -> int:
    result = _non_negative_int(value, error_code=error_code)
    if result == 0:
        _fail(error_code)
    return result


def _non_negative_int(value: object, *, error_code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _fail(error_code)
    return value


def _enforce_total_byte_cap(total_bytes: int, max_total_bytes: int) -> None:
    if total_bytes > max_total_bytes:
        _fail("startup_fixture_total_bytes_exceeded")


def _fail(error_code: str) -> NoReturn:
    raise ValueError(error_code)
