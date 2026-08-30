from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Literal, Protocol
import csv
import zipfile

from due_diligence_agent.adapters.documents.spreadsheet_parser import (
    CSV_MEDIA_TYPES,
    XLSM_MEDIA_TYPE,
    XLSX_MEDIA_TYPE,
)
from due_diligence_agent.adapters.documents.docx_parser import DocxDocumentParser
from due_diligence_agent.adapters.documents.image_ocr import (
    ImageSafetyLimits,
    ImageValidationError,
    TesseractOcrAdapter,
    detect_image_media_type,
)
from due_diligence_agent.adapters.documents.no_network_guard import (
    NoNetworkGuard,
    NoNetworkViolation,
)
from due_diligence_agent.adapters.documents.pdf_parser import PdfDocumentParser
from due_diligence_agent.domain.artifacts.models import Artifact
from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.domain.documents.models import ParsedDocument, TextBlock
from due_diligence_agent.domain.documents.startup import ParsedStartupArtifact
from due_diligence_agent.domain.documents.tabular import SpreadsheetParseResult
from due_diligence_agent.ports.repositories import ArtifactStore

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PNG = "image/png"
JPEG = "image/jpeg"
ZIP = "application/zip"
PLAIN_TEXT = "text/plain"


class _DocumentParser(Protocol):
    parser_name: str
    parser_version: str

    def parse(self, artifact: Artifact, payload: bytes) -> ParsedDocument: ...


class _OcrParser(Protocol):
    parser_name: str
    parser_version: str

    def bind(self, artifact_store: ArtifactStore) -> _OcrParser: ...

    @property
    def image_limits(self) -> ImageSafetyLimits: ...

    def parse(self, artifact: Artifact, payload: bytes, *, media_type: str) -> ParsedDocument: ...


class _SpreadsheetParser(Protocol):
    parser_name: str
    parser_version: str

    def parse(self, artifact: Artifact, *, no_network: bool = True) -> SpreadsheetParseResult: ...


