type StartupProfilePresentationField = Readonly<{
  status: "source_fact" | "inference" | "insufficient_data" | "contradiction";
  values: readonly string[];
  confidence: string;
  evidence_refs: readonly Readonly<{ evidence_id: string }>[];
  dependency_refs: readonly string[];
  reason_code: string | null;
  contradiction_ids: readonly string[];
}>;

type StartupProfilePresentationInput<TFieldName extends string> = Readonly<{
  profile_id: string;
  profile_hash: string;
  data_revision: number;
  analysis_stage: "primary" | "enriched";
  parent_profile_id: string | null;
  fields: Readonly<Record<TFieldName, StartupProfilePresentationField>>;
  gaps: readonly string[];
  contradictions: readonly string[];
  parse_inventory: Readonly<{
    source_hashes: Readonly<Record<string, string>>;
    parse_outcomes: Readonly<Record<string, string>>;
  }>;
}>;

export type StartupProfilePresentationCard = Readonly<{
  field: string;
  status: StartupProfilePresentationField["status"];
  valueLabel: string;
  labelRu: string;
  valueLabelRu: string;
  confidence: string;
  evidenceIds: readonly string[];
  dependencyIds: readonly string[];
  contradictionIds: readonly string[];
  reasonCode: string | null;
  technicalReasonCode: string | null;
  nextActionRu: string;
}>;

export type StartupProfileCoveragePresentation = Readonly<{
  totalFieldCount: number;
  coveredFieldCount: number;
  sourceFactFieldCount: number;
  inferredFieldCount: number;
  contradictionFieldCount: number;
  missingFieldCount: number;
  coveragePercent: number;
  evidenceBackedPercent: number;
}>;

export type StartupProfilePresentation = Readonly<{
  profileId: string;
  profileHash: string;
  parentProfileId: string | null;
  stageLabel: "Первичный профиль" | "Углублённый профиль";
  stageLabelRu: "Первичный профиль" | "Углублённый профиль";
  snapshotLabel: string;
  cards: readonly StartupProfilePresentationCard[];
  gapCodes: readonly string[];
  contradictionIds: readonly string[];
  gapCount: number;
  contradictionCount: number;
  sourceCount: number;
  parsedSourceCount: number;
  coverage: StartupProfileCoveragePresentation;
}>;

const fieldLabelsRu: Readonly<Record<string, string>> = {
  startup_name: "Название",
  one_line_description: "Описание в одну строку",
  problem: "Проблема",
  solution: "Решение",
  icp: "Идеальный клиент",
  users: "Пользователи",
  buyers: "Покупатели",
  geography: "География",
  stage: "Стадия",
  business_model: "Бизнес-модель",
  pricing_revenue_model: "Цена и выручка",
  traction: "Сигналы спроса",
  channels_gtm: "Каналы продаж",
  competitors_mentioned: "Конкуренты",
  assumptions: "Допущения",
  strengths: "Сильные стороны",
  weaknesses: "Слабые стороны",
  metric_pack_candidates: "Кандидаты в метрики",
};

const missingGuidanceRu: Readonly<Record<string, string>> = {
  startup_name:
    "Пока нет подтверждённого названия. Добавьте титульный слайд или краткое описание компании, и я свяжу выводы с конкретным проектом.",
  one_line_description:
    "Пока нет короткого позиционирования. Добавьте одну фразу: для кого продукт, какую боль снимает и чем отличается.",
  problem:
    "Пока боль не подтверждена. Добавьте 2-3 примера клиентской боли, частоту проблемы и текущую альтернативу.",
  solution:
    "Пока решение описано слабо. Добавьте, что делает продукт, какой результат получает клиент и почему это лучше текущего способа.",
  icp:
    "Пока нет подтверждённого сегмента. Добавьте целевой сегмент (ICP), бюджет владельца и пример покупателя, и я уточню позиционирование.",
  users:
    "Пока неясны пользователи. Добавьте роли, которые работают в продукте каждый день, и их основной сценарий.",
  buyers:
    "Пока неясен покупатель. Добавьте лицо, которое подписывает бюджет, критерии покупки и пример сделки.",
  geography:
    "Пока география не подтверждена. Добавьте стартовый рынок, язык продаж и ограничения по стране или региону.",
  stage:
    "Пока стадия не подтверждена. Добавьте статус продукта, пилотов, продаж и ближайшую контрольную точку.",
  business_model:
    "Пока модель монетизации не подтверждена. Добавьте тариф, единицу оплаты, цикл сделки и кто платит.",
  pricing_revenue_model:
    "Пока цена и выручка не подтверждены. Добавьте ежемесячную и годовую регулярную выручку (MRR/ARR), средний чек, валовую маржу и период расчёта.",
  traction:
    "Пока сигналы спроса не подтверждены. Добавьте пользователей, платящих клиентов, ежемесячную и годовую регулярную выручку (MRR/ARR), удержание и период метрик.",
  channels_gtm:
    "Пока канал продаж не подтверждён. Добавьте 1-2 канала, стоимость привлечения, конверсию или ранние сигналы спроса.",
  competitors_mentioned:
    "Пока конкуренты не подтверждены. Добавьте прямых конкурентов, альтернативы и почему клиент выберет вас.",
  assumptions:
    "Пока ключевые гипотезы не выделены. Добавьте 3-5 допущений, от которых зависит рост или выручка.",
  strengths:
    "Пока сильные стороны не подтверждены. Добавьте факты о команде, продукте, каналах или клиентах.",
  weaknesses:
    "Пока слабые места не подтверждены. Добавьте известные риски, ограничения продукта и слабые места выхода на рынок.",
  metric_pack_candidates:
    "Пока набор метрик не собран. Добавьте ежемесячную и годовую регулярную выручку (MRR/ARR), стоимость привлечения клиента (CAC), ценность клиента (LTV), отток клиентов, удержание, темп расходов и запас времени, если они есть.",
};

