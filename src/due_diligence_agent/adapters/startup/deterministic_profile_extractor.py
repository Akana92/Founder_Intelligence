from __future__ import annotations

import re
from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from due_diligence_agent.application.policies.data_egress import DisclosureScope
from due_diligence_agent.application.startup_advisor_recalculation import (
    is_founder_clarification_text,
    without_founder_clarification_marker,
)
from due_diligence_agent.ports.startup_profile_extraction import (
    MAX_VALUES_PER_FIELD,
    StartupProfileBoundedFragment,
    StartupProfileExtractedField,
    StartupProfileExtractionRequest,
    StartupProfileExtractionResponse,
    StartupProfileFieldName,
    StartupProfileFieldStatus,
    StartupProfileSafeRef,
)


class DeterministicStartupProfileExtractor:
    version = "deterministic-startup-profile-extractor@1"

    def extract(
        self,
        request: StartupProfileExtractionRequest,
        *,
        disclosure_scope: DisclosureScope | None = None,
    ) -> StartupProfileExtractionResponse:
        del disclosure_scope
        fields: list[StartupProfileExtractedField] = []
        extracted, gap_codes = _extract_labeled_fields(request)
        tariff_field = _extract_split_tariff_rows(request)
        if tariff_field is not None:
            pricing_field = StartupProfileFieldName.PRICING_REVENUE_MODEL
            existing_pricing = extracted.get(pricing_field)
            extracted[pricing_field] = (
                tariff_field
                if existing_pricing is None
                else _merge_profile_fields(existing_pricing, tariff_field)
            )
        metric_fields, metric_gap_codes = _extract_spreadsheet_metrics(request)
        extracted.update(metric_fields)
        gap_codes.update(metric_gap_codes)
        _extract_semantic_document_carriers(request, extracted)

        for field_name in request.allowed_field_names:
            field = extracted.get(field_name)
            if field is None:
                fields.append(
                    StartupProfileExtractedField(
                        field_name=field_name,
                        status=StartupProfileFieldStatus.INSUFFICIENT_DATA,
                        confidence=Decimal(0),
                    )
                )
            else:
                fields.append(field)
        return StartupProfileExtractionResponse(fields=tuple(fields), gap_codes=tuple(sorted(gap_codes)))


def _merge_profile_fields(
    primary: StartupProfileExtractedField,
    secondary: StartupProfileExtractedField,
) -> StartupProfileExtractedField:
    values: list[str] = []
    refs: list[StartupProfileSafeRef] = []
    for field in (primary, secondary):
        for value, ref in zip(field.normalized_values, field.refs, strict=True):
            if value in values:
                continue
            values.append(value)
            refs.append(ref)
            if len(values) >= MAX_VALUES_PER_FIELD:
                break
        if len(values) >= MAX_VALUES_PER_FIELD:
            break
    return primary.model_copy(
        update={
            "normalized_values": tuple(values),
            "refs": tuple(refs),
            "confidence": max(primary.confidence, secondary.confidence),
        }
    )


_LABELS: dict[StartupProfileFieldName, tuple[str, ...]] = {
    StartupProfileFieldName.STARTUP_NAME: (
        "Startup Name",
        "Company",
        "Founder idea brief",
        "Название стартапа",
        "Стартап",
    ),
    StartupProfileFieldName.ONE_LINE_DESCRIPTION: (
        "One Line Description",
        "Description",
        "Продукт",
        "Описание продукта",
    ),
    StartupProfileFieldName.PROBLEM: ("Problem", "Проблема", "Наблюдаемая проблема клиентов"),
    StartupProfileFieldName.SOLUTION: ("Solution", "Решение"),
    StartupProfileFieldName.ICP: (
        "ICP",
        "Ideal Customer Profile",
        "Целевая аудитория",
        "Клиент",
        "Клиенты",
        "Приоритетные сегменты",
    ),
    StartupProfileFieldName.USERS: ("Users", "Пользователи"),
    StartupProfileFieldName.BUYERS: ("Buyers", "Покупатели"),
    StartupProfileFieldName.GEOGRAPHY: ("Geography", "Market", "География запуска", "География", "Рынок"),
    StartupProfileFieldName.STAGE: ("Stage", "Стадия", "Текущая стадия"),
    StartupProfileFieldName.BUSINESS_MODEL: ("Business Model", "Бизнес-модель"),
    StartupProfileFieldName.PRICING_REVENUE_MODEL: (
        "Pricing",
        "Revenue Model",
        "Модель выручки",
        "Монетизация",
        "Ценообразование",
        "Тарифы",
    ),
    StartupProfileFieldName.CHANNELS_GTM: ("Channels", "GTM", "Каналы", "GTM-канал", "Модель выхода на рынок"),
    StartupProfileFieldName.COMPETITORS_MENTIONED: ("Competitors", "Конкуренты"),
    StartupProfileFieldName.ASSUMPTIONS: ("Assumptions", "Допущения"),
    StartupProfileFieldName.STRENGTHS: ("Strengths", "Сильные стороны"),
    StartupProfileFieldName.WEAKNESSES: ("Weaknesses", "Слабые стороны"),
    StartupProfileFieldName.METRIC_PACK_CANDIDATES: ("Metric Pack Candidates", "Market Formulas"),
}
_LABEL_BOUNDARY_PATTERN = "|".join(
    re.escape(label)
    for labels in _LABELS.values()
    for label in labels
)


_TEXT_METRIC_LABELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("MRR", ("MRR",)),
    ("ARR", ("ARR",)),
    ("Валовая маржа", ("Валовая маржа", "Gross Margin", "Gross margin")),
    ("Runway", ("Runway", "Runway months")),
    ("Burn", ("Burn", "Net Burn", "Burn rate")),
    ("CAC", ("CAC",)),
)
_INLINE_TEXT_METRIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "runway",
        re.compile(
            r"(?iu)\brunway\b[^\d\r\n]{0,40}(?P<value>\d+(?:[.,]\d+)?)\s*"
            r"(?P<unit>months?|мес\.?|месяц(?:а|ев)?)\b"
        ),
    ),
)
_PLANNING_METRIC_CONTEXT_PATTERN = re.compile(
    r"(?iu)\b(?:targets?|targeted|targeting|goals?|plans?|planned|planning|"
    r"forecasts?|forecasted|forecasting|projected|projections?|hypothesis|hypotheses|"
    r"hypothesized|hypothesizing|scenarios?|expected|expectations?|idea-only|"
    r"цел[ья][а-яё]*|план(?:а|у|ом|е|ы|ов|ам|ами|ах)?|"
    r"планов(?:ый|ая|ое|ые|ого|ой|ому|ым|ыми|ых|ую)|планируем[а-яё]*|планирован[а-яё]*|"
    r"прогноз[а-яё]*|гипотез[а-яё]*|сценар[а-яё]*|"
    r"ожида[а-яё]*)\b"
)


