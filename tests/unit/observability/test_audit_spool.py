from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import threading

import pytest

from due_diligence_agent.adapters.observability import audit_spool as audit_spool_module
from due_diligence_agent.adapters.observability.audit_spool import JsonlAuditSpool
from due_diligence_agent.ports.tracing import AuditEvent


def test_jsonl_audit_spool_writes_canonical_date_partitioned_events(tmp_path) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)
    event = _event("event-1", run_id="run-1", attributes={"status": "ok", "tokens": 42})

    path = spool.append(event)

    assert path.endswith("2026/08/09/run-1.jsonl")
    payload = (tmp_path / "2026" / "08" / "09" / "run-1.jsonl").read_text(encoding="utf-8")
    assert payload == (
        '{"attributes":{"status":"ok","tokens":42},"correlation_id":"corr-1",'
        '"event_id":"event-1","event_type":"span","run_id":"run-1",'
        '"schema_version":"audit_event@1","span_name":"llm.call",'
        '"timestamp_utc":"2026-08-09T12:00:00Z"}\n'
    )


def test_audit_spool_rejects_run_id_path_traversal(tmp_path) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)

    with pytest.raises(ValueError, match="run_id.invalid"):
        spool.append(_event("event-1", run_id="../outside"))


def test_audit_spool_rejects_windows_reserved_run_ids_and_invalid_utc_dates(tmp_path) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)

    for run_id in (
        "CON",
        "prn",
        "run:1",
        "run 1",
        "run.",
        "sk-proj-secret",
        "secret-run",
        "api-key-run",
        "john@example.com",
        "Bearer-abcdef",
        "x",
    ):
        with pytest.raises(ValueError, match="run_id.invalid"):
            spool.append(_event("event-1", run_id=run_id))

    for timestamp in (
        "2026-02-30T12:00:00Z",
        "2026-08-09T12:00:00+05:00",
        "2026-08-09T12:00:00",
    ):
        with pytest.raises(ValueError, match="timestamp_utc.invalid"):
            spool.append(_event("event-1", timestamp_utc=timestamp))


def test_audit_spool_validates_whole_event_before_persisting_forbidden_payloads(tmp_path) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)

    for attributes in (
        {"source_text": "raw filing text"},
        {"payload": "secret payload"},
        {"tool.arguments": "secret tool args"},
    ):
        with pytest.raises(ValueError, match="trace_attribute"):
            spool.append(_event("event-1", attributes=attributes))

    for bad_event in (
        _event("event-1", span_name="llm.call secret prompt"),
        _event("event-1", event_type="payload"),
    ):
        with pytest.raises(ValueError, match="audit_event"):
            spool.append(bad_event)

    assert list(tmp_path.rglob("*.jsonl")) == []


def test_audit_spool_rejects_sensitive_top_level_ids_before_persisting(tmp_path) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)

    for field_name, bad_value in (
        ("event_id", "john@example.com"),
        ("event_id", "Bearer abcdef"),
        ("event_id", "secret prompt"),
        ("event_id", "free text id"),
        ("correlation_id", "john@example.com"),
        ("correlation_id", "Bearer abcdef"),
        ("correlation_id", "secret prompt"),
        ("correlation_id", "free text id"),
    ):
        event = _event("event-1")
        event = event.__class__(
            **{
                **event.__dict__,
                field_name: bad_value,
            }
        )
        with pytest.raises(ValueError, match=f"audit_event.{field_name}.invalid"):
            spool.append(event)

    assert list(tmp_path.rglob("*.jsonl")) == []


def test_audit_spool_allows_sanitized_disclosure_event_type(tmp_path) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)

    spool.append(_event("event-1", event_type="disclosure", span_name="llm.call"))

    assert [event.event_type for event in spool.read_batch(limit=10)] == ["disclosure"]


