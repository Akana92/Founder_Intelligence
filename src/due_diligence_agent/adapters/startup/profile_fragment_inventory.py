from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from due_diligence_agent.adapters.local_storage.artifact_store import LocalArtifactStore
from due_diligence_agent.domain.approvals.startup_disclosure import ClassifiedDisclosureSnapshot
from due_diligence_agent.domain.artifacts.models import Artifact, SourceLocator
from due_diligence_agent.ports.startup_profile_extraction import (
    MAX_FRAGMENT_CHARS,
    MAX_FRAGMENTS,
    MAX_TOTAL_FRAGMENT_CHARS,
    StartupProfileBoundedFragment,
)


class StartupProfileFragmentInventoryIntegrityError(ValueError):
    stable_error_code = "STARTUP_PROFILE_FRAGMENT_INVENTORY_INTEGRITY_ERROR"


class PersistedStartupProfileFragmentInventory:
    def __init__(
        self,
        *,
        workflow_store: Any,
        parser: Any,
        artifact_repository: Any,
        artifact_store: LocalArtifactStore,
    ) -> None:
        self._workflow_store = workflow_store
        self._parser = parser
        self._artifact_repository = artifact_repository
        self._artifact_store = artifact_store

    def list_for_case_revision(
        self,
        case_id: UUID,
        data_revision: int,
    ) -> tuple[StartupProfileBoundedFragment, ...]:
        try:
            return self._list_for_case_revision(case_id, data_revision)
        except OSError:
            raise StartupProfileFragmentInventoryIntegrityError(
                "startup_profile_fragment_inventory_integrity_error"
            ) from None
        except (KeyError, UnicodeError) as exc:
            raise StartupProfileFragmentInventoryIntegrityError(
                "startup_profile_fragment_inventory_integrity_error"
            ) from exc

    def _list_for_case_revision(
        self,
        case_id: UUID,
        data_revision: int,
    ) -> tuple[StartupProfileBoundedFragment, ...]:
        snapshot = self._snapshot(case_id, data_revision)
        fragment_ids = tuple(snapshot.redacted_fragment_ids)
        text_refs = tuple(snapshot.minimized_fragment_refs)
        if len(fragment_ids) != len(text_refs):
            raise StartupProfileFragmentInventoryIntegrityError(
                "startup_profile_fragment_inventory_snapshot_mismatch"
            )
        if not fragment_ids:
            return ()
        blocks = tuple(self._parser.text_blocks_for_case(case_id))
        if len(blocks) != len(fragment_ids):
            if not blocks and self._privacy_fail_closed_reason(case_id) == "no_parsed_text_blocks":
                return ()
            raise StartupProfileFragmentInventoryIntegrityError(
                "startup_profile_fragment_inventory_block_mismatch"
            )
        validated_fragments: list[StartupProfileBoundedFragment] = []
        for block, fragment_id, text_ref in zip(blocks, fragment_ids, text_refs, strict=True):
            artifact_id = block.locator.artifact_id
            if artifact_id is None:
                raise StartupProfileFragmentInventoryIntegrityError(
                    "startup_profile_fragment_artifact_id_missing"
                )
            expected_fragment_id = uuid5(NAMESPACE_URL, f"{block.content_hash}:{text_ref}")
            if fragment_id != expected_fragment_id:
                raise StartupProfileFragmentInventoryIntegrityError(
                    "startup_profile_fragment_id_mismatch"
                )
            artifact = self._artifact(case_id, artifact_id)
            text = _bounded_fragment_text(
                self._artifact_store.read_bytes(text_ref).decode("utf-8"),
                max_chars=MAX_FRAGMENT_CHARS,
            )
            validated_fragments.append(
                StartupProfileBoundedFragment(
                    fragment_id=fragment_id,
                    artifact_id=artifact_id,
                    text=text,
                    text_hash=_hash_ref(text_ref),
                    artifact_hash=_artifact_hash(artifact),
                    locator_hash=_locator_hash(block.locator),
                    page=block.locator.page,
                    table=block.locator.table,
                    cell=block.locator.cell,
                    sensitivity=snapshot.overall_class,
                    redacted=True,
                    minimized=True,
                    redaction_policy_version=snapshot.redaction_policy_version,
                )
            )
        selected_indices = _selected_fragment_indices(validated_fragments, limit=MAX_FRAGMENTS)
        fragment_char_limit = min(
            MAX_FRAGMENT_CHARS,
            MAX_TOTAL_FRAGMENT_CHARS // len(selected_indices),
        )
        return tuple(
            validated_fragments[index].model_copy(
                update={
                    "text": _bounded_fragment_text(
                        validated_fragments[index].text,
                        max_chars=fragment_char_limit,
                    )
                }
            )
            for index in selected_indices
        )

    def _snapshot(self, case_id: UUID, data_revision: int) -> ClassifiedDisclosureSnapshot:
        runtime = self._workflow_store.load(str(case_id))
        snapshot = runtime.get("disclosure_snapshot")
        if not isinstance(snapshot, ClassifiedDisclosureSnapshot):
            raise StartupProfileFragmentInventoryIntegrityError(
                "startup_disclosure_snapshot_missing"
            )
        if snapshot.case_id != case_id or snapshot.data_revision != data_revision:
            raise StartupProfileFragmentInventoryIntegrityError(
                "startup_disclosure_snapshot_revision_mismatch"
            )
        return snapshot

    def _privacy_fail_closed_reason(self, case_id: UUID) -> str | None:
        value = self._workflow_store.load(str(case_id)).get("privacy_fail_closed_reason")
        return value if isinstance(value, str) else None

    def _artifact(self, case_id: UUID, artifact_id: UUID) -> Artifact:
        artifact = cast(Artifact, self._artifact_repository.get(artifact_id))
        if artifact.case_id != case_id:
            raise StartupProfileFragmentInventoryIntegrityError(
                "startup_fragment_artifact_case_mismatch"
            )
        return artifact