def _extract_labeled_fields(
    request: StartupProfileExtractionRequest,
) -> tuple[dict[StartupProfileFieldName, StartupProfileExtractedField], set[str]]:
    extracted: dict[StartupProfileFieldName, StartupProfileExtractedField] = {}
    gap_codes: set[str] = set()
    for fragment in request.fragments:
        if fragment.text.startswith("[REDACTED:"):
            continue
        is_founder_clarification = is_founder_clarification_text(fragment.text)
        text = (
            without_founder_clarification_marker(fragment.text)
            if is_founder_clarification
            else fragment.text
        )
        fragment_confidence = (
            Decimal("0.95") if is_founder_clarification else Decimal("0.85")
        )
        ref = _fragment_ref(fragment, confidence=fragment_confidence)
        for field_name, labels in _LABELS.items():
            if field_name not in request.allowed_field_names:
                continue
            existing = extracted.get(field_name)
            if (
                existing is not None
                and field_name
                not in {
                    StartupProfileFieldName.ASSUMPTIONS,
                    StartupProfileFieldName.WEAKNESSES,
                }
                and not is_founder_clarification
            ):
                continue
            labeled_values = _labeled_values(
                text,
                labels,
                allow_label_qualifier=field_name is StartupProfileFieldName.SOLUTION,
            )
            if field_name not in {
                StartupProfileFieldName.ASSUMPTIONS,
                StartupProfileFieldName.WEAKNESSES,
            }:
                labeled_values = labeled_values[:1]
            for value, gap_code in labeled_values:
                if gap_code is not None:
                    gap_codes.add(gap_code)
                if value is None:
                    continue
                existing = extracted.get(field_name)
                if existing is not None:
                    values = (
                        (value, *existing.normalized_values)
                        if is_founder_clarification
                        else (*existing.normalized_values, value)
                    )
                    refs = (
                        (ref, *existing.refs)
                        if is_founder_clarification
                        else (*existing.refs, ref)
                    )
                    unique_values: list[str] = []
                    unique_refs: list[StartupProfileSafeRef] = []
                    for candidate, candidate_ref in zip(values, refs, strict=True):
                        if candidate in unique_values:
                            continue
                        unique_values.append(candidate)
                        unique_refs.append(candidate_ref)
                        if len(unique_values) >= MAX_VALUES_PER_FIELD:
                            break
                    extracted[field_name] = existing.model_copy(
                        update={
                            "normalized_values": tuple(unique_values),
                            "refs": tuple(unique_refs),
                            "confidence": max(existing.confidence, fragment_confidence),
                        }
                    )
                    continue
                extracted[field_name] = StartupProfileExtractedField(
                    field_name=field_name,
                    normalized_values=(value,),
                    status=StartupProfileFieldStatus.SOURCE_FACT,
                    confidence=fragment_confidence,
                    refs=(ref,),
                )
        _extract_structured_rows(
            text,
            ref=ref,
            request=request,
            extracted=extracted,
            gap_codes=gap_codes,
        )
        _extract_startup_heading(
            text,
            ref=ref,
            request=request,
            extracted=extracted,
        )
        _extract_idea_stage(
            text,
            ref=ref,
            request=request,
            extracted=extracted,
        )
        _extract_prose_summary(
            text,
            ref=ref,
            request=request,
            extracted=extracted,
            gap_codes=gap_codes,
        )
        _extract_text_metrics(
            text,
            ref=ref,
            request=request,
            extracted=extracted,
            gap_codes=gap_codes,
        )
    return extracted, gap_codes


def _extract_spreadsheet_metrics(
    request: StartupProfileExtractionRequest,
) -> tuple[dict[StartupProfileFieldName, StartupProfileExtractedField], set[str]]:
    if not request.spreadsheet_facts:
        return {}, set()
    entries: list[tuple[str, StartupProfileSafeRef, str, str]] = []
    truncated = False
    for fact in request.spreadsheet_facts:
        if fact.value_type not in {"decimal", "integer"}:
            continue
        value = (
            " ".join(
                item
                for item in (
                    f"{fact.name}:",
                    fact.normalized_value,
                    fact.unit,
                    fact.period,
                )
                if item
            )
        )
        ref = (
            StartupProfileSafeRef(
                ref_type="evidence_fact",
                ref_id=fact.evidence_fact_id,
                artifact_id=fact.artifact_id,
                artifact_hash=fact.artifact_hash,
                locator_hash=fact.locator_hash,
                table=fact.table,
                cell=fact.cell,
                confidence=fact.confidence,
            )
        )
        entries.append((value, ref, fact.name, fact.normalized_value))
    if not entries:
        return {}, set()

    conflict_values, conflict_refs, conflict_source_ref_ids, conflict_gap_codes = _metric_conflicts(entries)
    status = StartupProfileFieldStatus.SOURCE_FACT
    reason_code: str | None = None
    if conflict_values:
        status = StartupProfileFieldStatus.CONTRADICTION
        reason_code = "metric_conflicts_detected"
        gap_codes = set(conflict_gap_codes)
        values = conflict_values[:MAX_VALUES_PER_FIELD]
        refs = conflict_refs
        for value, ref, _name, _normalized_value in entries:
            if len(values) >= MAX_VALUES_PER_FIELD:
                break
            if ref.ref_id in conflict_source_ref_ids:
                continue
            values.append(value)
            refs.append(ref)
    else:
        values = []
        refs = []
        for value, ref, _name, _normalized_value in entries:
            if len(values) >= MAX_VALUES_PER_FIELD:
                truncated = True
                continue
            values.append(value)
            refs.append(ref)
        gap_codes = {"deterministic_spreadsheet_metrics_truncated"} if truncated else set()

    field = StartupProfileExtractedField(
        field_name=StartupProfileFieldName.TRACTION,
        normalized_values=tuple(values),
        status=status,
        confidence=max(ref.confidence for ref in refs),
        refs=tuple(refs),
        reason_code=reason_code,
    )
    metric_field = field.model_copy(update={"field_name": StartupProfileFieldName.METRIC_PACK_CANDIDATES})
    return {
        StartupProfileFieldName.TRACTION: field,
        StartupProfileFieldName.METRIC_PACK_CANDIDATES: metric_field,
    }, gap_codes


