from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any, get_type_hints
from uuid import UUID, uuid4
import zipfile

from PIL import Image
from pydantic import ValidationError
import pytest

from due_diligence_agent.application.services.startup_parsing_service import (
    StartupParsingService,
)
from due_diligence_agent.application.services.claim_extraction_service import ClaimExtractionService
from due_diligence_agent.adapters.documents.no_network_guard import NoNetworkViolation
from due_diligence_agent.adapters.documents.spreadsheet_parser import XLSX_MEDIA_TYPE
from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator, StoredArtifact
from due_diligence_agent.domain.common import SensitivityClass
from due_diligence_agent.domain.documents.startup import ParsedStartupArtifact
from due_diligence_agent.domain.documents.models import ParsedDocument
from due_diligence_agent.domain.documents.tabular import SpreadsheetParseResult
from due_diligence_agent.adapters.documents.image_ocr import ImageSafetyLimits


CASE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def test_parsed_startup_artifact_rejects_mismatched_kind_and_document_payload() -> None:
    document = ParsedDocument.outcome(
        artifact_id=uuid4(),
        detected_mime_type="application/pdf",
        parser_name="pdf",
        parser_version="1",
        status="parsed",
        error_code="none",
    )

    with pytest.raises(ValidationError):
        ParsedStartupArtifact(
            artifact_id=document.artifact_id,
            case_id=CASE_ID,
            kind="spreadsheet",
            status="parsed",
            parser_name="pdf",
            parser_version="1",
            detected_mime_type="application/pdf",
            document=document,
        )


def test_parsed_startup_artifact_rejects_two_payloads() -> None:
    artifact_id = uuid4()

    with pytest.raises(ValidationError):
        ParsedStartupArtifact(
            artifact_id=artifact_id,
            case_id=CASE_ID,
            kind="document",
            status="parsed",
            parser_name="mixed",
            parser_version="1",
            document=ParsedDocument.outcome(
                artifact_id=artifact_id,
                detected_mime_type="application/pdf",
                parser_name="pdf",
                parser_version="1",
                status="parsed",
                error_code="none",
            ),
            spreadsheet=SpreadsheetParseResult(artifact_id=artifact_id, status="parsed"),
        )


