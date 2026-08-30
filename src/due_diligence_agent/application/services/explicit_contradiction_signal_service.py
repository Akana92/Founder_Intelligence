from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
import re
from uuid import UUID, uuid5

from due_diligence_agent.domain.common import (
    ContradictionStatus,
    FindingSeverity,
)
from due_diligence_agent.domain.evidence.models import EvidenceFact
from due_diligence_agent.domain.findings.models import Contradiction
from due_diligence_agent.ports.repositories import ContradictionRepository


_CONTRADICTION_NAMESPACE = UUID("7fbd965d-b89f-53d2-9f3d-316671b4e9ab")
_CONFLICT_TYPE = "explicit_source_conflict_signal"
_EXPLICIT_MARKER = re.compile(r"\bcontradiction\b\s*:?", re.IGNORECASE)
_NEGATED_MARKER_PREFIX = re.compile(
    r"(?:^|[\s.;,])(?:no|not\s+a)\s+contradiction\s*:?\s*$",
    re.IGNORECASE,
)
_RESOLVED_MARKER_PREFIX = re.compile(
    r"(?:^|[\s.;,])resolved\s+contradiction\s*:?\s*$",
    re.IGNORECASE,
)
_CONFLICT_CUES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bdiffers?\s+(?:from|between)\b", re.IGNORECASE),
    re.compile(r"\bconflicts?\s+with\b", re.IGNORECASE),
    re.compile(r"\bversus\b", re.IGNORECASE),
    re.compile(r"\balternates?\s+between\b", re.IGNORECASE),
)
_NUMBER_RE = re.compile(r"(?<![A-Za-zА-Яа-яЁё0-9])\d+(?:[.,]\d+)?(?![A-Za-zА-Яа-яЁё0-9])")
_SOURCE_LABEL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("crm", re.compile(r"(?iu)\bcrm\b")),
    ("invoices", re.compile(r"(?iu)\binvoices?\b|\binvoiced\b")),
    ("bank", re.compile(r"(?iu)\bbank\b")),
    ("finance", re.compile(r"(?iu)\bfinance\b|\baccounting\b")),
    ("operational", re.compile(r"(?iu)\boperational\b|\bops\b")),
    ("fully_loaded", re.compile(r"(?iu)\bfully[\s-]+loaded\b")),
    ("reported", re.compile(r"(?iu)\breported\b|\bdeclared\b|\bзаявлено\b")),
    ("recalculated", re.compile(r"(?iu)\brecalculated\b|\bпересчет\b|\bпересч[её]т\b")),
    ("actual", re.compile(r"(?iu)\bactual\b")),
    ("plan", re.compile(r"(?iu)\bplan\b|\bplanned\b")),
    ("forecast", re.compile(r"(?iu)\bforecast\b|\bforecasted\b")),
)
_GENERIC_EXPLANATION = (
    "A source document explicitly flags a contradiction or conflict signal. "
    "The raw source text remains linked through the evidence fact only."
)


@dataclass(frozen=True)
class _ExplicitSignal:
    code: str
    safe_context: str