def _first_labeled_value(
    text: str,
    labels: tuple[str, ...],
    *,
    allow_label_qualifier: bool = False,
    require_line_start: bool = False,
) -> tuple[str | None, str | None]:
    values = _labeled_values(
        text,
        labels,
        allow_label_qualifier=allow_label_qualifier,
        require_line_start=require_line_start,
    )
    return values[0] if values else (None, None)


def _labeled_values(
    text: str,
    labels: tuple[str, ...],
    *,
    allow_label_qualifier: bool = False,
    require_line_start: bool = False,
) -> list[tuple[str | None, str | None]]:
    found: list[tuple[str | None, str | None]] = []
    for label in labels:
        qualifier = r"(?:\s+[^:\r\n—-]{1,80})?" if allow_label_qualifier else ""
        prefix = "^" if require_line_start else r"(?:^|\s)"
        delimiter = r"(?:\s*[:—]\s*|\s+-\s+)"
        pattern = re.compile(
            rf"(?im){prefix}{re.escape(label)}{qualifier}{delimiter}(.+?)(?=\s+(?:{_LABEL_BOUNDARY_PATTERN}){delimiter}|$)"
        )
        for match in pattern.finditer(text):
            if _is_profile_control_table_row(match.group(0)):
                continue
            value, gap_code = _clean_value(match.group(1))
            if gap_code is not None:
                found.append((None, gap_code))
                continue
            if value:
                found.append((value, None))
    return found


def _extract_split_tariff_rows(request: StartupProfileExtractionRequest) -> StartupProfileExtractedField | None:
    if StartupProfileFieldName.PRICING_REVENUE_MODEL not in request.allowed_field_names:
        return None
    has_header = any(_is_tariff_header(fragment.text) for fragment in request.fragments)
    if not has_header:
        return None
    values: list[str] = []
    refs: list[StartupProfileSafeRef] = []
    for fragment in request.fragments:
        row = _tariff_row(fragment.text)
        if row is None:
            continue
        values.append(row)
        refs.append(_fragment_ref(fragment, confidence=Decimal("0.82")))
        if len(values) == MAX_VALUES_PER_FIELD:
            break
    if not values:
        return None
    return StartupProfileExtractedField(
        field_name=StartupProfileFieldName.PRICING_REVENUE_MODEL,
        normalized_values=tuple(values),
        status=StartupProfileFieldStatus.SOURCE_FACT,
        confidence=Decimal("0.82"),
        refs=tuple(refs),
    )


def _fragment_ref(fragment: StartupProfileBoundedFragment, *, confidence: Decimal) -> StartupProfileSafeRef:
    return StartupProfileSafeRef(
        ref_type="fragment",
        ref_id=fragment.fragment_id,
        artifact_id=fragment.artifact_id,
        artifact_hash=fragment.artifact_hash,
        locator_hash=fragment.locator_hash,
        page=getattr(fragment, "page", None),
        table=getattr(fragment, "table", None),
        cell=getattr(fragment, "cell", None),
        confidence=confidence,
    )


def _extract_structured_rows(
    text: str,
    *,
    ref: StartupProfileSafeRef,
    request: StartupProfileExtractionRequest,
    extracted: dict[StartupProfileFieldName, StartupProfileExtractedField],
    gap_codes: set[str],
) -> None:
    del gap_codes
    row_specs: tuple[tuple[StartupProfileFieldName, tuple[str, ...], tuple[str, ...]], ...] = (
        (
            StartupProfileFieldName.GEOGRAPHY,
            ("География запуска", "География"),
            ("Дата среза", "Раунд", "Стадия", "Бизнес-модель", "Формат", "Format"),
        ),
        (
            StartupProfileFieldName.STAGE,
            ("Стадия",),
            ("Дата среза", "География", "Раунд", "Бизнес-модель", "Формат", "Format"),
        ),
        (
            StartupProfileFieldName.BUSINESS_MODEL,
            ("Бизнес-модель",),
            ("Дата среза", "География", "Раунд", "Стадия", "Формат", "Format"),
        ),
    )
    for field_name, labels, sibling_keys in row_specs:
        if field_name not in request.allowed_field_names or field_name in extracted:
            continue
        value = _first_table_row_value(text, labels, sibling_keys=sibling_keys)
        if value is None:
            continue
        if field_name is StartupProfileFieldName.GEOGRAPHY:
            value = _strip_deferred_vertical_from_geography(value)
            if not value:
                continue
        extracted[field_name] = StartupProfileExtractedField(
            field_name=field_name,
            normalized_values=(value,),
            status=StartupProfileFieldStatus.SOURCE_FACT,
            confidence=Decimal("0.8"),
            refs=(ref.model_copy(update={"confidence": Decimal("0.8")}),),
        )

    field_name = StartupProfileFieldName.BUYERS
    if field_name in request.allowed_field_names and field_name not in extracted:
        buyer_rows = _buyer_segment_rows(text)
        if buyer_rows:
            extracted[field_name] = StartupProfileExtractedField(
                field_name=field_name,
                normalized_values=tuple(buyer_rows[:MAX_VALUES_PER_FIELD]),
                status=StartupProfileFieldStatus.SOURCE_FACT,
                confidence=Decimal("0.78"),
                refs=tuple(
                    ref.model_copy(update={"confidence": Decimal("0.78")})
                    for _row in buyer_rows[:MAX_VALUES_PER_FIELD]
                ),
            )

    field_name = StartupProfileFieldName.PRICING_REVENUE_MODEL
    if field_name not in request.allowed_field_names or field_name in extracted:
        return
    tariff_rows = _tariff_rows(text)
    if not tariff_rows:
        return
    extracted[field_name] = StartupProfileExtractedField(
        field_name=field_name,
        normalized_values=tuple(tariff_rows[:MAX_VALUES_PER_FIELD]),
        status=StartupProfileFieldStatus.SOURCE_FACT,
        confidence=Decimal("0.82"),
        refs=tuple(ref.model_copy(update={"confidence": Decimal("0.82")}) for _row in tariff_rows[:MAX_VALUES_PER_FIELD]),
    )


def _extract_startup_heading(
    text: str,
    *,
    ref: StartupProfileSafeRef,
    request: StartupProfileExtractionRequest,
    extracted: dict[StartupProfileFieldName, StartupProfileExtractedField],
) -> None:
    field_name = StartupProfileFieldName.STARTUP_NAME
    if field_name not in request.allowed_field_names or field_name in extracted:
        return
    value = _first_startup_heading(text)
    if value is None:
        return
    extracted[field_name] = StartupProfileExtractedField(
        field_name=field_name,
        normalized_values=(value,),
        status=StartupProfileFieldStatus.SOURCE_FACT,
        confidence=Decimal("0.76"),
        refs=(ref.model_copy(update={"confidence": Decimal("0.76")}),),
    )


