from __future__ import annotations

from pathlib import Path


OUTPUT_DIR_NOT_DIRECTORY = "evaluation_output_dir_not_directory"
OUTPUT_DIR_NOT_EMPTY = "evaluation_output_dir_not_empty"
OUTPUT_ROOT_RESERVATION_FILENAME = ".evaluation-output-root.reserved"
OUTPUT_ROOT_RESERVATION_CONTENT = "evaluation_output_root_reserved@1\n"
EVALUATION_OUTPUT_ERROR_CODES = frozenset(
    {
        OUTPUT_DIR_NOT_DIRECTORY,
        OUTPUT_DIR_NOT_EMPTY,
    }
)


def prepare_evaluation_output_root(output_dir: Path) -> Path:
    """Create and exclusively reserve a caller-owned evaluation output root."""

    _ensure_output_directory(output_dir)
    _validate_existing_output_root(output_dir)
    reservation_path = output_dir / OUTPUT_ROOT_RESERVATION_FILENAME
    try:
        with reservation_path.open("x", encoding="utf-8", newline="\n") as reservation:
            reservation.write(OUTPUT_ROOT_RESERVATION_CONTENT)
    except FileExistsError:
        raise ValueError(OUTPUT_DIR_NOT_EMPTY) from None
    except OSError:
        raise ValueError(OUTPUT_DIR_NOT_EMPTY) from None

    try:
        has_competing_evidence = any(
            child.name != OUTPUT_ROOT_RESERVATION_FILENAME for child in output_dir.iterdir()
        )
    except OSError:
        raise ValueError(OUTPUT_DIR_NOT_EMPTY) from None
    if has_competing_evidence:
        raise ValueError(OUTPUT_DIR_NOT_EMPTY)
    return output_dir


def validate_evaluation_output_root(output_dir: Path) -> Path:
    """Validate an output root without reserving it for execution."""

    if not output_dir.exists():
        return output_dir
    return _validate_existing_output_root(output_dir)


def _ensure_output_directory(output_dir: Path) -> None:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise ValueError(OUTPUT_DIR_NOT_DIRECTORY) from None
    if not output_dir.is_dir():
        raise ValueError(OUTPUT_DIR_NOT_DIRECTORY)


def _validate_existing_output_root(output_dir: Path) -> Path:
    if not output_dir.is_dir():
        raise ValueError(OUTPUT_DIR_NOT_DIRECTORY)
    try:
        has_existing_evidence = next(output_dir.iterdir(), None) is not None
    except OSError:
        raise ValueError(OUTPUT_DIR_NOT_EMPTY) from None
    if has_existing_evidence:
        raise ValueError(OUTPUT_DIR_NOT_EMPTY)
    return output_dir
