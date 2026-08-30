from __future__ import annotations

from decimal import Decimal
from io import BytesIO
import re
from typing import Any, Literal, cast

import pdfplumber
import pymupdf

from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator
from due_diligence_agent.domain.documents.models import (
    ParsedDocument,
    ParsedPage,
    ParsedTable,
    ParserStatus,
    TextBlock,
)
from due_diligence_agent.ports.repositories import ArtifactStore


class PdfDocumentParser:
    parser_name = "pymupdf+pdfplumber"
    parser_version = "1"
    media_type = "application/pdf"

    def __init__(self, artifact_store: ArtifactStore) -> None:
        self._artifact_store = artifact_store

    def parse(self, artifact: Artifact, payload: bytes) -> ParsedDocument:
        try:
            open_pdf: Any = getattr(pymupdf, "open")
            document: Any = open_pdf(stream=payload, filetype="pdf")
            pages, blocks = self._extract_pages(artifact, document)
            document.close()
            tables = self._extract_tables(artifact, payload)
        except Exception:  # parser libraries expose many format-specific errors
            return ParsedDocument.outcome(
                artifact_id=artifact.id,
                detected_mime_type=self.media_type,
                parser_name=self.parser_name,
                parser_version=self.parser_version,
                status="damaged",
                error_code="damaged_pdf",
            )
        status: ParserStatus = "parsed" if blocks or tables else "partial"
        return ParsedDocument(
            artifact_id=artifact.id,
            detected_mime_type=self.media_type,
            pages=pages,
            tables=tables,
            text_blocks=blocks,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            confidence=Decimal("1") if status == "parsed" else Decimal("0.5"),
            status=status,
            error_code=None if status == "parsed" else "no_extractable_content",
        )

    def _extract_pages(
        self,
        artifact: Artifact,
        document: Any,
    ) -> tuple[list[ParsedPage], list[TextBlock]]:
        pages: list[ParsedPage] = []
        all_blocks: list[TextBlock] = []
        for page_index, page in enumerate(cast(Any, document), start=1):
            page_blocks: list[TextBlock] = []
            for raw in page.get_text("blocks"):
                text = _normalize(str(raw[4]))
                if not text:
                    continue
                bbox = cast(
                    tuple[float, float, float, float],
                    tuple(float(value) for value in raw[:4]),
                )
                locator = SourceLocator(
                    kind="pdf_text_block",
                    value=f"page:{page_index}:bbox:{_bbox_value(bbox)}",
                    artifact_id=artifact.id,
                    page=page_index,
                )
                block = self._store_text(artifact, text, locator, Decimal("1"), "verified")
                page_blocks.append(block)
                all_blocks.append(block)
            pages.append(
                ParsedPage(
                    page_number=page_index,
                    locator=SourceLocator(
                        kind="pdf_page",
                        value=f"page:{page_index}",
                        artifact_id=artifact.id,
                        page=page_index,
                    ),
                    text_blocks=page_blocks,
                    width=Decimal(str(round(page.rect.width, 3))),
                    height=Decimal(str(round(page.rect.height, 3))),
                )
            )
        return pages, all_blocks

    def _extract_tables(self, artifact: Artifact, payload: bytes) -> list[ParsedTable]:
        tables: list[ParsedTable] = []
        with pdfplumber.open(BytesIO(payload)) as document:
            for page_index, page in enumerate(document.pages, start=1):
                for table_index, raw_table in enumerate(page.extract_tables(), start=1):
                    rows = [[_normalize(cell or "") for cell in row] for row in raw_table]
                    if not rows or not any(any(cell for cell in row) for row in rows):
                        continue
                    text = "\n".join("\t".join(row) for row in rows)
                    locator = SourceLocator(
                        kind="pdf_table",
                        value=f"page:{page_index}:table:{table_index}",
                        artifact_id=artifact.id,
                        page=page_index,
                        table=str(table_index),
                    )
                    stored = self._artifact_store.put_bytes(
                        text.encode("utf-8"),
                        media_type="text/tab-separated-values; charset=utf-8",
                        artifact_id=artifact.id,
                        source_snapshot_hash=artifact.content_hash,
                        sensitivity=artifact.sensitivity,
                    )
                    table_block = self._store_text(
                        artifact,
                        text,
                        locator,
                        Decimal("0.90"),
                        "verified",
                    )
                    tables.append(
                        ParsedTable(
                            locator=locator,
                            text_ref=stored.content_hash,
                            content_hash=stored.content_hash,
                            char_count=len(text),
                            row_count=len(rows),
                            column_count=max(len(row) for row in rows),
                            text_blocks=[table_block],
                            confidence=Decimal("0.90"),
                        )
                    )
        return tables

    def _store_text(
        self,
        artifact: Artifact,
        text: str,
        locator: SourceLocator,
        confidence: Decimal,
        verification_status: Literal["candidate", "needs_review", "verified"],
    ) -> TextBlock:
        stored = self._artifact_store.put_bytes(
            text.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            artifact_id=artifact.id,
            source_snapshot_hash=artifact.content_hash,
            sensitivity=artifact.sensitivity,
        )
        return TextBlock(
            text_ref=stored.content_hash,
            content_hash=stored.content_hash,
            char_count=len(text),
            locator=locator,
            confidence=confidence,
            verification_status=verification_status,
        )


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _bbox_value(bbox: tuple[float, float, float, float]) -> str:
    return ",".join(f"{value:.2f}" for value in bbox)