def _extract_prose_summary(
    text: str,
    *,
    ref: StartupProfileSafeRef,
    request: StartupProfileExtractionRequest,
    extracted: dict[StartupProfileFieldName, StartupProfileExtractedField],
    gap_codes: set[str],
) -> None:
    specs: tuple[tuple[StartupProfileFieldName, Decimal, Callable[[str], tuple[str | None, str | None]]], ...] = (
        (StartupProfileFieldName.ONE_LINE_DESCRIPTION, Decimal("0.72"), _first_case_sentence),
        (StartupProfileFieldName.PROBLEM, Decimal("0.74"), _first_problem_statement),
        (StartupProfileFieldName.ICP, Decimal("0.74"), _first_icp_statement),
    )
    for field_name, confidence, extractor in specs:
        if field_name not in request.allowed_field_names or field_name in extracted:
            continue
        value, gap_code = extractor(text)
        if gap_code is not None:
            gap_codes.add(gap_code)
            continue
        if value is None:
            continue
        extracted[field_name] = StartupProfileExtractedField(
            field_name=field_name,
            normalized_values=(value,),
            status=StartupProfileFieldStatus.SOURCE_FACT,
            confidence=confidence,
            refs=(ref.model_copy(update={"confidence": confidence}),),
        )


_SEMANTIC_LINE_SPECS: tuple[tuple[StartupProfileFieldName, Decimal, re.Pattern[str]], ...] = (
    (
        StartupProfileFieldName.SOLUTION,
        Decimal("0.74"),
        re.compile(r"(?iu)\b(?:platform|solution|module|разрабатывает|платформ[ауы]|модул[ьяеий])\b"),
    ),
    (
        StartupProfileFieldName.ICP,
        Decimal("0.72"),
        re.compile(
            r"(?iu)\b(?:customer|segment|universit|student|parent|agent|"
            r"клиент|сегмент|университет|студент|абитуриент|родител|агент)\b"
        ),
    ),
    (
        StartupProfileFieldName.PRICING_REVENUE_MODEL,
        Decimal("0.74"),
        re.compile(
            r"(?iu)\b(?:pricing|tariff|monetization|revenue\s+model|kzt/month|"
            r"starter\s+[\d\s]+(?:kzt|₸)|growth\s+[\d\s]+(?:kzt|₸)|"
            r"enterprise\s+[\d\s]+(?:kzt|₸)|тариф|монетизац|ценообраз|модель\s+выручки|₸/мес)\b"
        ),
    ),
    (
        StartupProfileFieldName.ASSUMPTIONS,
        Decimal("0.72"),
        re.compile(
            r"(?iu)\b(?:rating|fit|funding|forecast|roadmap|gate|go/no-go|35\.2m|"
            r"рейтинг|подбор|финанс|инвест|прогноз|роадмап|гейт|раунд)\b"
        ),
    ),
    (
        StartupProfileFieldName.WEAKNESSES,
        Decimal("0.72"),
        re.compile(
            r"(?iu)\b(?:privacy|consent|legal|no-go|fire-safety|sanitary|insurance|landlord|"
            r"персональн|соглас|правов|стоп|не\s+запуск|не\s+продолж)\b"
        ),
    ),
    (
        StartupProfileFieldName.METRIC_PACK_CANDIDATES,
        Decimal("0.72"),
        re.compile(
            r"(?iu)\b(?:tam|sam|som|rating|fit|funding|forecast|ebitda|2027|2028|2029|2030|2031|"
            r"рынок|рейтинг|подбор|финанс|инвест|прогноз|раунд)\b"
        ),
    ),
)
_SEMANTIC_APPEND_FIELDS = {
    StartupProfileFieldName.ICP,
    StartupProfileFieldName.ASSUMPTIONS,
    StartupProfileFieldName.WEAKNESSES,
    StartupProfileFieldName.METRIC_PACK_CANDIDATES,
}


def _extract_semantic_document_carriers(
    request: StartupProfileExtractionRequest,
    extracted: dict[StartupProfileFieldName, StartupProfileExtractedField],
) -> None:
    for fragment in request.fragments:
        if fragment.text.startswith("[REDACTED:"):
            continue
        text = (
            without_founder_clarification_marker(fragment.text)
            if is_founder_clarification_text(fragment.text)
            else fragment.text
        )
        ref = _fragment_ref(fragment, confidence=Decimal("0.72"))
        for field_name, confidence, marker_pattern in _SEMANTIC_LINE_SPECS:
            if field_name not in request.allowed_field_names:
                continue
            if field_name in extracted and not (
                field_name in _SEMANTIC_APPEND_FIELDS
                and len(extracted[field_name].normalized_values) < MAX_VALUES_PER_FIELD
                and extracted[field_name].status is StartupProfileFieldStatus.SOURCE_FACT
            ):
                continue
            candidates = _semantic_line_candidates(
                text,
                marker_pattern,
                field_name=field_name,
                skip_planning_context=field_name is StartupProfileFieldName.METRIC_PACK_CANDIDATES,
            )
            if field_name is StartupProfileFieldName.SOLUTION:
                candidates = tuple(
                    candidate for candidate in candidates if not _is_solution_profile_noise(candidate)
                )
            if field_name is StartupProfileFieldName.PRICING_REVENUE_MODEL:
                candidates = tuple(
                    candidate for candidate in candidates if not _is_negative_pricing_statement(candidate)
                )
            if not candidates:
                continue
            _append_profile_values(
                extracted,
                field_name=field_name,
                values=candidates,
                ref=ref.model_copy(update={"confidence": confidence}),
                confidence=confidence,
            )