def test_audit_spool_allows_startup_disclosure_gate_events_and_flushes_by_id(tmp_path) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)
    event_types = (
        "startup_disclosure.previewed",
        "startup_disclosure.approved",
        "startup_disclosure.denied",
        "startup_disclosure.invalidated",
    )

    for index, event_type in enumerate(event_types, start=1):
        spool.append(
            _event(
                f"startup-event-{index}",
                event_type=event_type,
                span_name="startup.disclosure_gate",
                attributes={
                    "decision": event_type.rsplit(".", 1)[1],
                    "reason": "approval_scope_invalid" if event_type.endswith("invalidated") else None,
                    "data_revision": 1,
                    "content_hash": "a" * 64,
                    "overall_class": "confidential",
                    "detected_class_count": 3,
                    "artifact_count": 1,
                    "fragment_count": 1,
                    "egress_policy_version": "ai-egress@1",
                    "destination": "openai.responses",
                },
            )
        )

    assert [event.event_type for event in spool.read_batch(limit=10)] == list(event_types)

    spool.mark_flushed(["startup-event-1"])

    assert [event.event_id for event in spool.read_batch(limit=10)] == [
        "startup-event-2",
        "startup-event-3",
        "startup-event-4",
    ]


def test_audit_spool_allows_sanitized_startup_report_lineage_events(tmp_path) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)

    spool.append(
        _event(
            "startup-report-event-1",
            run_id="startup-api-case-1",
            event_type="startup_report.gate4_completed",
            span_name="report.generate",
            attributes={
                "case_id": "case-1",
                "status": "completed",
                "report_status": "canonical",
                "report_id": "snapshot-1",
                "report_revision": 3,
                "report_checksum": "a" * 64,
                "gate4_status": "completed",
                "decision": "approved",
            },
        )
    )

    [event] = spool.read_batch(limit=10)
    assert event.event_type == "startup_report.gate4_completed"
    assert event.attributes == {
        "case_id": "case-1",
        "decision": "approved",
        "gate4_status": "completed",
        "report_checksum": "a" * 64,
        "report_id": "snapshot-1",
        "report_revision": 3,
        "report_status": "canonical",
        "status": "completed",
    }


def test_audit_spool_rejects_private_startup_report_lineage_attributes(tmp_path) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)

    for attributes in (
        {"case_id": "case-1", "report_checksum": "not-a-hex-hash"},
        {"case_id": "case-1", "report_id": r"C:\private\report.json"},
        {"case_id": "case-1", "decision": "approved because prompt leaked"},
        {"case_id": "case-1", "payload": "raw report body"},
    ):
        with pytest.raises(ValueError, match="trace_attribute"):
            spool.append(
                _event(
                    "startup-report-event-1",
                    run_id="startup-api-case-1",
                    event_type="startup_report.canonical_snapshot",
                    span_name="report.generate",
                    attributes=attributes,
                )
            )

    assert list(tmp_path.rglob("*.jsonl")) == []


def test_audit_spool_rotates_and_flushes_by_event_id(tmp_path) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1 / 1024 / 1024)

    first_path = spool.append(_event("event-1", attributes={"artifact_hash": "a" * 64}))
    second_path = spool.append(_event("event-2", attributes={"artifact_hash": "b" * 64}))

    assert first_path != second_path
    assert {event.event_id for event in spool.read_batch(limit=10)} == {"event-1", "event-2"}

    spool.mark_flushed(["event-1"])

    assert [event.event_id for event in spool.read_batch(limit=10)] == ["event-2"]


