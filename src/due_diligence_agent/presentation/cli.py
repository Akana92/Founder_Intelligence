from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

from due_diligence_agent.bootstrap.container import build_container
from due_diligence_agent.config import Settings


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "run-public":
        return _run_public(args)
    if args.command == "run-eval":
        return _run_eval(args)
    if args.command == "run-gate-c":
        return _run_gate_c(args)
    if args.command == "run-gate-d":
        return _run_gate_d(args)
    if args.command == "run-gate-e":
        return _run_gate_e(args)
    if args.command == "run-sellable-demo-freeze":
        return _run_sellable_demo_freeze(args)
    parser.print_help()
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="investment-dd")
    subparsers = parser.add_subparsers(dest="command")
    public = subparsers.add_parser("run-public", help="Run a public-company case locally")
    public.add_argument("--ticker", required=True)
    public.add_argument("--as-of", required=True)
    public.add_argument("--fixture", default=None)
    eval_parser = subparsers.add_parser("run-eval", help="Run the Stage 1A evaluation boundary")
    eval_parser.add_argument("--dataset", required=True)
    gate_c = subparsers.add_parser("run-gate-c", help="Run the offline Gate C startup baseline")
    gate_c.add_argument("--dataset", required=True)
    gate_c.add_argument("--output-dir", default=None)
    gate_d = subparsers.add_parser(
        "run-gate-d", help="Run the offline Gate D startup deep benchmark"
    )
    gate_d.add_argument("--dataset", required=True)
    gate_d.add_argument("--output-dir", default=None)
    gate_e = subparsers.add_parser(
        "run-gate-e", help="Run the offline Gate E combined compatibility benchmark"
    )
    gate_e.add_argument("--dataset", required=True)
    gate_e.add_argument("--output-dir", default=None)
    freeze = subparsers.add_parser(
        "run-sellable-demo-freeze",
        help="Build the offline Queue 5 sellable-demo freeze packet",
    )
    freeze.add_argument("--output-dir", default=None)
    for argument in (
        "--gate-b-result",
        "--gate-c-result",
        "--gate-d-first-result",
        "--gate-d-second-result",
        "--gate-e-result",
        "--browser-evidence",
        "--desktop-screenshot",
        "--sample-pdf",
        "--demo-script",
        "--capstone-map",
    ):
        freeze.add_argument(argument, required=True)
    freeze.add_argument("--mobile-screenshot", default=None)
    return parser


def _run_public(args: argparse.Namespace) -> int:
    use_fixture = args.fixture is not None
    if args.fixture not in {None, "public_us_frozen_v1"}:
        raise SystemExit(f"unsupported fixture: {args.fixture}")
    try:
        as_of = _as_of_datetime(str(args.as_of))
    except ValueError:
        print("invalid --as-of: expected YYYY-MM-DD", file=sys.stderr)
        return 2
    settings = Settings()
    container = build_container(settings, use_fixture_adapters=use_fixture)
    try:
        case = container.case_service.create_public_case(
            ticker=str(args.ticker),
            entity_name=str(args.ticker).strip().upper(),
            as_of=as_of,
        )
        state = container.public_analysis_service.start(
            ticker=case.entity_identifier,
            case_id=str(case.case_id),
            as_of=as_of.isoformat(),
        )
        print(
            json.dumps(
                {
                    "ticker": case.entity_identifier,
                    "case_id": str(case.case_id),
                    "fixture": args.fixture,
                    "offline": bool(use_fixture),
                    "state": _jsonable(state),
                },
                sort_keys=True,
                default=str,
            )
        )
    finally:
        container.close()
    return 0


def _run_eval(args: argparse.Namespace) -> int:
    from due_diligence_agent.evals.runner import run_public_eval

    result = run_public_eval(str(args.dataset))
    payload = result.to_json_dict()
    eval_result_path = result.artifact_paths.get("eval_result")
    if eval_result_path is not None:
        payload = json.loads(Path(eval_result_path).read_text(encoding="utf-8"))
    print(json.dumps(payload, sort_keys=True, default=str))
    return 0 if result.gate_b_passed else 1


def _run_gate_c(args: argparse.Namespace) -> int:
    from due_diligence_agent.evals.gate_c import run_gate_c_eval

    output_dir = Path(str(args.output_dir)) if args.output_dir is not None else None
    result = run_gate_c_eval(str(args.dataset), output_dir=output_dir)
    payload = result.to_json_dict()
    eval_result_path = result.artifact_paths.get("eval_result")
    if eval_result_path is not None:
        payload = json.loads(Path(eval_result_path).read_text(encoding="utf-8"))
    print(json.dumps(payload, sort_keys=True, default=str))
    return 0 if result.gate_c_passed else 1


