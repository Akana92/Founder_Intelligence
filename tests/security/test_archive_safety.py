from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
from shutil import rmtree
import struct
from uuid import uuid4
import warnings
import zipfile

import pytest

from due_diligence_agent.adapters.documents.archive_inspector import ZipArchiveInspector
from due_diligence_agent.adapters.local_storage.artifact_store import LocalArtifactStore
from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.application.services.data_room_service import DataRoomService
from due_diligence_agent.domain.artifacts.models import Artifact
from due_diligence_agent.domain.artifacts.safety import SafetyLimits


class RecordingArtifactRepository:
    def __init__(self) -> None:
        self.artifacts: list[Artifact] = []

    def add(self, artifact: Artifact) -> None:
        self.artifacts.append(artifact)

    def get(self, artifact_id):  # noqa: ANN001, ANN201
        return next(artifact for artifact in self.artifacts if artifact.id == artifact_id)


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "../escape.csv",
        "../",
        "..\\escape.csv",
        "/absolute.csv",
        "C:\\drive.csv",
        "C:/drive.csv",
        "C:drive-relative.csv",
        "\\\\server\\share\\unc.csv",
        "//server/share/unc.csv",
    ],
)
def test_zip_slip_variants_are_quarantined_without_partial_object_writes(
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    source = tmp_path / "unsafe.zip"
    _write_zip(source, [("safe.csv", b"a,b\n1,2\n"), (unsafe_name, b"x,y\n3,4\n")])
    before = source.read_bytes()
    service, store, _, _ = _service(tmp_path)

    inventory = service.ingest("case-1", [source])

    assert inventory.accepted == []
    assert len(inventory.quarantined) == 1
    assert inventory.quarantined[0].reason == "zip_slip"
    assert inventory.unpacked_bytes == 0
    assert list(store.root.rglob("objects/*/*")) == []
    assert source.read_bytes() == before
    assert not (tmp_path / "escape.csv").exists()


@pytest.mark.parametrize(
    ("member_names", "reason"),
    [
        (("safe.csv", "safe.csv"), "duplicate_archive_path"),
        (("safe.csv", "SAFE.csv"), "archive_path_case_collision"),
        (("folder/safe.csv", "folder\\safe.csv"), "duplicate_archive_path"),
    ],
)
def test_duplicate_or_case_colliding_member_paths_are_quarantined(
    tmp_path: Path,
    member_names: tuple[str, str],
    reason: str,
) -> None:
    source = tmp_path / "colliding.zip"
    _write_zip(
        source,
        [(member_names[0], b"a,b\n1,2\n"), (member_names[1], b"c,d\n3,4\n")],
    )
    service, store, _, _ = _service(tmp_path)

    inventory = service.ingest("case-1", [source])

    assert inventory.accepted == []
    assert inventory.quarantined[0].reason == reason
    assert list(store.root.rglob("objects/*/*")) == []


def test_archive_bomb_is_rejected_before_any_payload_is_persisted(tmp_path: Path) -> None:
    source = tmp_path / "bomb.zip"
    _write_zip(source, [("bomb.csv", b"A" * 20_000)], compression=zipfile.ZIP_DEFLATED)
    limits = SafetyLimits(max_decompression_ratio=2.0)
    service, store, _, _ = _service(tmp_path, limits=limits)

    inventory = service.ingest("case-1", [source])

    assert inventory.accepted == []
    assert inventory.quarantined[0].reason == "decompression_ratio_exceeded"
    assert inventory.unpacked_bytes == 0
    assert list(store.root.rglob("objects/*/*")) == []


def test_late_invalid_member_rolls_back_chunked_private_staging_without_commits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "late-invalid.zip"
    _write_zip(
        source,
        [
            ("large.pdf", b"%PDF-1.7\n" + b"A" * (2 * 1024 * 1024)),
            ("late.bin", b"\x00unsupported"),
        ],
    )
    staging_root = tmp_path / "private-staging"
    read_sizes: list[int] = []
    real_read = zipfile.ZipExtFile.read

    def bounded_read(member: zipfile.ZipExtFile, size: int = -1) -> bytes:
        read_sizes.append(size)
        return real_read(member, size)

    monkeypatch.setattr(zipfile.ZipExtFile, "read", bounded_read)
    service, store, _, _ = _service(tmp_path, staging_root=staging_root)

    inventory = service.ingest("case-1", [source])

    assert inventory.accepted == []
    assert inventory.quarantined[0].reason == "unsupported_media_type"
    assert read_sizes
    assert all(0 < size <= 1024 * 1024 for size in read_sizes)
    assert list(store.root.rglob("objects/*/*")) == []
    assert list(staging_root.iterdir()) == []


def test_valid_single_docx_with_private_staging_is_accepted_and_cleans_transaction(
) -> None:
    tmp_path = Path(".tmp-task9-staging-test") / uuid4().hex
    tmp_path.mkdir(parents=True)
    source = tmp_path / "pitch.docx"
    source.write_bytes(_office_bytes("word/document.xml"))
    staging_root = tmp_path / "private-staging"
    service, store, repository, _ = _service(tmp_path, staging_root=staging_root)

    try:
        inventory = service.ingest("case-1", [source])

        assert inventory.quarantined == []
        assert len(inventory.accepted) == 1
        assert inventory.accepted[0].source == "pitch.docx"
        assert inventory.accepted[0].mime_type == (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert len(repository.artifacts) == 1
        assert list(store.root.rglob("objects/*/*"))
        assert list(staging_root.iterdir()) == []
    finally:
        rmtree(tmp_path, ignore_errors=True)


def test_archive_depth_above_two_is_quarantined(tmp_path: Path) -> None:
    level_three = _zip_bytes([("deep.csv", b"a,b\n1,2\n")])
    level_two = _zip_bytes([("level-three.zip", level_three)])
    source = tmp_path / "level-one.zip"
    _write_zip(source, [("level-two.zip", level_two)])
    service, _, _, _ = _service(tmp_path)

    inventory = service.ingest("case-1", [source])

    assert inventory.accepted == []
    assert inventory.quarantined[0].reason == "archive_depth_exceeded"
    assert inventory.unpacked_bytes == 0


def test_archive_file_count_limit_is_enforced_before_storage(tmp_path: Path) -> None:
    source = tmp_path / "many.zip"
    _write_zip(source, [("one.csv", b"a,b\n1,2\n"), ("two.csv", b"c,d\n3,4\n")])
    service, store, _, _ = _service(tmp_path, limits=SafetyLimits(max_files=1))

    inventory = service.ingest("case-1", [source])

    assert inventory.accepted == []
    assert inventory.quarantined[0].reason == "file_count_exceeded"
    assert list(store.root.rglob("objects/*/*")) == []


@pytest.mark.parametrize("inside_archive", [False, True])
def test_individual_file_quota_is_enforced(tmp_path: Path, inside_archive: bool) -> None:
    payload = b"a,b\n123456789,2\n"
    if inside_archive:
        source = tmp_path / "large.zip"
        _write_zip(source, [("large.csv", payload)])
    else:
        source = tmp_path / "large.csv"
        source.write_bytes(payload)
    service, store, _, _ = _service(tmp_path, limits=SafetyLimits(max_file_bytes=8))

    inventory = service.ingest("case-1", [source])

    assert inventory.accepted == []
    assert inventory.quarantined[0].reason == "file_size_exceeded"
    assert list(store.root.rglob("objects/*/*")) == []


def test_cumulative_unpacked_quota_is_enforced_across_inputs(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_bytes(b"a,b\n1,2\n")
    second.write_bytes(b"c,d\n3,4\n")
    service, _, _, _ = _service(tmp_path, limits=SafetyLimits(max_unpacked_bytes=12))

    inventory = service.ingest("case-1", [first, second])

    assert [artifact.source for artifact in inventory.accepted] == ["first.csv"]
    assert inventory.unpacked_bytes == 8
    assert [item.reason for item in inventory.quarantined] == ["unpacked_size_exceeded"]


def test_file_count_limit_is_enforced_across_inputs(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_bytes(b"a,b\n1,2\n")
    second.write_bytes(b"c,d\n3,4\n")
    service, _, _, _ = _service(tmp_path, limits=SafetyLimits(max_files=1))

    inventory = service.ingest("case-1", [first, second])

    assert [artifact.source for artifact in inventory.accepted] == ["first.csv"]
    assert inventory.scanned_files == 1
    assert [item.reason for item in inventory.quarantined] == ["file_count_exceeded"]


def test_archive_quota_counts_office_container_and_its_unpacked_internals(tmp_path: Path) -> None:
    source = tmp_path / "office.zip"
    _write_zip(source, [("governance.docx", _office_bytes("word/document.xml"))])
    service, store, _, _ = _service(tmp_path, limits=SafetyLimits(max_unpacked_bytes=280))

    inventory = service.ingest("case-1", [source])

    assert inventory.accepted == []
    assert inventory.quarantined[0].reason == "unpacked_size_exceeded"
    assert list(store.root.rglob("objects/*/*")) == []


def test_safe_top_level_text_file_is_accepted(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_bytes(b"Founder idea brief\nKnown gaps: no MRR exists.\n")
    service, _, _, _ = _service(tmp_path)

    inventory = service.ingest("case-1", [source])

    assert inventory.quarantined == []
    assert len(inventory.accepted) == 1
    assert inventory.accepted[0].source == "notes.txt"
    assert inventory.accepted[0].mime_type == "text/plain"


@pytest.mark.parametrize(
    ("filename", "payload_kind", "reason"),
    [
        ("spoofed.pdf", "plain", "unsupported_media_type"),
        ("spoofed.pdf", "zip", "mime_type_mismatch"),
    ],
)
def test_unsupported_or_spoofed_media_is_quarantined(
    tmp_path: Path,
    filename: str,
    payload_kind: str,
    reason: str,
) -> None:
    source = tmp_path / filename
    payload = (
        _zip_bytes([("a.csv", b"a,b\n1,2\n")])
        if payload_kind == "zip"
        else b"plain unsupported text"
    )
    source.write_bytes(payload)
    service, _, _, _ = _service(tmp_path)

    inventory = service.ingest("case-1", [source])

    assert inventory.accepted == []
    assert inventory.quarantined[0].reason == reason


def test_damaged_zip_is_quarantined(tmp_path: Path) -> None:
    source = tmp_path / "damaged.zip"
    source.write_bytes(b"PK\x03\x04truncated")
    service, _, _, _ = _service(tmp_path)

    inventory = service.ingest("case-1", [source])

    assert inventory.accepted == []
    assert inventory.quarantined[0].reason == "damaged_archive"


def test_unsupported_zip_compression_is_quarantined_with_stable_reason(tmp_path: Path) -> None:
    source = tmp_path / "unsupported-compression.zip"
    _write_zip(source, [("data.csv", b"a,b\n1,2\n")])
    _patch_first_member_compression(source, method=99)
    service, store, _, _ = _service(tmp_path)

    try:
        inventory = service.ingest("case-1", [source])
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"ingest raised instead of quarantining: {type(exc).__name__}: {exc}")

    assert inventory.accepted == []
    assert inventory.quarantined[0].reason == "unsupported_compression"
    assert list(store.root.rglob("objects/*/*")) == []


def test_malformed_supported_compression_is_quarantined_instead_of_raising(tmp_path: Path) -> None:
    source = tmp_path / "malformed-deflate.zip"
    _write_zip(
        source,
        [("data.csv", b"name,value\n" + b"acme,42\n" * 200)],
        compression=zipfile.ZIP_DEFLATED,
    )
    _corrupt_first_member_payload(source)
    service, store, _, _ = _service(tmp_path)

    try:
        inventory = service.ingest("case-1", [source])
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"ingest raised instead of quarantining: {type(exc).__name__}: {exc}")

    assert inventory.accepted == []
    assert inventory.quarantined[0].reason == "archive_decompression_failed"
    assert list(store.root.rglob("objects/*/*")) == []


@pytest.mark.parametrize(
    ("suffix", "primary_part"),
    [(".docx", "word/document.xml"), (".xlsx", "xl/workbook.xml")],
)
def test_office_zip_containers_receive_archive_path_preflight(
    tmp_path: Path,
    suffix: str,
    primary_part: str,
) -> None:
    source = tmp_path / f"unsafe{suffix}"
    _write_zip(
        source,
        [
            ("[Content_Types].xml", b"<Types/>"),
            (primary_part, b"<document/>"),
            ("../escape.xml", b"<escape/>"),
        ],
    )
    service, store, _, _ = _service(tmp_path)

    inventory = service.ingest("case-1", [source])

    assert inventory.accepted == []
    assert inventory.quarantined[0].reason == "zip_slip"
    assert list(store.root.rglob("objects/*/*")) == []


def test_safe_mixed_archive_is_stored_with_real_mime_types_and_locators(tmp_path: Path) -> None:
    nested = _zip_bytes([("nested.csv", b"name,value\nacme,42\n")])
    source = tmp_path / "mixed.zip"
    members = [
        ("deck.pdf", b"%PDF-1.7\nsynthetic\n%%EOF"),
        ("model.csv", b"month,revenue\nJan,100\n"),
        ("logo.png", b"\x89PNG\r\n\x1a\nsynthetic"),
        ("photo.jpg", b"\xff\xd8\xff\xe0synthetic\xff\xd9"),
        ("governance.docx", _office_bytes("word/document.xml")),
        ("financials.xlsx", _office_bytes("xl/workbook.xml")),
        ("nested.zip", nested),
    ]
    _write_zip(source, members)
    original_hash = sha256(source.read_bytes()).hexdigest()
    service, store, repository, audit_root = _service(tmp_path)

    inventory = service.ingest("case-1", [source])

    assert inventory.quarantined == []
    assert len(inventory.accepted) == 7
    assert {artifact.mime_type for artifact in inventory.accepted} == {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/png",
        "image/jpeg",
    }
    assert {artifact.source for artifact in inventory.accepted} == {
        "mixed.zip!/deck.pdf",
        "mixed.zip!/model.csv",
        "mixed.zip!/logo.png",
        "mixed.zip!/photo.jpg",
        "mixed.zip!/governance.docx",
        "mixed.zip!/financials.xlsx",
        "mixed.zip!/nested.zip!/nested.csv",
    }
    assert len(repository.artifacts) == 7
    assert all(store.read_bytes(artifact.content_hash) for artifact in inventory.accepted)
    assert sha256(source.read_bytes()).hexdigest() == original_hash
    assert len(list(audit_root.rglob("*.jsonl"))) == 1


def test_real_shaped_mixed_archive_accepts_safe_utf8_text_member(tmp_path: Path) -> None:
    source = tmp_path / "transactional-data-room.zip"
    _write_zip(
        source,
        [
            (
                "summary/traction.txt",
                "Revenue grew 24% year over year.\nCustomers renew annually.\n".encode(),
            ),
            ("metrics/orders.csv", b"month,orders\n2026-01,120\n2026-02,145\n"),
        ],
    )
    service, store, repository, _ = _service(tmp_path)

    inventory = service.ingest("case-1", [source])

    assert inventory.quarantined == []
    assert {(artifact.source, artifact.mime_type) for artifact in inventory.accepted} == {
        ("transactional-data-room.zip!/summary/traction.txt", "text/plain"),
        ("transactional-data-room.zip!/metrics/orders.csv", "text/csv"),
    }
    assert len(repository.artifacts) == 2
    assert all(store.read_bytes(artifact.content_hash) for artifact in inventory.accepted)


@pytest.mark.parametrize(
    ("member_name", "payload", "reason"),
    [
        ("summary/traction.txt", b"safe prefix\x00binary tail", "unsupported_media_type"),
        ("summary/traction.txt", b"safe prefix\x01control tail", "unsupported_media_type"),
        ("summary/traction.txt", b"\xff\xfeinvalid utf-8", "unsupported_media_type"),
        ("summary/traction.txt", b"%PDF-1.7\nspoofed", "mime_type_mismatch"),
        ("summary/traction.bin", b"safe utf-8 prose", "unsupported_media_type"),
    ],
)
def test_hostile_or_mismatched_archive_text_member_quarantines_entire_transaction(
    tmp_path: Path,
    member_name: str,
    payload: bytes,
    reason: str,
) -> None:
    source = tmp_path / "hostile-text.zip"
    _write_zip(
        source,
        [
            ("metrics/orders.csv", b"month,orders\n2026-01,120\n"),
            (member_name, payload),
        ],
    )
    service, store, repository, _ = _service(tmp_path)

    inventory = service.ingest("case-1", [source])

    assert inventory.accepted == []
    assert [item.reason for item in inventory.quarantined] == [reason]
    assert repository.artifacts == []
    assert list(store.root.rglob("objects/*/*")) == []


def test_content_addressed_ingest_deduplicates_bytes_without_modifying_source(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    payload = b"name,value\nacme,42\n"
    first.write_bytes(payload)
    second.write_bytes(payload)
    service, _, _, _ = _service(tmp_path)

    inventory = service.ingest("case-1", [first, second])

    assert len(inventory.accepted) == 2
    assert inventory.accepted[0].content_hash == inventory.accepted[1].content_hash
    assert inventory.accepted[0].storage_ref == inventory.accepted[1].storage_ref
    assert first.read_bytes() == payload
    assert second.read_bytes() == payload


def test_quarantine_records_hash_reason_and_original_bytes_atomically(tmp_path: Path) -> None:
    source = tmp_path / "malware.exe"
    payload = b"MZ\x90\x00synthetic executable"
    source.write_bytes(payload)
    service, store, _, _ = _service(tmp_path)

    inventory = service.ingest("case-1", [source])

    item = inventory.quarantined[0]
    assert item.content_hash == "123c77ffe12c5a5246864cf9b2812f3f6831b33070123fc074b950ba064e169d"
    assert item.reason == "unsupported_media_type"
    assert item.source.value == str(source.resolve())
    assert item.quarantine_ref is not None
    assert Path(item.quarantine_ref).read_bytes() == payload
    assert Path(item.quarantine_ref).name == f"{item.content_hash}.quarantine"
    service_temp_name = re.compile(
        rf"\.{re.escape(item.content_hash)}\.[0-9a-f]{{32}}\.tmp"
    )
    assert [
        path
        for path in Path(item.quarantine_ref).parent.iterdir()
        if service_temp_name.fullmatch(path.name)
    ] == []
    assert list(store.root.rglob("objects/*/*")) == []


def _service(
    tmp_path: Path,
    *,
    limits: SafetyLimits | None = None,
    staging_root: Path | None = None,
) -> tuple[DataRoomService, LocalArtifactStore, RecordingArtifactRepository, Path]:
    store = LocalArtifactStore(tmp_path / "artifact-store")
    repository = RecordingArtifactRepository()
    audit_root = tmp_path / "audit"
    inspector = (
        ZipArchiveInspector(limits=limits or SafetyLimits())
        if staging_root is None
        else ZipArchiveInspector(
            limits=limits or SafetyLimits(),
            staging_root=staging_root,
        )
    )
    service = DataRoomService(
        artifact_store=store,
        artifact_repository=repository,
        archive_inspector=inspector,
        quarantine_root=tmp_path / "quarantine",
        limits=limits or SafetyLimits(),
        audit_spool=JsonlAuditSpool(audit_root),
    )
    return service, store, repository, audit_root


def _write_zip(
    path: Path,
    members: Iterable[tuple[str, bytes]],
    *,
    compression: int = zipfile.ZIP_STORED,
) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w", compression=compression) as archive:
            for name, payload in members:
                archive.writestr(name, payload)


def _zip_bytes(
    members: Iterable[tuple[str, bytes]],
    *,
    compression: int = zipfile.ZIP_STORED,
) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, payload in members:
            archive.writestr(name, payload)
    return buffer.getvalue()


def _office_bytes(primary_part: str) -> bytes:
    return _zip_bytes(
        [
            ("[Content_Types].xml", b"<Types/>"),
            (primary_part, b"<document/>"),
        ]
    )


def _patch_first_member_compression(path: Path, *, method: int) -> None:
    payload = bytearray(path.read_bytes())
    local = payload.index(b"PK\x03\x04")
    central = payload.index(b"PK\x01\x02")
    struct.pack_into("<H", payload, local + 8, method)
    struct.pack_into("<H", payload, central + 10, method)
    path.write_bytes(payload)


def _corrupt_first_member_payload(path: Path) -> None:
    payload = bytearray(path.read_bytes())
    local = payload.index(b"PK\x03\x04")
    compressed_size = struct.unpack_from("<I", payload, local + 18)[0]
    name_length = struct.unpack_from("<H", payload, local + 26)[0]
    extra_length = struct.unpack_from("<H", payload, local + 28)[0]
    data_start = local + 30 + name_length + extra_length
    for offset in range(data_start, data_start + compressed_size):
        payload[offset] = 0xFF
    path.write_bytes(payload)