def _append_profile_values(
    extracted: dict[StartupProfileFieldName, StartupProfileExtractedField],
    *,
    field_name: StartupProfileFieldName,
    values: tuple[str, ...],
    ref: StartupProfileSafeRef,
    confidence: Decimal,
) -> None:
    existing = extracted.get(field_name)
    existing_values = existing.normalized_values if existing is not None else ()
    existing_refs = existing.refs if existing is not None else ()
    merged_values: list[str] = []
    merged_refs: list[StartupProfileSafeRef] = []
    for value, value_ref in (
        *((candidate, candidate_ref) for candidate, candidate_ref in zip(existing_values, existing_refs)),
        *((candidate, ref) for candidate in values),
    ):
        if _has_equivalent_profile_value(value, merged_values):
            continue
        merged_values.append(value)
        merged_refs.append(value_ref)
        if len(merged_values) >= MAX_VALUES_PER_FIELD:
            break
    if not merged_values:
        return
    if existing is None:
        extracted[field_name] = StartupProfileExtractedField(
            field_name=field_name,
            normalized_values=tuple(merged_values),
            status=StartupProfileFieldStatus.SOURCE_FACT,
            confidence=confidence,
            refs=tuple(merged_refs),
        )
        return
    extracted[field_name] = existing.model_copy(
        update={
            "normalized_values": tuple(merged_values),
            "refs": tuple(merged_refs),
            "confidence": max(existing.confidence, confidence),
        }
    )


def _has_equivalent_profile_value(value: str, existing_values: list[str]) -> bool:
    normalized = value.casefold()
    for existing in existing_values:
        existing_normalized = existing.casefold()
        if normalized == existing_normalized:
            return True
        if normalized in existing_normalized or existing_normalized in normalized:
            return True
    return False


def _semantic_line_candidates(
    text: str,
    marker_pattern: re.Pattern[str],
    *,
    field_name: StartupProfileFieldName,
    skip_planning_context: bool,
) -> tuple[str, ...]:
    candidates: list[str] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line or marker_pattern.search(line) is None:
            continue
        labeled_field = _profile_label_at_line_start(line)
        if labeled_field is not None and labeled_field is not field_name:
            continue
        if _is_extractor_audit_metadata(line):
            continue
        if _is_profile_control_table_row(line):
            continue
        if skip_planning_context and _is_planning_metric_context(line):
            continue
        segments = [segment.strip(" •;-") for segment in re.split(r"(?<=[.!?])\s+", line)]
        relevant_segments = [segment for segment in segments if segment and marker_pattern.search(segment)]
        if not relevant_segments:
            relevant_segments = [line]
        for segment in relevant_segments:
            cleaned, gap_code = _clean_value(segment)
            if gap_code is not None and len(segment) > 240:
                cleaned, gap_code = _clean_value(_semantic_excerpt(segment, marker_pattern))
            if gap_code is None and cleaned and cleaned not in candidates:
                candidates.append(cleaned)
                if len(candidates) >= MAX_VALUES_PER_FIELD:
                    return tuple(candidates)
    return tuple(candidates)


def _profile_label_at_line_start(value: str) -> StartupProfileFieldName | None:
    for candidate_field, labels in _LABELS.items():
        for label in labels:
            if re.match(
                rf"(?iu)^\s*{re.escape(label)}(?:\s*[:—]\s*|\s+-\s+)",
                value,
            ):
                return candidate_field
    return None


def _is_extractor_audit_metadata(value: str) -> bool:
    return (
        re.match(
            r"(?iu)^\s*(?:privacy\s+sentinel|redaction\s+audit|privacy\s+audit)\s*[:—-]",
            value,
        )
        is not None
    )


def _semantic_excerpt(value: str, marker_pattern: re.Pattern[str]) -> str:
    match = marker_pattern.search(value)
    if match is None:
        return value[:240]
    start = max(0, match.start() - 90)
    end = min(len(value), match.end() + 140)
    return value[start:end].strip(" .,;:-")


def _is_solution_profile_noise(value: str) -> bool:
    normalized = " ".join(value.casefold().split())
    return any(
        pattern.search(normalized)
        for pattern in (
            re.compile(r"(?iu)\bbreak-even\b|\bgo/no-go\b"),
            re.compile(r"(?iu)\b(?:раунд|планов(?:ый|ая|ое|ые)|инвестиц|equity|capex|opex|ebitda)\b"),
            re.compile(r"(?iu)\b(?:финансир[а-яё]*|commercial\s+validation|staged\s+commercial)\b"),
            re.compile(r"(?iu)\b(?:прогноз|forecast|корпоративн[а-яё]*\s+аналог[а-яё]*|benchmark|бенчмарк)\b"),
            re.compile(r"(?iu)\d[\d\s,.]*(?:₸|kzt|usd|тенге|\$)"),
            re.compile(r"(?iu)\b(?:ключевое\s+инвестиционное\s+решение|доказать\s+b2b-спрос)\b"),
        )
    )


def _is_negative_pricing_statement(value: str) -> bool:
    normalized = " ".join(value.casefold().split())
    return any(
        pattern.search(normalized)
        for pattern in (
            re.compile(r"(?iu)\bno\s+(?:pricing|tariff|monetization|revenue\s+model)\b"),
            re.compile(
                r"(?iu)\b(?:pricing|tariff|monetization|revenue\s+model)(?:\s+\w+){0,6}\s+"
                r"(?:not\s+(?:stated|provided|available|included|specified)|missing|absent)\b"
            ),
            re.compile(
                r"(?iu)\b(?:не\s+указан[аы]?\s+(?:тариф|тарифы|модель\s+выручки)|"
                r"(?:тариф|тарифы|модель\s+выручки)\s+не\s+указан[аы]?|"
                r"нет\s+(?:тарифов?|модели\s+выручки))\b"
            ),
        )
    )