def _run_gate_d(args: argparse.Namespace) -> int:
    from due_diligence_agent.evals.gate_d import run_gate_d_eval

    output_dir = _required_eval_output_dir(args.output_dir)
    if output_dir is None:
        return 2
    try:
        result = run_gate_d_eval(str(args.dataset), output_dir=output_dir)
    except ValueError as exc:
        if _print_evaluation_output_error(exc):
            return 2
        raise
    payload = _payload_from_eval_result(result)
    print(json.dumps(payload, sort_keys=True, default=str))
    return 0 if result.gate_d_passed else 1


def _run_gate_e(args: argparse.Namespace) -> int:
    from due_diligence_agent.evals.gate_e import run_gate_e_eval

    output_dir = _required_eval_output_dir(args.output_dir)
    if output_dir is None:
        return 2
    try:
        result = run_gate_e_eval(str(args.dataset), output_dir=output_dir)
    except ValueError as exc:
        if _print_evaluation_output_error(exc):
            return 2
        raise
    payload = _payload_from_eval_result(result)
    print(json.dumps(payload, sort_keys=True, default=str))
    return 0 if result.gate_e_passed else 1


def _run_sellable_demo_freeze(args: argparse.Namespace) -> int:
    from due_diligence_agent.evals.sellable_demo_freeze import (
        SellableDemoFreezeInputs,
        build_sellable_demo_freeze_packet,
    )

    output_dir = _required_eval_output_dir(args.output_dir)
    if output_dir is None:
        return 2
    inputs = SellableDemoFreezeInputs(
        output_dir=output_dir,
        gate_b_result_path=Path(str(args.gate_b_result)),
        gate_c_result_path=Path(str(args.gate_c_result)),
        gate_d_first_result_path=Path(str(args.gate_d_first_result)),
        gate_d_second_result_path=Path(str(args.gate_d_second_result)),
        gate_e_result_path=Path(str(args.gate_e_result)),
        browser_evidence_path=Path(str(args.browser_evidence)),
        desktop_screenshot_path=Path(str(args.desktop_screenshot)),
        sample_pdf_path=Path(str(args.sample_pdf)),
        demo_script_path=Path(str(args.demo_script)),
        capstone_map_path=Path(str(args.capstone_map)),
        mobile_screenshot_path=(
            Path(str(args.mobile_screenshot)) if args.mobile_screenshot is not None else None
        ),
        require_approved_report_lineage=True,
    )
    try:
        result = build_sellable_demo_freeze_packet(inputs)
    except ValueError as exc:
        if _print_evaluation_output_error(exc):
            return 2
        raise
    print(json.dumps(result.to_json_dict(), sort_keys=True, default=str))
    return 0 if result.sellable_demo_passed else 1


def _as_of_datetime(value: str) -> datetime:
    return datetime.fromisoformat(f"{value}T00:00:00+00:00").astimezone(UTC)


def _required_eval_output_dir(raw_output_dir: str | None) -> Path | None:
    from due_diligence_agent.evals.output_root import validate_evaluation_output_root

    if raw_output_dir is None:
        print("--output-dir is required", file=sys.stderr)
        return None
    output_dir = Path(raw_output_dir)
    project_root = Path(__file__).resolve().parents[3]
    if output_dir.resolve() == project_root.resolve():
        print("--output-dir must not be the repository root", file=sys.stderr)
        return None
    try:
        return validate_evaluation_output_root(output_dir)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return None


def _print_evaluation_output_error(exc: ValueError) -> bool:
    from due_diligence_agent.evals.output_root import EVALUATION_OUTPUT_ERROR_CODES

    error_code = str(exc)
    if error_code not in EVALUATION_OUTPUT_ERROR_CODES:
        return False
    print(error_code, file=sys.stderr)
    return True


def _payload_from_eval_result(result: Any) -> dict[str, object]:
    raw_payload = result.to_json_dict()
    if not isinstance(raw_payload, dict):
        raise TypeError("evaluation result payload must be a JSON object")
    payload = {str(key): value for key, value in raw_payload.items()}
    artifact_paths = payload.get("artifact_paths")
    if isinstance(artifact_paths, dict):
        eval_result_path = artifact_paths.get("eval_result")
        if eval_result_path is not None:
            persisted = json.loads(Path(str(eval_result_path)).read_text(encoding="utf-8"))
            if isinstance(persisted, dict):
                return {str(key): value for key, value in persisted.items()}
    return payload


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    return value


if __name__ == "__main__":
    raise SystemExit(main())