class StartupParsingService:
    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        pdf_parser: _DocumentParser | None = None,
        docx_parser: _DocumentParser | None = None,
        ocr_parser: _OcrParser | None = None,
        spreadsheet_parser: _SpreadsheetParser | None = None,
    ) -> None:
        self._artifact_store = artifact_store
        self._pdf = pdf_parser or PdfDocumentParser(artifact_store)
        self._docx = docx_parser or DocxDocumentParser(artifact_store)
        self._ocr = (ocr_parser or TesseractOcrAdapter()).bind(artifact_store)
        self._spreadsheet = spreadsheet_parser

    def parse(self, artifact: Artifact, *, no_network: bool = True) -> ParsedStartupArtifact:
        payload = self._artifact_store.read_bytes(artifact.content_hash)
        try:
            media_type = _detect_media_type(payload, artifact, self._ocr)
        except ImageValidationError as exc:
            return ParsedStartupArtifact.from_document(
                ParsedDocument.outcome(
                    artifact_id=artifact.id,
                    detected_mime_type=None,
                    parser_name="pillow",
                    parser_version="1",
                    status="damaged",
                    error_code=exc.error_code,
                ),
                case_id=artifact.case_id,
            )
        claimed_ooxml = _claimed_ooxml_media_type(artifact)
        if payload.startswith(b"PK\x03\x04") and claimed_ooxml is not None and _zip_is_corrupt(payload):
            return _damaged_ooxml_artifact(artifact, claimed_ooxml)
        if media_type == ZIP:
            if claimed_ooxml is not None:
                return _damaged_ooxml_artifact(artifact, claimed_ooxml)
            return ParsedStartupArtifact.outcome(
                artifact_id=artifact.id,
                case_id=artifact.case_id,
                kind="unsupported",
                detected_mime_type=media_type,
                parser_name="none",
                parser_version="1",
                status="unsupported",
                error_code="unsupported_media_type",
            )
        if media_type == PLAIN_TEXT:
            return _parse_plain_text_archive_member(
                artifact,
                payload,
                artifact_store=self._artifact_store,
            )
        if media_type in {XLSX_MEDIA_TYPE, XLSM_MEDIA_TYPE, "text/csv"} and self._spreadsheet is None:
            return self._spreadsheet_unavailable(artifact, media_type)
        parser = self._select_parser(media_type)
        if parser is None:
            return ParsedStartupArtifact.outcome(
                artifact_id=artifact.id,
                case_id=artifact.case_id,
                kind="unsupported",
                detected_mime_type=media_type,
                parser_name="none",
                parser_version="1",
                status="unsupported",
                error_code="unsupported_media_type",
            )
        try:
            if no_network:
                with NoNetworkGuard():
                    return self._parse_selected(parser, artifact, payload, media_type)
            return self._parse_selected(parser, artifact, payload, media_type)
        except NoNetworkViolation:
            return ParsedStartupArtifact.outcome(
                artifact_id=artifact.id,
                case_id=artifact.case_id,
                kind=_startup_kind_for_media_type(media_type),
                detected_mime_type=media_type,
                parser_name=getattr(parser, "parser_name", "unknown"),
                parser_version=getattr(parser, "parser_version", "unknown"),
                status="parser_unavailable",
                error_code="network_access_blocked",
            )

    def _select_parser(self, media_type: str | None) -> object | None:
        if media_type == PDF:
            return self._pdf
        if media_type == DOCX:
            return self._docx
        if media_type in {PNG, JPEG}:
            return self._ocr
        if media_type in {XLSX_MEDIA_TYPE, XLSM_MEDIA_TYPE, "text/csv"}:
            return self._spreadsheet
        return None

    def _spreadsheet_unavailable(
        self,
        artifact: Artifact,
        media_type: str | None,
    ) -> ParsedStartupArtifact:
        return ParsedStartupArtifact.outcome(
            artifact_id=artifact.id,
            case_id=artifact.case_id,
            kind="spreadsheet",
            detected_mime_type=media_type,
            parser_name="none",
            parser_version="1",
            status="parser_unavailable",
            error_code="spreadsheet_parser_unavailable",
        )

    def _parse_selected(
        self,
        parser: object,
        artifact: Artifact,
        payload: bytes,
        media_type: str | None,
    ) -> ParsedStartupArtifact:
        if parser is self._spreadsheet:
            if self._spreadsheet is None:
                return self._spreadsheet_unavailable(artifact, media_type)
            result = self._spreadsheet.parse(artifact, no_network=True)
            return ParsedStartupArtifact.from_spreadsheet(
                result,
                case_id=artifact.case_id,
                detected_mime_type=media_type,
                parser_name=self._spreadsheet.parser_name,
                parser_version=self._spreadsheet.parser_version,
            )
        if parser is self._ocr:
            if media_type is None:
                return ParsedStartupArtifact.outcome(
                    artifact_id=artifact.id,
                    case_id=artifact.case_id,
                    kind="unsupported",
                    detected_mime_type=None,
                    parser_name="none",
                    parser_version="1",
                    status="unsupported",
                    error_code="unsupported_media_type",
                )
            return ParsedStartupArtifact.from_document(
                self._ocr.parse(artifact, payload, media_type=media_type),
                case_id=artifact.case_id,
            )
        if parser in (self._pdf, self._docx):
            return ParsedStartupArtifact.from_document(
                parser.parse(artifact, payload),
                case_id=artifact.case_id,
            )
        raise TypeError("unsupported parser registration")


def _detect_media_type(payload: bytes, artifact: Artifact, ocr: _OcrParser) -> str | None:
    if payload.startswith(b"%PDF-"):
        return PDF
    if payload.startswith(b"PK\x03\x04"):
        return _detect_zip_media_type(payload, artifact)
    detected_image = detect_image_media_type(payload, ocr.image_limits)
    if detected_image is not None:
        return detected_image
    if _looks_like_csv(payload, artifact):
        return "text/csv"
    if _looks_like_plain_text_document(payload, artifact):
        return PLAIN_TEXT
    return None


def _detect_zip_media_type(payload: bytes, artifact: Artifact) -> str:
    if _artifact_is_macro_enabled(artifact):
        return XLSM_MEDIA_TYPE
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return ZIP
    if "word/document.xml" in names:
        return DOCX
    if "xl/workbook.xml" in names:
        return XLSX_MEDIA_TYPE
    return ZIP


def _artifact_is_macro_enabled(artifact: Artifact) -> bool:
    return (
        Path(artifact.source).suffix.casefold() == ".xlsm"
        or artifact.mime_type.casefold() == XLSM_MEDIA_TYPE.casefold()
    )


def _claimed_ooxml_media_type(artifact: Artifact) -> str | None:
    source_suffix = Path(artifact.source).suffix.casefold()
    declared_type = artifact.mime_type.casefold()
    if source_suffix == ".docx" or declared_type == DOCX.casefold():
        return DOCX
    if source_suffix == ".xlsx" or declared_type == XLSX_MEDIA_TYPE.casefold():
        return XLSX_MEDIA_TYPE
    if source_suffix == ".xlsm" or declared_type == XLSM_MEDIA_TYPE.casefold():
        return XLSM_MEDIA_TYPE
    return None