def _extract_text_metrics(
    text: str,
    *,
    ref: StartupProfileSafeRef,
    request: StartupProfileExtractionRequest,
    extracted: dict[StartupProfileFieldName, StartupProfileExtractedField],
    gap_codes: set[str],
) -> None:
    if not {
        StartupProfileFieldName.TRACTION,
        StartupProfileFieldName.METRIC_PACK_CANDIDATES,
    }.intersection(request.allowed_field_names):
        return
    values: list[str] = []
    for normalized_label, labels in _TEXT_METRIC_LABELS:
        value = None
        gap_code = None
        for raw_line in text.splitlines():
            if _is_planning_metric_context(raw_line):
                continue
            value, gap_code = _first_labeled_value(raw_line, labels, require_line_start=True)
            if gap_code is not None or value is not None:
                break
        if gap_code is not None:
            gap_codes.add(gap_code)
            continue
        if value is None:
            continue
        metric_value = _clean_metric_value(value)
        if not metric_value:
            continue
        values.append(f"{normalized_label}: {metric_value}")
    for normalized_label, pattern in _INLINE_TEXT_METRIC_PATTERNS:
        if any(value.casefold().startswith(f"{normalized_label.casefold()}:") for value in values):
            continue
        match = next(
            (
                candidate
                for candidate in pattern.finditer(text)
                if not _is_planning_metric_context(_line_containing_match(text, candidate))
            ),
            None,
        )
        if match is None:
            continue
        raw_value = match.group("value").replace(",", ".")
        unit = match.group("unit")
        metric_value = _clean_metric_value(f"{raw_value} {unit}")
        if metric_value:
            values.append(f"{normalized_label}: {metric_value}")
    if not values:
        return
    refs = tuple(
        ref.model_copy(update={"confidence": Decimal("0.78")})
        for _item in values
    )
    field = StartupProfileExtractedField(
        field_name=StartupProfileFieldName.TRACTION,
        normalized_values=tuple(values[:MAX_VALUES_PER_FIELD]),
        status=StartupProfileFieldStatus.SOURCE_FACT,
        confidence=Decimal("0.78"),
        refs=refs[:MAX_VALUES_PER_FIELD],
    )
    if StartupProfileFieldName.TRACTION in request.allowed_field_names and StartupProfileFieldName.TRACTION not in extracted:
        extracted[StartupProfileFieldName.TRACTION] = field
    if (
        StartupProfileFieldName.METRIC_PACK_CANDIDATES in request.allowed_field_names
        and StartupProfileFieldName.METRIC_PACK_CANDIDATES not in extracted
    ):
        extracted[StartupProfileFieldName.METRIC_PACK_CANDIDATES] = field.model_copy(
            update={"field_name": StartupProfileFieldName.METRIC_PACK_CANDIDATES}
        )


def _is_planning_metric_context(text: str) -> bool:
    return bool(_PLANNING_METRIC_CONTEXT_PATTERN.search(text))


def _line_containing_match(text: str, match: re.Match[str]) -> str:
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end]


def _first_case_sentence(text: str) -> tuple[str | None, str | None]:
    normalized = " ".join(text.split())
    if not normalized:
        return None, None
    russian_match = re.search(
        r"(?iu)\b[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9 .&+-]{1,40}\s+разрабатывает\s+([^.!?]{8,220}[.?!])",
        normalized,
    )
    if russian_match is not None:
        return _clean_value(russian_match.group(1))
    match = re.match(r"(?i)^([a-z0-9][a-z0-9 &/+-]{1,40}\s+case:\s*[^.?!]{8,220}[.?!])", normalized)
    if match is None:
        return None, None
    return _clean_value(match.group(1))


def _first_problem_statement(text: str) -> tuple[str | None, str | None]:
    table_value = _first_problem_table_value(text)
    if table_value is not None:
        return _clean_value(table_value)
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line:
            continue
        if not re.search(
            r"(?iu)\b(?:problem|pain|manual|fragmented|ручн[а-я]*|разрозненн[а-я]*|фрагментированн[а-я]*|ошибк[а-я]*|stock-out|теря[ею]т)\b",
            line,
        ):
            continue
        if re.search(r"(?iu)\b(?:решение|solution|ответ|response|recommendation)\b", line):
            continue
        cleaned, gap_code = _clean_value(line)
        if gap_code is None and cleaned:
            return cleaned, None
        if gap_code is not None:
            return None, gap_code
    return None, None


def _first_problem_table_value(text: str) -> str | None:
    lines = [" ".join(line.split()).strip() for line in text.splitlines()]
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(r"(?iu)\b(?:проблема\s+клиента|customer\s+problem)\b", line)
            and re.search(r"(?iu)\b(?:наблюдение|observation|следствие|impact|effect)\b", line)
        ),
        None,
    )
    if header_index is None:
        return None
    values: list[str] = []
    for line in lines[header_index + 1:]:
        if not line:
            continue
        if re.search(r"(?iu)\b(?:решение|solution|сегмент\s+профиль|тариф\s+ежемесячно)\b", line):
            break
        value = _problem_row_label(line)
        if value:
            values.append(value)
        if len(values) == 3:
            break
    return "; ".join(values) if values else None


def _problem_row_label(line: str) -> str | None:
    match = re.match(
        r"(?iu)^(.{8,90}?)\s+(?:нет|излишки|пробег|закупк[а-я]*|ошибк[а-я]*|cost|manual|no\s+|lack\s+|delays?\b|stock-out\b)",
        line,
    )
    candidate = match.group(1) if match is not None else line
    candidate = candidate.strip(" .;-")
    return candidate if len(candidate) >= 8 else None


def _first_icp_statement(text: str) -> tuple[str | None, str | None]:
    table_value = _first_segment_table_value(text)
    if table_value is not None:
        return _clean_value(table_value)
    normalized = " ".join(text.split())
    if re.search(r"(?iu)\b(?:разрабатывает|builds?|develops?)\b", normalized):
        target_match = re.search(
            r"(?iu)\bдля\s+([^.!?]{8,180}\b(?:дистрибьютор[а-я]*|розничн[а-я]*|retail|сет[а-я]*|клиент[а-я]*|customers?|segments?)[^.!?]*[.?!]?)",
            normalized,
        )
        if target_match is not None:
            return _clean_value(target_match.group(1))
    return None, None


def _first_segment_table_value(text: str) -> str | None:
    lines = [" ".join(line.split()).strip() for line in text.splitlines()]
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(r"(?iu)\b(?:сегмент\s+профиль|segment\s+profile|приоритетные\s+сегменты)\b", line)
        ),
        None,
    )
    if header_index is None:
        return None
    values: list[str] = []
    for line in lines[header_index + 1:]:
        if not line:
            continue
        if _is_navigation_control_only_value(line):
            continue
        if re.search(r"(?iu)\b(?:рынок|тариф|конкурент|альтернатива|mrr)\b", line):
            break
        value = _segment_row_label(line)
        if value:
            values.append(value)
        if len(values) == 4:
            break
    return "; ".join(values) if values else None


def _segment_row_label(line: str) -> str | None:
    match = re.match(
        r"(?iu)^(.{4,80}?)\s+(?:\d|серийн[а-я]*|собственн[а-я]*|снизить|согласовать|контроль|видимость|\d+-\d+|[0-9]+\s+склад)",
        line,
    )
    candidate = match.group(1) if match is not None else line
    candidate = candidate.strip(" .;-")
    return candidate if len(candidate) >= 4 else None


