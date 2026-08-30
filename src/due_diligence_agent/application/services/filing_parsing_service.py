from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from uuid import NAMESPACE_URL, UUID, uuid5

from bs4 import BeautifulSoup
from bs4.element import Tag

from due_diligence_agent.domain.artifacts.models import SourceLocator
from due_diligence_agent.ports.collectors import FilingArtifact
from due_diligence_agent.ports.retrieval import CHUNK_CONFIG_VERSION


@dataclass(frozen=True)
class ParsedFilingChunk:
    chunk_id: UUID
    locator: SourceLocator
    content_hash: str
    text: str
    chunk_config_hash: str


class FilingParsingService:
    def __init__(self, *, max_tokens: int = 256, overlap_tokens: int = 32) -> None:
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        if overlap_tokens < 0 or overlap_tokens >= max_tokens:
            raise ValueError("overlap_tokens must be non-negative and smaller than max_tokens")
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.chunk_config_hash = sha256(
            f"{CHUNK_CONFIG_VERSION}:{max_tokens}:{overlap_tokens}".encode("utf-8")
        ).hexdigest()

    def parse(
        self,
        *,
        case_id: UUID,
        artifact_id: UUID,
        filing: FilingArtifact,
    ) -> tuple[ParsedFilingChunk, ...]:
        del case_id
        soup = BeautifulSoup(filing.content, "html.parser")
        body = soup.body
        if body is None:
            raise ValueError("malformed html: missing body")
        for tag in body.find_all(["script", "style", "noscript"]):
            tag.decompose()

        sections = self._extract_sections(body)
        if not sections:
            raise ValueError("malformed html: no parseable text")

        filing_hash = sha256(filing.content).hexdigest()
        chunks: list[ParsedFilingChunk] = []
        for section_ordinal, locator_value, text in sections:
            words = text.split()
            chunk_ordinal = 0
            step = self.max_tokens - self.overlap_tokens
            for start in range(0, len(words), step):
                token_slice = words[start : start + self.max_tokens]
                if not token_slice:
                    continue
                chunk_text = " ".join(token_slice)
                content_hash = sha256(chunk_text.encode("utf-8")).hexdigest()
                chunk_id = uuid5(
                    NAMESPACE_URL,
                    ":".join(
                        [
                            filing_hash,
                            self.chunk_config_hash,
                            str(section_ordinal),
                            locator_value,
                            str(chunk_ordinal),
                            content_hash,
                        ]
                    ),
                )
                chunks.append(
                    ParsedFilingChunk(
                        chunk_id=chunk_id,
                        locator=SourceLocator(
                            kind="sec_filing_section",
                            value=locator_value,
                            artifact_id=artifact_id,
                        ),
                        content_hash=content_hash,
                        text=chunk_text,
                        chunk_config_hash=self.chunk_config_hash,
                    )
                )
                chunk_ordinal += 1
                if start + self.max_tokens >= len(words):
                    break
        return tuple(chunks)

    @staticmethod
    def _extract_sections(body: Tag) -> list[tuple[int, str, str]]:
        sections: list[tuple[int, str, str]] = []
        current_heading = "document"
        current_text: list[str] = []
        ordinal = 1

        def flush() -> None:
            nonlocal ordinal, current_text
            text = _normalize_whitespace(" ".join(current_text))
            if text:
                sections.append((ordinal, f"section:{ordinal:04d}:{_slug(current_heading)}", text))
                ordinal += 1
            current_text = []

        for element in body.descendants:
            name = getattr(element, "name", None)
            if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                flush()
                current_heading = element.get_text(" ", strip=True) or "section"
                continue
            if name is not None:
                continue
            text = _normalize_whitespace(str(element))
            if text:
                current_text.append(text)
        flush()
        return sections


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "section"