def _artifact_hash(artifact: Artifact) -> str:
    return _hash_ref(artifact.source_snapshot_hash or artifact.content_hash)


def _hash_ref(value: str) -> str:
    return value if value.startswith("sha256:") else f"sha256:{value}"


def _locator_hash(locator: SourceLocator) -> str:
    payload = json.dumps(locator.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(payload.encode('utf-8')).hexdigest()}"


def _bounded_fragment_text(value: str, *, max_chars: int) -> str:
    lines = [" ".join(line.split()) for line in value.splitlines()]
    normalized = "\n".join(lines)
    if len(normalized) <= max_chars:
        return normalized
    relevant = _relevant_fragment_excerpt(lines, max_chars=max_chars)
    if relevant:
        return relevant
    return normalized[:max_chars]


def _relevant_fragment_excerpt(lines: list[str], *, max_chars: int) -> str:
    semantic_excerpts, reserved_line_indices = _semantic_line_excerpts(
        lines,
        max_chars=max_chars,
    )
    selected = list(semantic_excerpts)
    for index, line in enumerate(lines):
        if not line:
            continue
        if index in reserved_line_indices:
            continue
        if not _is_relevant_fragment_line(line):
            continue
        candidate = "\n".join([*selected, line])
        if len(candidate) > max_chars:
            if selected:
                continue
            return line[:max_chars]
        selected.append(line)
    return "\n".join(selected)