def _first_startup_heading(text: str) -> str | None:
    concept_match = re.match(
        r"(?iu)^\s*([A-Z][A-Za-z0-9&+-]*(?:\s+[A-Z][A-Za-z0-9&+-]*){0,3})\s+"
        r"is\s+(?:an?|the)\s+[^.?!]{8,180}\b(?:SaaS|service|platform|tool|app)\b",
        " ".join(text.split()),
    )
    if concept_match is not None:
        value, gap_code = _clean_value(concept_match.group(1))
        if gap_code is None and value:
            return value
    prose_match = re.search(
        r"(?iu)\b([A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9.&+-]*Flow\s+AI)\s+разрабатывает\b",
        " ".join(text.split()),
    )
    if prose_match is not None:
        value, gap_code = _clean_value(prose_match.group(1))
        if gap_code is None and value:
            return value
    for raw_line in text.splitlines()[:4]:
        line = " ".join(raw_line.split()).strip()
        if not line or ":" in line or len(line) > 80:
            continue
        if re.search(r"(?iu)^(?:решение|solution)\b", line):
            continue
        if "|" in line:
            continue
        if re.search(r"(?iu)\b(?:инвестиционный|бизнес-план|профиль|проект|раунд|seed)\b", line):
            continue
        if re.search(r"(?iu)\b(?:qa-документ|qa document|capstone|не для инвестирования)\b", line):
            continue
        if re.fullmatch(r"[A-Z][A-Z0-9&+-]{1,}(?:\s+[A-Z][A-Z0-9&+-]{1,}){1,3}", line):
            if re.search(
                r"(?i)\b(?:BUSINESS\s+PLAN|EXECUTIVE\s+SUMMARY|MARKET\s+ANALYSIS|"
                r"FINANCIAL\s+MODEL|INVESTMENT\s+MEMORANDUM)\b",
                line,
            ) is None:
                value, gap_code = _clean_value(line)
                if gap_code is None and value:
                    return value
        if re.search(r"(?iu)\b(?:b2b|управлени[ея]|логистик[аои]|рынок|для)\b", line):
            continue
        if not re.search(r"(?iu)\b(?:AI|Inc|LLC|SaaS|[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9]+Flow)\b", line):
            continue
        value, gap_code = _clean_value(line)
        if gap_code is None and value:
            return value
    return None


def _extract_idea_stage(
    text: str,
    *,
    ref: StartupProfileSafeRef,
    request: StartupProfileExtractionRequest,
    extracted: dict[StartupProfileFieldName, StartupProfileExtractedField],
) -> None:
    field_name = StartupProfileFieldName.STAGE
    if field_name not in request.allowed_field_names or field_name in extracted:
        return
    if not re.search(r"(?iu)\b(?:founder\s+idea\s+brief|idea-only|idea\s+brief)\b", text):
        return
    extracted[field_name] = StartupProfileExtractedField(
        field_name=field_name,
        normalized_values=("idea",),
        status=StartupProfileFieldStatus.SOURCE_FACT,
        confidence=Decimal("0.76"),
        refs=(ref.model_copy(update={"confidence": Decimal("0.76")}),),
    )


def _first_table_row_value(
    text: str,
    labels: tuple[str, ...],
    *,
    sibling_keys: tuple[str, ...],
) -> str | None:
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        for label in labels:
            match = re.search(rf"(?iu)(?:^|\s){re.escape(label)}\s+(.+)$", line)
            if match is None:
                continue
            value = _stop_at_sibling_key(match.group(1), sibling_keys)
            cleaned, gap_code = _clean_value(value)
            if gap_code is None and cleaned:
                return cleaned
    return None


def _tariff_rows(text: str) -> tuple[str, ...]:
    has_header = any(_is_tariff_header(line) for line in text.splitlines())
    if not has_header:
        return ()
    rows: list[str] = []
    for raw_line in text.splitlines():
        row = _tariff_row(raw_line)
        if row is None:
            continue
        rows.append(row)
    return tuple(rows)


def _is_tariff_header(text: str) -> bool:
    normalized = " ".join(text.split())
    return bool(
        re.search(r"(?iu)^Тариф\s+Ежемесячно\s+Разовый\s+запуск\s+Включено$", normalized)
        or (
            re.search(r"(?iu)\b(?:Тариф|Pricing|Tariff)\b", normalized) is not None
            and re.search(
                r"(?iu)\b(?:Подписка|subscription|Accepted\s+leads?|Что\s+получает)\b",
                normalized,
            )
            is not None
        )
    )


def _tariff_row(text: str) -> str | None:
    line = " ".join(text.split()).strip()
    if not re.match(r"(?iu)^(?:Starter|Growth|Enterprise)\s+", line):
        return None
    if not re.search(r"[₸$€]|(?:\bKZT\b|\bUSD\b|\bEUR\b)", line):
        return None
    cleaned, gap_code = _clean_value(line)
    if gap_code is not None or not cleaned:
        return None
    return cleaned


def _buyer_segment_rows(text: str) -> tuple[str, ...]:
    lines = [" ".join(line.split()).strip() for line in text.splitlines()]
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if _is_buyer_segment_header(line)
        ),
        None,
    )
    if header_index is None:
        return ()
    buyers: list[str] = []
    for line in lines[header_index + 1:]:
        if not line:
            continue
        if re.search(r"(?iu)\b(?:рынок|market|тариф|pricing|конкурент|competitor|mrr)\b", line):
            break
        buyer = _buyer_segment_row(line)
        if buyer is None:
            continue
        if buyer not in buyers:
            buyers.append(buyer)
        if len(buyers) >= MAX_VALUES_PER_FIELD:
            break
    return tuple(buyers)


def _is_buyer_segment_header(text: str) -> bool:
    normalized = " ".join(text.split())
    return (
        re.search(r"(?iu)\b(?:Сегмент|Segment)\b", normalized) is not None
        and re.search(r"(?iu)\b(?:Job-to-be-done|JTBD)\b", normalized) is not None
        and re.search(r"(?iu)\b(?:Плат[её]ж|Payment|Accepted\s+leads?|Подписка)\b", normalized)
        is not None
    )


def _buyer_segment_row(text: str) -> str | None:
    line = " ".join(text.split()).strip(" .;-")
    if not line or _is_profile_control_table_row(line):
        return None
    if re.search(r"(?iu)\b(?:Accepted\s+leads?|Подписка|Payment|Плат[её]ж|₸|\bKZT\b)\b", line) is None:
        return None
    split_match = re.search(
        r"(?iu)\s+(?:снизить|ускорить|быстрее|закрывать|получить|увеличить|уменьшить|"
        r"найти|поднять|контролировать|автоматизировать|reduce|increase|close|"
        r"find|automate|control|speed\s+up|faster)\b",
        line,
    )
    if split_match is not None:
        candidate = line[: split_match.start()]
    else:
        payment_match = re.search(r"(?iu)\b(?:Accepted\s+leads?|Подписка|Payment|Плат[её]ж|₸|\bKZT\b)\b", line)
        if payment_match is None:
            return None
        candidate = line[: payment_match.start()]
    candidate = candidate.strip(" .;-")
    if len(candidate) < 4:
        return None
    cleaned, gap_code = _clean_value(candidate)
    if gap_code is not None or not cleaned:
        return None
    return cleaned