class ExplicitContradictionSignalService:
    def __init__(
        self,
        *,
        contradiction_repository: ContradictionRepository,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._contradiction_repository = contradiction_repository
        self._clock = clock or _utc_now

    def materialize_from_text(
        self,
        *,
        case_id: UUID,
        text_fact: EvidenceFact,
        text: str,
    ) -> tuple[Contradiction, ...]:
        signals = tuple(_signals(text))
        if not signals:
            return ()

        existing_by_id = {
            item.id: item for item in self._contradiction_repository.list_for_case(case_id)
        }
        materialized: list[Contradiction] = []
        for signal in signals:
            contradiction_id = uuid5(
                _CONTRADICTION_NAMESPACE,
                "\x1f".join(
                    (
                        str(case_id),
                        str(text_fact.artifact_id),
                        signal.code,
                    )
                ),
            )
            contradiction = existing_by_id.get(contradiction_id)
            if contradiction is None:
                contradiction = Contradiction(
                    id=contradiction_id,
                    case_id=case_id,
                    conflict_type=_CONFLICT_TYPE,
                    fact_ids=(text_fact.id,),
                    finding_ids=(),
                    explanation=f"{_GENERIC_EXPLANATION} Safe context: {signal.safe_context}.",
                    severity=FindingSeverity.MEDIUM,
                    status=ContradictionStatus.OPEN,
                    recommended_resolution=(
                        "Open the linked evidence fact and reconcile the conflicting source statement."
                    ),
                    resolved_by_approval_id=None,
                    sensitivity=text_fact.sensitivity,
                    detected_at=self._clock(),
                )
                self._contradiction_repository.add(contradiction)
                existing_by_id[contradiction.id] = contradiction
            materialized.append(contradiction)
        return tuple(sorted(materialized, key=lambda item: str(item.id)))


def _signal_codes(text: str) -> Iterable[str]:
    for signal in _signals(text):
        yield signal.code


def _signals(text: str) -> Iterable[_ExplicitSignal]:
    bounded_text = text[:8_192]
    for candidate, topic in _explicit_signal_topics(bounded_text):
        safe_context = _safe_context(candidate)
        yield _ExplicitSignal(
            code=f"explicit_contradiction_with_conflict_cue:{topic}:{safe_context}",
            safe_context=safe_context,
        )


def _explicit_signal_topics(text: str) -> tuple[tuple[str, str], ...]:
    topics: list[tuple[str, str]] = []
    seen: set[str] = set()
    for candidate in _signal_candidates(text):
        if not _has_open_explicit_marker(candidate):
            continue
        if not (
            any(pattern.search(candidate) for pattern in _CONFLICT_CUES)
            or _has_competing_numeric_observations(candidate)
        ):
            continue
        topic = _safe_topic_code(candidate)
        if topic in seen:
            continue
        topics.append((candidate, topic))
        seen.add(topic)
    return tuple(topics)


def _signal_candidates(text: str) -> tuple[str, ...]:
    lines = tuple(line.strip() for line in text.splitlines() if line.strip())
    marked_lines = tuple(line for line in lines if _EXPLICIT_MARKER.search(line))
    return marked_lines or (text,)


def _has_open_explicit_marker(text: str) -> bool:
    for match in _EXPLICIT_MARKER.finditer(text):
        prefix = text[max(0, match.start() - 32) : match.end()]
        suffix = text[match.end() : match.end() + 16]
        if _NEGATED_MARKER_PREFIX.search(prefix):
            continue
        if _RESOLVED_MARKER_PREFIX.search(prefix):
            continue
        if re.match(r"(?i)\s*resolved\b", suffix):
            continue
        return True
    return False


def _has_competing_numeric_observations(text: str) -> bool:
    if len(_NUMBER_RE.findall(text)) < 2:
        return False
    segments = [segment for segment in re.split(r"[;\n|]", text) if segment.strip()]
    numeric_segments = [segment for segment in segments if _NUMBER_RE.search(segment)]
    labels = {
        label
        for segment in numeric_segments
        if (label := _observation_label(segment)) is not None
    }
    return len(labels) >= 2


def _observation_label(segment: str) -> str | None:
    number_match = _NUMBER_RE.search(segment)
    if number_match is None:
        return None
    context = segment
    marker_match = _EXPLICIT_MARKER.search(context)
    if marker_match is not None:
        context = context[marker_match.end() :]
        number_match = _NUMBER_RE.search(context)
        if number_match is None:
            return None
    window_start = max(0, number_match.start() - 48)
    window_end = min(len(context), number_match.end() + 48)
    window = context[window_start:window_end]
    for label, pattern in _SOURCE_LABEL_PATTERNS:
        if pattern.search(window):
            return label
    return None


def _safe_topic_code(text: str) -> str:
    before_marker = _EXPLICIT_MARKER.split(text, maxsplit=1)[0]
    source = before_marker.strip() or text
    normalized = source.casefold()
    normalized = re.sub(r"\d+(?:[.,]\d+)?", " ", normalized)
    normalized = re.sub(r"[^0-9a-zа-яё]+", "_", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized[:64] or "explicit"


def _safe_context(text: str) -> str:
    field = _field_key(text)
    metric = _metric_label(text)
    sources = _safe_source_labels(text)
    values = _safe_value_labels(text)
    parts = [f"field={field}", f"metric={metric}"]
    if sources:
        parts.append(f"sources={'|'.join(sources)}")
    if values:
        parts.append(f"values={'|'.join(values)}")
    return "; ".join(parts)


def _field_key(text: str) -> str:
    normalized = text.casefold()
    if any(marker in normalized for marker in ("icp", "customer segment", "client segment")):
        return "icp"
    if any(marker in normalized for marker in ("agencies", "enterprises", "enterprise")):
        return "icp"
    if any(marker in normalized for marker in ("burn", "runway", "cash")):
        return "burn_cash"
    if any(marker in normalized for marker in ("cac", "margin", "traction")):
        return "traction"
    return "revenue_pricing"


def _metric_label(text: str) -> str:
    normalized = text.casefold()
    if "mrr" in normalized:
        return "MRR"
    if "arr" in normalized:
        return "ARR"
    if "icp" in normalized or "customer segment" in normalized or "client segment" in normalized:
        return "ICP"
    if "agencies" in normalized and "enterprises" in normalized:
        return "ICP"
    if "cac" in normalized:
        return "CAC payback"
    if "margin" in normalized:
        return "gross margin"
    if "runway" in normalized:
        return "runway"
    if "customer" in normalized and "count" in normalized:
        return "customer count"
    return "metric"


def _safe_source_labels(text: str) -> tuple[str, ...]:
    labels: list[str] = []
    for label, pattern in _SOURCE_LABEL_PATTERNS:
        if pattern.search(text):
            labels.append(label)
    normalized = text.casefold()
    if "agencies" in normalized:
        labels.append("agencies")
    if "enterprises" in normalized:
        labels.append("enterprises")
    return tuple(dict.fromkeys(labels))


def _safe_value_labels(text: str) -> tuple[str, ...]:
    values: list[str] = []
    normalized = text.casefold()
    if "млн" in normalized:
        suffix = "m KZT" if "kzt" in normalized or "₸" in normalized else "m"
    else:
        suffix = " KZT" if "kzt" in normalized or "₸" in normalized else ""
    for match in _NUMBER_RE.finditer(text):
        value = match.group(0).replace(",", ".")
        if suffix and "." in value:
            value = f"{value}{suffix}"
        elif suffix:
            value = f"{value}{suffix.strip()}"
        values.append(value)
    return tuple(dict.fromkeys(values[:4]))


def _utc_now() -> datetime:
    return datetime.now(UTC)
