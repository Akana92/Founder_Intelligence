from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    host = _resolve_host(args.host, all_interfaces=args.all_interfaces, parser=parser)
    uvicorn.run(
        "due_diligence_agent.presentation.api.app:create_app",
        factory=True,
        host=host,
        port=args.port,
        log_level=args.log_level,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local Founder API.")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address. Defaults to 127.0.0.1 for local-only demo use.",
    )
    parser.add_argument("--port", type=int, default=8000, help="Bind port. Defaults to 8000.")
    parser.add_argument(
        "--all-interfaces",
        action="store_true",
        help="Explicitly expose the API on 0.0.0.0. Use only on trusted networks.",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=("critical", "error", "warning", "info", "debug", "trace"),
        help="Uvicorn log level.",
    )
    return parser


def _resolve_host(
    host: str,
    *,
    all_interfaces: bool,
    parser: argparse.ArgumentParser,
) -> str:
    if all_interfaces:
        return "0.0.0.0"
    if host in {"0.0.0.0", "::"}:
        parser.error("all-interface binding requires --all-interfaces")
    return host


if __name__ == "__main__":
    main()