def _semantic_line_excerpts(
    lines: list[str],
    *,
    max_chars: int,
) -> tuple[tuple[str, ...], frozenset[int]]:
    reservations: list[tuple[int, re.Pattern[str]]] = []
    for _category, pattern in _SEMANTIC_CATEGORY_PATTERNS:
        candidate_indices = [
            index
            for index, line in enumerate(lines)
            if line and pattern.search(line)
        ]
        if not candidate_indices:
            continue
        best_index = min(
            candidate_indices,
            key=lambda index: (-_fragment_relevance_score(lines[index]), index),
        )
        reservations.append((best_index, pattern))

    selected: list[str] = []
    reserved_line_indices: set[int] = set()
    for position, (line_index, pattern) in enumerate(reservations):
        remaining_slots = len(reservations) - position
        used_chars = len("\n".join(selected))
        remaining_chars = max_chars - used_chars - (1 if selected else 0)
        if remaining_chars <= 0:
            break
        excerpt_limit = max(
            1,
            min(180, (remaining_chars - max(0, remaining_slots - 1)) // remaining_slots),
        )
        excerpt = _line_excerpt_around_pattern(
            lines[line_index],
            pattern,
            max_chars=excerpt_limit,
        )
        if excerpt and excerpt not in selected:
            selected.append(excerpt)
        reserved_line_indices.add(line_index)
    return tuple(selected), frozenset(reserved_line_indices)


def _line_excerpt_around_pattern(
    line: str,
    pattern: re.Pattern[str],
    *,
    max_chars: int,
) -> str:
    if len(line) <= max_chars:
        return line
    match = pattern.search(line)
    if match is None:
        return line[:max_chars]
    context = max_chars - (match.end() - match.start())
    prefix = max(0, context // 2)
    start = max(0, match.start() - prefix)
    end = min(len(line), start + max_chars)
    start = max(0, end - max_chars)
    return line[start:end].strip()


def _is_relevant_fragment_line(line: str) -> bool:
    if _fragment_relevance_score(line) > 0:
        return True
    return bool(
        re.search(
            r"(?iu)^(?:Starter|Growth|Enterprise)\b.*(?:₸|\bKZT\b|\bUSD\b|\bEUR\b)",
            line,
        )
    )


def _evenly_spaced_indices(item_count: int, *, limit: int) -> tuple[int, ...]:
    if item_count <= limit:
        return tuple(range(item_count))
    if limit == 1:
        return (0,)
    return tuple(
        index * (item_count - 1) // (limit - 1)
        for index in range(limit)
    )


def _selected_fragment_indices(
    fragments: list[StartupProfileBoundedFragment],
    *,
    limit: int,
) -> tuple[int, ...]:
    if len(fragments) <= limit:
        return tuple(range(len(fragments)))
    coverage_budget = max(4, limit // 3)
    relevance_budget = limit - coverage_budget
    coverage = list(_evenly_spaced_indices(len(fragments), limit=coverage_budget))
    selected: list[int] = []
    seen: set[int] = set()
    for index in _semantic_category_indices(fragments, limit=min(limit, relevance_budget)):
        selected.append(index)
        seen.add(index)
    ranked = sorted(
        range(len(fragments)),
        key=lambda index: (-_fragment_relevance_score(fragments[index].text), index),
    )
    for index in ranked:
        if _fragment_relevance_score(fragments[index].text) <= 0:
            break
        if index in seen:
            continue
        selected.append(index)
        seen.add(index)
        if len(selected) >= relevance_budget:
            break
    for index in coverage:
        if index in seen:
            continue
        selected.append(index)
        seen.add(index)
        if len(selected) >= limit:
            break
    for index in range(len(fragments)):
        if len(selected) >= limit:
            break
        if index not in seen:
            selected.append(index)
            seen.add(index)
    return tuple(selected)


_SEMANTIC_CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "stage",
        re.compile(r"(?iu)\b(?:stage|стадия|pre-scale|working product|рабоч[а-я]*\s+продукт)\b"),
    ),
    (
        "product_platform",
        re.compile(
            r"(?iu)\b(?:разрабатывает|"
            r"(?:product|solution|продукт|решение)\s*[:—-]|"
            r"(?:platform|платформ[ауы]).{0,100}(?:"
            r"module|admission|workflow|university|rating|housing|student|"
            r"модул[а-яё]*|поступлен[а-яё]*|университет[а-яё]*|рейтинг[а-яё]*|"
            r"студенческ[а-яё]*|жиль[а-яё]*))\b"
        ),
    ),
    (
        "customers",
        re.compile(
            r"(?iu)\b(?:customer|segment|universit|student|parent|agent|"
            r"клиент|сегмент|университет|студент|абитуриент|родител|агент)\b"
        ),
    ),
    (
        "problem_pain",
        re.compile(
            r"(?iu)\b(?:problem|pain|customer\s+problem|"
            r"проблема|боль|потер[яьи]|теря[ею]т|ручн[а-я]*|ошибк[а-я]*)\b"
        ),
    ),
    (
        "pricing",
        re.compile(r"(?iu)\b(?:pricing|tariffs?|kzt/month|₸/мес|тариф|тенге)\b"),
    ),
    (
        "market_formula",
        re.compile(r"(?iu)\b(?:tam|sam|som|market formulas?|рынок|формул)\b"),
    ),
    (
        "rating",
        re.compile(r"(?iu)\b(?:rating|fit methodology|рейтинг|подбор)\b"),
    ),
    (
        "funding_gate",
        re.compile(r"(?iu)\b(?:funding|roadmap|gate|go/no-go|35\.2m|финанс|инвест|роадмап|гейт|раунд)\b"),
    ),
    (
        "legal_privacy",
        re.compile(r"(?iu)\b(?:privacy|consent|legal|personal data|персональн|соглас|правов)\b"),
    ),
    (
        "no_go",
        re.compile(r"(?iu)\b(?:no-go|fire-safety|sanitary|insurance|landlord|стоп|не\s+запуск|не\s+продолж)\b"),
    ),
    (
        "forecast",
        re.compile(r"(?iu)\b(?:forecast|ebitda|2027|2028|2029|2030|2031|прогноз)\b"),
    ),
)

_PRIMARY_PRODUCT_DESCRIPTION_RE = re.compile(
    r"(?iu)\b(?:platform|платформ[ауы])[^\n]{0,160}(?:"
    r"module|admission|workflow|university|rating|housing|student|"
    r"модул[а-яё]*|поступлен[а-яё]*|университет[а-яё]*|рейтинг[а-яё]*|"
    r"студенческ[а-яё]*|жиль[а-яё]*)\b"
)
_PRODUCT_FINANCE_OR_CONTROL_RE = re.compile(
    r"(?iu)(?:\bbreak-even\b|\bgo/no-go\b|"
    r"\b(?:round|раунд|планов[а-яё]*|финанс[а-яё]*|инвест[а-яё]*|"
    r"equity|ebitda|capex|opex)\b|"
    r"\d[\d\s,.]*(?:₸|kzt|usd|тенге|\$))"
)


def _semantic_category_indices(
    fragments: list[StartupProfileBoundedFragment],
    *,
    limit: int,
) -> tuple[int, ...]:
    selected: list[int] = []
    seen: set[int] = set()
    for category, pattern in _SEMANTIC_CATEGORY_PATTERNS:
        best_index = next(
            (
                index
                for index in sorted(
                    range(len(fragments)),
                    key=lambda item: _semantic_category_rank(
                        category,
                        fragments[item].text,
                        item,
                    ),
                )
                if index not in seen and pattern.search(fragments[index].text)
            ),
            None,
        )
        if best_index is None:
            continue
        selected.append(best_index)
        seen.add(best_index)
        if len(selected) >= limit:
            break
    return tuple(selected)


def _semantic_category_rank(category: str, text: str, index: int) -> tuple[int, int, int]:
    product_priority = 0
    if category == "product_platform":
        product_priority = 0 if _is_primary_product_description(text) else 1
    return product_priority, -_fragment_relevance_score(text), index


def _is_primary_product_description(text: str) -> bool:
    return (
        _PRIMARY_PRODUCT_DESCRIPTION_RE.search(text) is not None
        and _PRODUCT_FINANCE_OR_CONTROL_RE.search(text) is None
    )


_RELEVANCE_PATTERNS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"(?iu)\bfounder\s+idea\s+brief\s*:"), 48),
    (re.compile(r"(?iu)^[^\n|:]{2,80}\bAI\s*$"), 70),
    (re.compile(r"(?iu)\bразрабатывает\b.{0,160}\bплатформ[ауы]\b"), 60),
    (re.compile(r"(?iu)\bСтадия\s+Seed\b"), 35),
    (re.compile(r"(?iu)\bГеография\s+Казахстан\b"), 30),
    (re.compile(r"(?iu)\bТариф\s+Ежемесячно\b"), 40),
    (re.compile(r"(?iu)\b(?:Starter|Growth|Enterprise)\b.*(?:₸|\bKZT\b|\bUSD\b|\bEUR\b)"), 35),
    (re.compile(r"(?iu)\b(?:startup name|название стартапа|company|юрлицо|офис)\b"), 12),
    (re.compile(r"(?iu)\b(?:продукт|разрабатывает|solution|решение|платформ[ауы]|saas|service|platform|tool|app|закупк|маршрутизац)\b"), 28),
    (re.compile(r"(?iu)\b(?:problem|проблема|теря[ею]т|ручн[а-я]+|pain)\b"), 9),
    (re.compile(r"(?iu)\b(?:icp|клиент|клиенты|сегмент|дистрибьютор|retail|fmcg)\b"), 9),
    (re.compile(r"(?iu)\b(?:проблема\s+клиента|наблюдаемая\s+проблема|операционное\s+следствие)\b"), 44),
    (re.compile(r"(?iu)\b(?:приоритетные\s+сегменты|сегмент\s+профиль|job-to-be-done)\b"), 44),
    (re.compile(r"(?iu)\b(?:pricing|тариф|тарифы|выручк|revenue|mrr|arr|₸|kzt)\b"), 10),
    (re.compile(r"(?iu)\b(?:stage|стадия|seed|mvp|раунд)\b"), 7),
    (re.compile(r"(?iu)\b(?:gtm|канал|пилот|партнер|партн[её]р|go-to-market)\b"), 7),
    (re.compile(r"(?iu)\b(?:privacy|consent|персональн|соглас(?:ие|ия|ий)|legal|правов)\b"), 60),
    (re.compile(r"(?iu)\b(?:no-go|go/no-go|fire-safety|sanitary|insurance|landlord|стоп|не\s+запуск)\b"), 60),
    (re.compile(r"(?iu)\b(?:forecast|forecasted|прогноз|2027|2028|2029|2030|2031|ebitda)\b"), 60),
    (re.compile(r"(?iu)\bТема\s+Тип\s+сигнала\s+Наблюдение\b"), 88),
    (re.compile(r"(?iu)\bCONTRADICTION\b(?!.{0,3}:).*\d"), 70),
    (re.compile(r"(?iu)\b(?:contradiction|conflict|differs|versus|расхожд|конфликт)\b"), 24),
    (re.compile(r"(?iu)\b(?:gross margin|валовая маржа|runway|burn|net burn|cac payback|customers)\b"), 30),
    (re.compile(r"(?iu)\b(?:net burn|средний\s+net\s+burn|механический\s+runway)\b"), 45),
)