const nextActionsRu: Readonly<
  Record<StartupProfilePresentationField["status"], string>
> = {
  source_fact:
    "Используйте этот факт как основу следующего вывода и проверьте, что дата и определение метрики актуальны.",
  inference:
    "Подтвердите вывод отдельным источником или оставьте как рабочую гипотезу для следующего анализа.",
  insufficient_data:
    "Добавьте указанный параметр или разрешите отдельный поиск по рынку, и я расширю анализ без изменения текущих фактов.",
  contradiction:
    "Сверьте противоречивые цифры и оставьте одну версию с датой, источником и определением метрики.",
};

function readableValueRu(
  field: string,
  value: StartupProfilePresentationField,
): string {
  if (value.status === "insufficient_data" || value.values.length === 0) {
    return (
      missingGuidanceRu[field] ??
      "Пока поле не подтверждено. Добавьте конкретный источник или параметр, и я уточню вывод."
    );
  }
  return value.values.join(" · ");
}

function percent(numerator: number, denominator: number): number {
  if (denominator <= 0) return 0;
  return Math.round((numerator / denominator) * 100);
}

function buildCoverage(
  fields: readonly StartupProfilePresentationField[],
): StartupProfileCoveragePresentation {
  const totalFieldCount = fields.length;
  const sourceFactFieldCount = fields.filter(
    (field) =>
      field.status === "source_fact" &&
      field.values.length > 0 &&
      field.evidence_refs.length > 0,
  ).length;
  const inferredFieldCount = fields.filter(
    (field) => field.status === "inference" && field.values.length > 0,
  ).length;
  const contradictionFieldCount = fields.filter(
    (field) => field.status === "contradiction" && field.values.length > 0,
  ).length;
  const missingFieldCount = fields.filter(
    (field) => field.status === "insufficient_data" || field.values.length === 0,
  ).length;
  const coveredFieldCount =
    sourceFactFieldCount + inferredFieldCount + contradictionFieldCount;

  return {
    totalFieldCount,
    coveredFieldCount,
    sourceFactFieldCount,
    inferredFieldCount,
    contradictionFieldCount,
    missingFieldCount,
    coveragePercent: percent(coveredFieldCount, totalFieldCount),
    evidenceBackedPercent: percent(sourceFactFieldCount, totalFieldCount),
  };
}

export function buildStartupProfilePresentation<TFieldName extends string>(
  profile: StartupProfilePresentationInput<TFieldName>,
): StartupProfilePresentation {
  const fieldEntries = Object.entries<StartupProfilePresentationField>(
    profile.fields,
  );
  const cards = Object.entries<StartupProfilePresentationField>(
    profile.fields,
  ).map(([field, value]) => ({
    field,
    status: value.status,
    valueLabel: value.values.length > 0 ? value.values.join(" · ") : "Не указано",
    labelRu: fieldLabelsRu[field] ?? field,
    valueLabelRu: readableValueRu(field, value),
    confidence: value.confidence,
    evidenceIds: value.evidence_refs.map((reference) => reference.evidence_id),
    dependencyIds: [...value.dependency_refs],
    contradictionIds: [...value.contradiction_ids],
    reasonCode: value.reason_code,
    technicalReasonCode: value.reason_code,
    nextActionRu: nextActionsRu[value.status],
  }));

  return {
    profileId: profile.profile_id,
    profileHash: profile.profile_hash,
    parentProfileId: profile.parent_profile_id,
    stageLabel:
      profile.analysis_stage === "primary"
        ? "Первичный профиль"
        : "Углублённый профиль",
    stageLabelRu:
      profile.analysis_stage === "primary"
        ? "Первичный профиль"
        : "Углублённый профиль",
    snapshotLabel: `Версия данных ${profile.data_revision}`,
    cards,
    gapCodes: [...profile.gaps],
    contradictionIds: [...profile.contradictions],
    gapCount: profile.gaps.length,
    contradictionCount: profile.contradictions.length,
    sourceCount: Object.keys(profile.parse_inventory.source_hashes).length,
    parsedSourceCount: Object.values(
      profile.parse_inventory.parse_outcomes,
    ).filter((outcome) => outcome === "parsed").length,
    coverage: buildCoverage(fieldEntries.map(([, value]) => value)),
  };
}