def test_document_payload_is_wrapped_but_remains_document_like() -> None:
    payload = b"%PDF-1.7\nfixture"
    artifact = _artifact(payload, "deck.bin", mime_type="application/octet-stream")
    store = _Store({artifact.content_hash: payload})
    service = StartupParsingService(
        artifact_store=store,
        pdf_parser=_DocumentParser("pdf", "application/pdf"),
        docx_parser=_DocumentParser(
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ocr_parser=_OcrParser("ocr", "image/png"),
        spreadsheet_parser=_SpreadsheetParser(),
    )

    parsed = service.parse(artifact, no_network=True)

    assert parsed.kind == "document"
    assert parsed.status == "parsed"
    assert parsed.document is not None
    assert parsed.spreadsheet is None
    assert parsed.pages == []
    assert parsed.text_blocks == []
    assert parsed.detected_mime_type == "application/pdf"
    assert parsed.case_id == artifact.case_id


def test_parsed_startup_artifact_requires_authoritative_case_id() -> None:
    artifact_id = uuid4()

    with pytest.raises(ValidationError):
        ParsedStartupArtifact.model_validate(
            {
                "artifact_id": artifact_id,
                "kind": "unsupported",
                "status": "unsupported",
                "parser_name": "none",
                "parser_version": "1",
                "detected_mime_type": None,
                "error_code": "unsupported_media_type",
            }
        )

    parsed = ParsedStartupArtifact.outcome(
        artifact_id=artifact_id,
        case_id=CASE_ID,
        kind="unsupported",
        detected_mime_type=None,
        parser_name="none",
        parser_version="1",
        status="unsupported",
        error_code="unsupported_media_type",
    )

    assert parsed.case_id == CASE_ID


def test_parsed_artifact_repository_port_is_coherent_with_case_owned_aggregate() -> None:
    from due_diligence_agent.ports.parsed_artifacts import ParsedStartupArtifactRepository

    assert "case_id" in ParsedStartupArtifact.model_fields
    assert get_type_hints(ParsedStartupArtifactRepository.add)["artifact"] is ParsedStartupArtifact
    assert "get" not in ParsedStartupArtifactRepository.__dict__
    assert get_type_hints(ParsedStartupArtifactRepository.get_for_case)["case_id"] is UUID
    assert get_type_hints(ParsedStartupArtifactRepository.get_for_case)["artifact_id"] is UUID
    assert get_type_hints(ParsedStartupArtifactRepository.list_for_case)["case_id"] is UUID


@pytest.mark.parametrize(
    ("payload_factory", "source", "mime_type", "expected_kind", "expected_mime"),
    [
        (lambda: b"Metric,2025\r\nARR,1000\r\n", "metrics.csv", "text/csv", "spreadsheet", "text/csv"),
        (lambda: _xlsx_like_payload(), "metrics.xlsx", XLSX_MEDIA_TYPE, "spreadsheet", XLSX_MEDIA_TYPE),
        (lambda: b"%PDF-1.7\nfixture", "deck.pdf", "application/pdf", "document", "application/pdf"),
        (
            lambda: _docx_like_payload(),
            "deck.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "document",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (lambda: _png_bytes(), "scan.png", "image/png", "document", "image/png"),
    ],
)
def test_no_network_violation_preserves_routed_startup_artifact_kind(
    payload_factory: Any,
    source: str,
    mime_type: str,
    expected_kind: str,
    expected_mime: str,
) -> None:
    payload = payload_factory()
    artifact = _artifact(payload, source, mime_type=mime_type)
    service = StartupParsingService(
        artifact_store=_Store({artifact.content_hash: payload}),
        pdf_parser=_NetworkViolatingDocumentParser("pdf"),
        docx_parser=_NetworkViolatingDocumentParser("docx"),
        ocr_parser=_NetworkViolatingOcrParser("ocr"),
        spreadsheet_parser=_NetworkViolatingSpreadsheetParser(),
    )

    parsed = service.parse(artifact, no_network=True)

    assert parsed.kind == expected_kind
    assert parsed.status == "parser_unavailable"
    assert parsed.error_code == "network_access_blocked"
    assert parsed.detected_mime_type == expected_mime
    assert parsed.document is None
    assert parsed.spreadsheet is None


@pytest.mark.parametrize(
    ("source", "mime_type", "payload_factory", "expected_mime"),
    [
        (
            "metrics.csv",
            "application/octet-stream",
            lambda: b"Metric,2025\r\nARR,1000\r\n",
            "text/csv",
        ),
        (
            "metrics.bin",
            "text/csv",
            lambda: b"Metric,2025\r\nRevenue,2500\r\n",
            "text/csv",
        ),
        (
            "metrics.xlsx",
            "application/octet-stream",
            lambda: _xlsx_like_payload(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    ],
)
def test_csv_and_xlsx_are_routed_to_injected_spreadsheet_parser(
    source: str,
    mime_type: str,
    payload_factory: Any,
    expected_mime: str,
) -> None:
    payload = payload_factory()
    artifact = _artifact(payload, source, mime_type=mime_type)
    spreadsheet_parser = _SpreadsheetParser()
    service = StartupParsingService(
        artifact_store=_Store({artifact.content_hash: payload}),
        pdf_parser=_DocumentParser("pdf", "application/pdf"),
        docx_parser=_DocumentParser(
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ocr_parser=_OcrParser("ocr", "image/png"),
        spreadsheet_parser=spreadsheet_parser,
    )

    parsed = service.parse(artifact, no_network=True)

    assert spreadsheet_parser.seen == [artifact.id]
    assert parsed.kind == "spreadsheet"
    assert parsed.status == "parsed"
    assert parsed.detected_mime_type == expected_mime
    assert parsed.spreadsheet is not None
    assert parsed.document is None


@pytest.mark.parametrize(
    ("source", "mime_type", "payload"),
    [
        ("notes.csv", "application/octet-stream", b"just one line\nand another line\n"),
        ("notes.bin", "text/csv", b"just one line\nand another line\n"),
    ],
)
def test_text_plain_or_newlines_alone_are_not_credible_csv(
    source: str,
    mime_type: str,
    payload: bytes,
) -> None:
    artifact = _artifact(payload, source, mime_type=mime_type)
    spreadsheet_parser = _SpreadsheetParser()
    service = StartupParsingService(
        artifact_store=_Store({artifact.content_hash: payload}),
        spreadsheet_parser=spreadsheet_parser,
    )

    parsed = service.parse(artifact, no_network=True)

    assert spreadsheet_parser.seen == []
    assert parsed.kind == "unsupported"
    assert parsed.status == "unsupported"
    assert parsed.error_code == "unsupported_media_type"


def test_top_level_plain_text_brief_becomes_source_backed_text_block() -> None:
    payload = b"Founder idea brief: SilkStock Planner\nKnown gaps: no MRR exists.\n"
    artifact = _artifact(payload, "brief.txt", mime_type="text/plain")
    store = _Store({artifact.content_hash: payload})
    service = StartupParsingService(artifact_store=store)

    parsed = service.parse(artifact, no_network=True)

    assert parsed.kind == "document"
    assert parsed.status == "parsed"
    assert parsed.detected_mime_type == "text/plain"
    assert parsed.parser_name == "plain-text"
    assert parsed.text_blocks[0].locator.kind == "plain_text_document"
    assert parsed.text_blocks[0].locator.value == "brief.txt"
    assert parsed.text_blocks[0].locator.artifact_id == artifact.id
    assert store.read_bytes(parsed.text_blocks[0].text_ref) == payload


def test_plain_text_archive_member_becomes_source_backed_text_block_for_claim_pipeline() -> None:
    payload = b"Traction summary\nARR 1.2m\nRunway 18 months\n"
    artifact = _artifact(payload, "data_room.zip!/summary/traction.txt", mime_type="text/plain")
    store = _Store({artifact.content_hash: payload})
    service = StartupParsingService(artifact_store=store)

    parsed = service.parse(artifact, no_network=True)

    assert parsed.kind == "document"
    assert parsed.status == "parsed"
    assert parsed.detected_mime_type == "text/plain"
    assert parsed.parser_name == "plain-text"
    assert parsed.text_blocks[0].locator.kind == "archive_text_member"
    assert parsed.text_blocks[0].locator.value == "data_room.zip!/summary/traction.txt"
    assert parsed.text_blocks[0].locator.artifact_id == artifact.id
    assert store.read_bytes(parsed.text_blocks[0].text_ref) == payload

    claims = ClaimExtractionService().extract_fixture_claims(
        case_id=artifact.case_id,
        artifact_id=artifact.id,
        text=store.read_bytes(parsed.text_blocks[0].text_ref).decode("utf-8"),
        locator=parsed.text_blocks[0].locator,
        sensitivity=artifact.sensitivity,
        period="unknown",
    )

    assert {claim.normalized_name for claim in claims} == {"arr", "runway"}


def test_canonical_founder_pdf_metric_claims_support_mrr_burn_and_kzt_million_values() -> None:
    artifact_id = uuid4()
    locator = SourceLocator(kind="pdf_text_block", value="page=9", artifact_id=artifact_id)
    text = (
        "MRR CONTRADICTION CRM 28,6 млн ₸; invoices 27,9 млн ₸.\n"
        "Валовая маржа: 74% contribution, 70% fully loaded.\n"
        "Средний net burn за последние три месяца: 22,4 млн ₸.\n"
        "Механический runway: 7,8 месяца."
    )

    claims = ClaimExtractionService().extract_fixture_claims(
        case_id=CASE_ID,
        artifact_id=artifact_id,
        text=text,
        locator=locator,
        sensitivity=SensitivityClass.CONFIDENTIAL,
        period="unknown",
    )

    by_name = {}
    for claim in claims:
        by_name.setdefault(claim.normalized_name, []).append(claim)
    assert [claim.normalized_value for claim in by_name["monthly_recurring_revenue"]] == [
        Decimal("28600000"),
        Decimal("27900000"),
    ]
    assert {claim.unit for claim in by_name["monthly_recurring_revenue"]} == {"KZT"}
    assert [claim.normalized_value for claim in by_name["gross_margin"]] == [
        Decimal("74"),
        Decimal("70"),
    ]
    assert {claim.unit for claim in by_name["gross_margin"]} == {"percent"}
    assert by_name["monthly_net_burn"][0].normalized_value == Decimal("22400000")
    assert by_name["monthly_net_burn"][0].unit == "KZT/month"
    assert by_name["runway"][0].normalized_value == Decimal("7.8")
    assert by_name["runway"][0].unit == "months"


def test_binary_archive_text_member_remains_unsupported_without_raw_leak() -> None:
    payload = b"ARR 1.2m\x00SECRET-BINARY"
    artifact = _artifact(payload, "data_room.zip!/summary/traction.txt", mime_type="text/plain")
    service = StartupParsingService(artifact_store=_Store({artifact.content_hash: payload}))

    parsed = service.parse(artifact, no_network=True)

    assert parsed.kind == "unsupported"
    assert parsed.status == "unsupported"
    assert parsed.error_code == "unsupported_media_type"
    assert "SECRET-BINARY" not in repr(parsed)
    assert "SECRET-BINARY" not in parsed.model_dump_json()


def test_macro_enabled_workbook_preserves_rejected_status() -> None:
    payload = _xlsx_like_payload()
    artifact = _artifact(
        payload,
        "model.xlsm",
        mime_type="application/vnd.ms-excel.sheet.macroEnabled.12",
    )
    service = StartupParsingService(
        artifact_store=_Store({artifact.content_hash: payload}),
        spreadsheet_parser=_SpreadsheetParser(
            result=SpreadsheetParseResult.outcome(
                artifact_id=artifact.id,
                status="rejected",
                error_code="macro_enabled_workbook_rejected",
            )
        ),
    )

    parsed = service.parse(artifact, no_network=True)

    assert parsed.kind == "spreadsheet"
    assert parsed.status == "rejected"
    assert parsed.error_code == "macro_enabled_workbook_rejected"


@pytest.mark.parametrize(
    ("payload_factory", "source", "expected_mime"),
    [
        (lambda: b"Metric,2025\r\nARR,1000\r\n", "metrics.csv", "text/csv"),
        (
            lambda: _xlsx_like_payload(),
            "metrics.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    ],
)
def test_spreadsheets_without_injected_parser_are_typed_unavailable(
    payload_factory: Any,
    source: str,
    expected_mime: str,
) -> None:
    payload = payload_factory()
    artifact = _artifact(payload, source)
    service = StartupParsingService(artifact_store=_Store({artifact.content_hash: payload}))

    parsed = service.parse(artifact, no_network=True)

    assert parsed.kind == "spreadsheet"
    assert parsed.status == "parser_unavailable"
    assert parsed.detected_mime_type == expected_mime
    assert parsed.error_code == "spreadsheet_parser_unavailable"


def test_generic_ooxml_package_is_not_misclassified_as_xlsx() -> None:
    payload = _generic_ooxml_payload()
    artifact = _artifact(
        payload,
        "slides.pptx",
        mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    spreadsheet_parser = _SpreadsheetParser()
    service = StartupParsingService(
        artifact_store=_Store({artifact.content_hash: payload}),
        spreadsheet_parser=spreadsheet_parser,
    )

    parsed = service.parse(artifact, no_network=True)

    assert spreadsheet_parser.seen == []
    assert parsed.kind == "unsupported"
    assert parsed.status == "unsupported"
    assert parsed.detected_mime_type == "application/zip"


@pytest.mark.parametrize(
    ("source", "mime_type", "expected_kind", "expected_mime"),
    [
        (
            "deck.docx",
            "application/octet-stream",
            "document",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "metrics.bin",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "spreadsheet",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (
            "model.xlsm",
            "application/octet-stream",
            "spreadsheet",
            "application/vnd.ms-excel.sheet.macroEnabled.12",
        ),
    ],
)
def test_corrupt_claimed_ooxml_is_typed_damaged(
    source: str,
    mime_type: str,
    expected_kind: str,
    expected_mime: str,
) -> None:
    payload = b"PK\x03\x04not a readable ooxml archive"
    artifact = _artifact(payload, source, mime_type=mime_type)
    spreadsheet_parser = _SpreadsheetParser()
    service = StartupParsingService(
        artifact_store=_Store({artifact.content_hash: payload}),
        spreadsheet_parser=spreadsheet_parser,
    )

    parsed = service.parse(artifact, no_network=True)

    assert spreadsheet_parser.seen == []
    assert parsed.kind == expected_kind
    assert parsed.status == "damaged"
    assert parsed.detected_mime_type == expected_mime
    assert parsed.error_code == "damaged_ooxml_archive"


@pytest.mark.parametrize(
    ("payload_factory", "expected_status", "expected_code"),
    [
        (
            lambda: b"not a supported startup upload SECRET-RAW-CONTENT",
            "unsupported",
            "unsupported_media_type",
        ),
        (lambda: _damaged_docx_payload(), "damaged", "damaged_docx"),
    ],
)
def test_damaged_or_unsupported_inputs_return_typed_private_startup_artifacts(
    payload_factory: Any,
    expected_status: str,
    expected_code: str,
) -> None:
    payload = payload_factory()
    artifact = _artifact(payload, "upload.bin")
    service = StartupParsingService(artifact_store=_Store({artifact.content_hash: payload}))

    parsed = service.parse(artifact, no_network=True)

    assert parsed.kind in {"document", "unsupported"}
    assert parsed.status == expected_status
    assert parsed.error_code == expected_code
    assert "SECRET-RAW-CONTENT" not in repr(parsed)
    assert "SECRET-RAW-CONTENT" not in parsed.model_dump_json()


@pytest.mark.parametrize(
    ("payload_factory", "source", "mime_type", "expected_mime"),
    [
        (lambda: b"%PDF-1.7\nfixture", "misleading.csv", "text/csv", "application/pdf"),
        (
            lambda: _damaged_docx_payload(),
            "misleading.csv",
            "text/csv",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (lambda: _png_bytes(), "scan.csv", "text/csv", "image/png"),
        (lambda: _jpeg_bytes(), "scan.csv", "text/csv", "image/jpeg"),
    ],
)
def test_binary_document_and_image_signatures_win_over_spreadsheet_hints(
    payload_factory: Any,
    source: str,
    mime_type: str,
    expected_mime: str,
) -> None:
    payload = payload_factory()
    artifact = _artifact(payload, source, mime_type=mime_type)
    spreadsheet_parser = _SpreadsheetParser()
    service = StartupParsingService(
        artifact_store=_Store({artifact.content_hash: payload}),
        pdf_parser=_DocumentParser("pdf", "application/pdf"),
        docx_parser=_DocumentParser(
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ocr_parser=_OcrParser(
            "ocr",
            expected_mime if expected_mime.startswith("image/") else "image/png",
        ),
        spreadsheet_parser=spreadsheet_parser,
    )

    parsed = service.parse(artifact, no_network=True)

    assert spreadsheet_parser.seen == []
    assert parsed.kind == "document"
    assert parsed.detected_mime_type == expected_mime


class _Store:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self._payloads = payloads

    def put_bytes(
        self,
        payload: bytes,
        *,
        media_type: str,
        artifact_id: UUID | None = None,
        source_snapshot_hash: str | None = None,
        sensitivity: SensitivityClass = SensitivityClass.RESTRICTED,
    ) -> StoredArtifact:
        digest = __import__("hashlib").sha256(payload).hexdigest()
        self._payloads[digest] = payload
        return StoredArtifact(
            artifact_id=artifact_id or uuid4(),
            content_hash=digest,
            source_snapshot_hash=source_snapshot_hash or digest,
            storage_ref=digest,
            media_type=media_type,
            byte_size=len(payload),
            stored_at=datetime.now(UTC),
            sensitivity=sensitivity,
        )

    def read_bytes(self, content_hash: str) -> bytes:
        return self._payloads[content_hash]


class _DocumentParser:
    parser_name: str
    parser_version = "1"

    def __init__(self, parser_name: str, detected_mime_type: str) -> None:
        self.parser_name = parser_name
        self._detected_mime_type = detected_mime_type

    def bind(self, _artifact_store: object) -> _DocumentParser:
        return self

    def parse(self, artifact: Artifact, payload: bytes) -> ParsedDocument:
        del payload
        return ParsedDocument(
            artifact_id=artifact.id,
            detected_mime_type=self._detected_mime_type,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            confidence=Decimal("1"),
            status="parsed",
        )


class _OcrParser:
    parser_name: str
    parser_version = "1"
    image_limits = ImageSafetyLimits()

    def __init__(self, parser_name: str, detected_mime_type: str) -> None:
        self.parser_name = parser_name
        self._detected_mime_type = detected_mime_type

    def bind(self, _artifact_store: object) -> _OcrParser:
        return self

    def parse(self, artifact: Artifact, payload: bytes, *, media_type: str) -> ParsedDocument:
        del payload
        return ParsedDocument(
            artifact_id=artifact.id,
            detected_mime_type=media_type,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            confidence=Decimal("1"),
            status="parsed",
        )


class _SpreadsheetParser:
    parser_name = "spreadsheet"
    parser_version = "1"

    def __init__(self, result: SpreadsheetParseResult | None = None) -> None:
        self._result = result
        self.seen: list[UUID] = []

    def parse(self, artifact: Artifact, *, no_network: bool = True) -> SpreadsheetParseResult:
        del no_network
        self.seen.append(artifact.id)
        return self._result or SpreadsheetParseResult(artifact_id=artifact.id, status="parsed")


class _NetworkViolatingDocumentParser:
    parser_version = "1"

    def __init__(self, parser_name: str) -> None:
        self.parser_name = parser_name

    def parse(self, artifact: Artifact, payload: bytes) -> ParsedDocument:
        del artifact, payload
        raise NoNetworkViolation("network access blocked: model_hub")


class _NetworkViolatingOcrParser:
    parser_version = "1"
    image_limits = ImageSafetyLimits()

    def __init__(self, parser_name: str) -> None:
        self.parser_name = parser_name

    def bind(self, _artifact_store: object) -> _NetworkViolatingOcrParser:
        return self

    def parse(self, artifact: Artifact, payload: bytes, *, media_type: str) -> ParsedDocument:
        del artifact, payload, media_type
        raise NoNetworkViolation("network access blocked: model_hub")


class _NetworkViolatingSpreadsheetParser:
    parser_name = "spreadsheet"
    parser_version = "1"

    def parse(self, artifact: Artifact, *, no_network: bool = True) -> SpreadsheetParseResult:
        del artifact, no_network
        raise NoNetworkViolation("network access blocked: model_hub")


def _artifact(payload: bytes, source: str, mime_type: str = "application/octet-stream") -> Artifact:
    digest = __import__("hashlib").sha256(payload).hexdigest()
    return Artifact(
        id=uuid4(),
        case_id=CASE_ID,
        content_hash=digest,
        mime_type=mime_type,
        source=source,
        retrieved_at=datetime.now(UTC),
        source_snapshot_hash=digest,
        sensitivity=SensitivityClass.RESTRICTED,
    )


def _xlsx_like_payload() -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("xl/workbook.xml", b"<workbook/>")
    return output.getvalue()


def _docx_like_payload() -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("word/document.xml", b"<document/>")
    return output.getvalue()


def _damaged_docx_payload() -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", b"not valid office xml")
    return output.getvalue()


def _generic_ooxml_payload() -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("ppt/presentation.xml", b"<presentation/>")
    return output.getvalue()


def _png_bytes() -> bytes:
    image = Image.new("RGB", (4, 4))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (4, 4))
    output = BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()