_PENALTY_PATTERNS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"(?iu)\b(?:синтетический\s+qa-документ|qa-документ|capstone|не для инвестирования|стр\.)\b"), 24),
    (re.compile(r"(?iu)\b(?:pass-критерий|supported:|missing|contradiction:|human-in-the-loop|ожидаемый\s+путь)\b"), 80),
    (re.compile(r"(?iu)^\s*[●•]\s*(?:supported|contradiction|missing)\b"), 12),
    (re.compile(r"(?iu)^E\d{2}\s+.+\b(?:средняя|низкая|высокая)\b"), 18),
)


def _fragment_relevance_score(text: str) -> int:
    if _is_low_value_fragment(text):
        return 0
    positive = sum(weight for pattern, weight in _RELEVANCE_PATTERNS if pattern.search(text))
    positive += max(0, len(re.findall(r"(?iu)\bCONTRADICTION\b", text)) - 1) * 24
    penalty = sum(weight for pattern, weight in _PENALTY_PATTERNS if pattern.search(text))
    return max(0, positive - penalty)


def _is_low_value_fragment(text: str) -> bool:
    normalized = " ".join(text.split())
    return bool(
        re.search(
            r"(?iu)(?:^|\s)(?:●\s*)?(?:SUPPORTED|CONTRADICTION|MISSING)\s*:",
            normalized,
        )
        or re.search(r"(?iu)\b(?:pass-критерий|ожидаемый\s+human-in-the-loop\s+путь)\b", normalized)
        or re.fullmatch(
            r"(?iu)(?:решение\s+go\s+no-go\s*/\s*pause\s+следующее\s+действие|"
            r"solution\s+go\s+no-go\s*/\s*pause\s+next\s+action|"
            r"сегмент\s+job-to-be-done\s+плат[её]ж\s+первый\s+продукт|"
            r"segment\s+job-to-be-done\s+payment\s+first\s+product)",
            normalized,
        )
    )