def test_audit_spool_retries_partial_writes_and_fsyncs_before_success(tmp_path, monkeypatch) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)
    real_write = os.write
    write_sizes: list[int] = []
    fsync_calls = 0

    def partial_write(fd: int, data: bytes) -> int:
        if len(data) > 1:
            written = max(1, len(data) // 2)
            write_sizes.append(written)
            return real_write(fd, data[:written])
        write_sizes.append(len(data))
        return real_write(fd, data)

    def fake_fsync(fd: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1

    monkeypatch.setattr(audit_spool_module.os, "write", partial_write)
    monkeypatch.setattr(audit_spool_module.os, "fsync", fake_fsync)

    spool.append(_event("event-1", attributes={"status": "success"}))

    assert len(write_sizes) > 1
    assert fsync_calls == 1
    assert [event.event_id for event in spool.read_batch(limit=10)] == ["event-1"]


def test_audit_spool_serializes_concurrent_rotation_and_append(tmp_path) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1 / 1024 / 1024)
    start = threading.Barrier(3)

    def append_event(event_id: str, hash_char: str) -> None:
        start.wait()
        spool.append(_event(event_id, attributes={"artifact_hash": hash_char * 64}))

    threads = [
        threading.Thread(target=append_event, args=("event-1", "a")),
        threading.Thread(target=append_event, args=("event-2", "b")),
    ]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join()

    assert {event.event_id for event in spool.read_batch(limit=10)} == {"event-1", "event-2"}
    for path in tmp_path.rglob("*.jsonl"):
        assert path.stat().st_size <= spool.max_bytes or path.read_text(encoding="utf-8").count("\n") == 1


def test_audit_spool_newest_first_bounds_across_date_partitions(tmp_path) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)
    spool.append(
        _event(
            "event-current",
            run_id="run-current",
            timestamp_utc="2026-08-30T12:00:00Z",
        )
    )
    spool.append(
        _event(
            "event-old",
            run_id="run-old",
            timestamp_utc="2026-08-29T12:00:00Z",
        )
    )

    events = spool.read_bounded(
        max_events=1,
        max_files=1,
        max_bytes=1_048_576,
        max_line_chars=8192,
        newest_first=True,
    )

    assert [event.event_id for event in events] == ["event-current"]


def test_audit_spool_newest_first_skips_file_removed_during_scan(
    tmp_path,
    monkeypatch,
) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)
    stable_path = Path(
        spool.append(
            _event(
                "event-stable",
                run_id="run-stable",
                timestamp_utc="2026-08-30T12:00:00Z",
            )
        )
    )
    vanished_path = stable_path.with_name("vanished.jsonl")
    vanished_path.write_text(stable_path.read_text(encoding="utf-8"), encoding="utf-8")
    real_stat = Path.stat

    def disappearing_stat(path: Path, *args, **kwargs):
        if path.name == vanished_path.name:
            raise FileNotFoundError(path)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", disappearing_stat)

    events = spool.read_bounded(
        max_events=1,
        max_files=1,
        max_bytes=1_048_576,
        max_line_chars=8192,
        newest_first=True,
    )

    assert [event.event_id for event in events] == ["event-stable"]


def test_audit_spool_read_and_mark_flushed_share_append_lock(tmp_path, monkeypatch) -> None:
    spool = JsonlAuditSpool(tmp_path, max_mb=1)
    lock_events: list[str] = []

    class RecordingLock:
        def __enter__(self) -> None:
            lock_events.append("enter")

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
            lock_events.append("exit")

    spool._lock = RecordingLock()  # type: ignore[assignment]

    spool.read_batch(limit=10)
    spool.mark_flushed(["event-1"])

    assert lock_events == ["enter", "exit", "enter", "exit"]


def _event(
    event_id: str,
    *,
    run_id: str = "run-1",
    timestamp_utc: str | None = None,
    span_name: str = "llm.call",
    event_type: str = "span",
    attributes: dict[str, str | int | float | bool | None] | None = None,
) -> AuditEvent:
    return AuditEvent(
        schema_version="audit_event@1",
        event_id=event_id,
        timestamp_utc=timestamp_utc
        or datetime(2026, 8, 9, 12, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        run_id=run_id,
        correlation_id="corr-1",
        span_name=span_name,
        event_type=event_type,
        attributes=attributes or {},
    )