def _zip_is_corrupt(payload: bytes) -> bool:
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            archive.infolist()
    except (OSError, zipfile.BadZipFile):
        return True
    return False


def _damaged_ooxml_artifact(artifact: Artifact, media_type: str) -> ParsedStartupArtifact:
    kind: Literal["document", "spreadsheet", "unsupported"]
    kind = "document" if media_type == DOCX else "spreadsheet" if media_type in {
        XLSX_MEDIA_TYPE,
        XLSM_MEDIA_TYPE,
    } else "unsupported"
    return ParsedStartupArtifact.outcome(
        artifact_id=artifact.id,
        case_id=artifact.case_id,
        kind=kind,
        detected_mime_type=media_type,
        parser_name="zip",
        parser_version="1",
        status="damaged",
        error_code="damaged_ooxml_archive",
    )


def _startup_kind_for_media_type(media_type: str | None) -> Literal["document", "spreadsheet", "unsupported"]:
    if media_type in {XLSX_MEDIA_TYPE, XLSM_MEDIA_TYPE, "text/csv"}:
        return "spreadsheet"
    if media_type in {PDF, DOCX, PNG, JPEG, PLAIN_TEXT}:
        return "document"
    return "unsupported"


def _parse_plain_text_archive_member(
    artifact: Artifact,
    payload: bytes,
    *,
    artifact_store: ArtifactStore,
) -> ParsedStartupArtifact:
    text = _safe_plain_text(payload)
    if text is None:
        return ParsedStartupArtifact.outcome(
            artifact_id=artifact.id,
            case_id=artifact.case_id,
            kind="unsupported",
            detected_mime_type=None,
            parser_name="none",
            parser_version="1",
            status="unsupported",
            error_code="unsupported_media_type",
        )
    stored = artifact_store.put_bytes(
        text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        artifact_id=artifact.id,
        source_snapshot_hash=artifact.content_hash,
        sensitivity=artifact.sensitivity,
    )
    block = TextBlock(
        text_ref=stored.content_hash,
        content_hash=stored.content_hash,
        char_count=len(text),
        locator=SourceLocator(
            kind=(
                "archive_text_member"
                if "!/" in artifact.source
                else "plain_text_document"
            ),
            value=artifact.source,
            artifact_id=artifact.id,
        ),
        confidence=Decimal("1"),
        verification_status="verified",
    )
    return ParsedStartupArtifact.from_document(
        ParsedDocument(
            artifact_id=artifact.id,
            detected_mime_type=PLAIN_TEXT,
            text_blocks=[block],
            parser_name="plain-text",
            parser_version="1",
            confidence=Decimal("1"),
            status="parsed",
        ),
        case_id=artifact.case_id,
    )


def _looks_like_plain_text_document(payload: bytes, artifact: Artifact) -> bool:
    if Path(artifact.source).suffix.casefold() != ".txt":
        return False
    if artifact.mime_type.casefold() not in {"text/plain", "application/octet-stream"}:
        return False
    return _safe_plain_text(payload) is not None


def _safe_plain_text(payload: bytes) -> str | None:
    if not payload or b"\x00" in payload:
        return None
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    if any(ord(char) < 32 and char not in "\r\n\t" for char in text):
        return None
    if not text.strip():
        return None
    return text


def _looks_like_csv(payload: bytes, artifact: Artifact) -> bool:
    source_suffix = Path(artifact.source).suffix.casefold()
    declared_type = artifact.mime_type.casefold()
    if source_suffix != ".csv" and declared_type not in (CSV_MEDIA_TYPES - {"text/plain"}):
        return False
    try:
        sample = payload[:4096].decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            sample = payload[:4096].decode("cp1252")
        except UnicodeDecodeError:
            return False
    return _has_credible_csv_shape(sample)


def _has_credible_csv_shape(sample: str) -> bool:
    try:
        rows = [
            row
            for row in csv.reader(sample.splitlines())
            if any(cell.strip() for cell in row)
        ]
    except csv.Error:
        return False
    if len(rows) < 2:
        return False
    widths = [len(row) for row in rows]
    return max(widths, default=0) >= 2 and len(set(widths[: min(len(widths), 5)])) == 1