def _stop_at_sibling_key(value: str, sibling_keys: tuple[str, ...]) -> str:
    earliest: int | None = None
    for key in sibling_keys:
        match = re.search(rf"(?iu)\s+\b{re.escape(key)}\b", value)
        if match is not None and (earliest is None or match.start() < earliest):
            earliest = match.start()
    return value[:earliest] if earliest is not None else value


def _strip_deferred_vertical_from_geography(value: str) -> str:
    segments = [segment.strip(" .;:-—") for segment in value.split(";")]
    if len(segments) < 2:
        return value
    deferred_vertical = re.compile(
        r"(?iu)\b(?:жиль[еёя]|аренд[ауы]?|недвижимост[ьи]|общежити[ея]|койко-?мест|housing|real\s+estate|rentals?)\b"
    )
    if any(deferred_vertical.search(segment) is not None for segment in segments[1:]):
        locations: list[str] = []
        for segment in segments[1:]:
            if deferred_vertical.search(segment) is None:
                continue
            location = deferred_vertical.sub("", segment)
            location = re.sub(r"\s+", " ", location).strip(" .;:-—")
            if location:
                locations.append(location)
        if locations:
            return ", ".join(dict.fromkeys((segments[0], *locations)))
        return segments[0]
    return value


def _metric_conflicts(
    entries: list[tuple[str, StartupProfileSafeRef, str, str]],
) -> tuple[list[str], list[StartupProfileSafeRef], set[UUID], set[str]]:
    values: list[str] = []
    refs: list[StartupProfileSafeRef] = []
    source_ref_ids: set[UUID] = set()
    gap_codes: set[str] = set()
    specs: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
        ("mrr", "MRR conflict", "metric_conflict_mrr", ("mrr",)),
        ("customers", "Customers conflict", "metric_conflict_customers", ("customer", "customers", "клиент")),
        (
            "gross_margin",
            "Gross margin conflict",
            "metric_conflict_gross_margin",
            ("gross margin", "валовая маржа"),
        ),
        ("cac_payback", "CAC payback conflict", "metric_conflict_cac_payback", ("cac payback",)),
    )
    for _group_key, label, gap_code, needles in specs:
        group = [
            (value, ref, name, normalized_value)
            for value, ref, name, normalized_value in entries
            if any(needle in name.casefold() for needle in needles)
        ]
        distinct_values = {normalized_value.casefold() for _value, _ref, _name, normalized_value in group}
        if len(group) < 2 or len(distinct_values) < 2:
            continue
        distinct_group: list[tuple[str, StartupProfileSafeRef, str, str]] = []
        seen_values: set[str] = set()
        for item in group:
            normalized_key = item[3].casefold()
            if normalized_key in seen_values:
                continue
            seen_values.add(normalized_key)
            distinct_group.append(item)
            if len(distinct_group) == 2:
                break
        first, second = distinct_group[0], distinct_group[1]
        values.append(f"{label}: {_metric_fact_without_colon(first[0])} | {_metric_fact_without_colon(second[0])}")
        refs.extend((first[1], second[1]))
        source_ref_ids.update(item[1].ref_id for item in group)
        gap_codes.add(gap_code)
    return values, refs, source_ref_ids, gap_codes


def _metric_fact_without_colon(value: str) -> str:
    return value.replace(":", "", 1)


def _clean_metric_value(value: str) -> str:
    cleaned = " ".join(value.split()).strip(" .;-")
    cleaned = re.sub(r"(?iu)\bв\s+(?=[а-яa-z]*\s*20\d{2}\b)", "", cleaned)
    return cleaned.strip(" .;-")


def _clean_value(value: str) -> tuple[str, str | None]:
    stripped = " ".join(value.split()).strip(" -")
    if not stripped or "[REDACTED:" in stripped:
        return "", None
    if _is_profile_control_table_row(stripped):
        return "", None
    lowered = stripped.casefold()
    if _is_navigation_control_only_value(lowered):
        return "", None
    if "sk-proj-" in lowered or ":\\" in stripped or ("@" in stripped and "." in stripped.rsplit("@", 1)[-1]):
        return "", None
    if len(stripped) > 240:
        return "", "deterministic_value_too_long"
    return stripped, None


def _is_navigation_control_only_value(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value).strip(" .;:—-→")
    profile_labels = "|".join(re.escape(label) for labels in _LABELS.values() for label in labels)
    normalized = re.sub(
        rf"(?iu)^(?:{profile_labels})(?:\s+[^:\r\n—-]{{1,80}})?(?:\s*[:—]\s*|\s+-\s+)",
        "",
        normalized,
        count=1,
    )
    simple_control = re.fullmatch(
        r"(?iu)(?:go\s*/\s*pause(?:\s+(?:next action|следующее действие))?|"
        r"next action|следующее действие|next|previous|back|continue|pause)",
        normalized,
    )
    table_control = re.fullmatch(
        r"(?iu)(?:"
        r"решение\s+go\s+no-go\s*/\s*pause\s+следующее\s+действие|"
        r"solution\s+go\s+no-go\s*/\s*pause\s+next\s+action|"
        r"сегмент\s+job-to-be-done\s+плат[её]ж\s+первый\s+продукт|"
        r"segment\s+job-to-be-done\s+payment\s+first\s+product"
        r")",
        normalized,
    )
    return simple_control is not None or table_control is not None


def _is_profile_control_table_row(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value).casefold().strip(" .;:—-→")
    if not normalized:
        return False
    if re.fullmatch(
        r"(?iu)(?:решение\s+)?go\s+no-go\s*/\s*pause(?:\s+следующее действие|\s+next action)?",
        normalized,
    ):
        return True
    if re.fullmatch(
        r"(?iu)(?:solution\s+)?go\s*/\s*pause(?:\s+next action|\s+следующее действие)?",
        normalized,
    ):
        return True
    has_jtbd_header = re.search(r"(?iu)\b(?:job-to-be-done|be-done)\b", normalized) is not None
    has_worksheet_label = re.search(
        r"(?iu)\b(?:segment|сегмент|плат[её]ж|first product|первый продукт)\b",
        normalized,
    ) is not None
    return has_jtbd_header and has_worksheet_label
