import assert from "node:assert/strict";
import test from "node:test";

import {
  buildFounderReportPresentation,
  REPORT_MAIN_SECTION_ORDER,
} from "./report-presentation.ts";
import type { StartupReportSnapshotResponse } from "./contracts.ts";

const reportSnapshot = {
  title_ru: "Отчёт для основателя",
  subtitle_ru: "Краткий разбор проекта, блокеры и следующие шаги",
  as_of_ru: "2026-08-15",
  data_revision: 4,
  main_sections: [
    safeSection("business_idea_summary", "Идея бизнеса", "confirmed", ["FounderCo", "SMB finance teams"]),
    safeSection("problem_solution", "Проблема и решение", "confirmed", ["Manual invoice reconciliation", "AI review queue"]),
    safeSection("market_size", "Размер рынка", "needs_input", [], ["Уточните размер рынка"]),
    safeSection("competitors", "Конкуренты", "partial", ["LedgerPilot", "limited source coverage"]),
    safeSection("moat", "Защитимость", "partial", ["workflow-specific reconciliation rules"], ["Проверьте разделы без достаточных доказательств"]),
    safeSection("go_to_market", "Выход на рынок", "confirmed", ["partner-led finance communities"]),
    safeSection("metrics", "Метрики", "partial", ["ARR указан как 1200000 USD"], ["Нужна детализация по CAC"]),
    safeSection("financial_assumptions", "Финансовые предположения", "partial", ["Валовая маржа указана как 0.72"], ["Подтвердить pricing"]),
    safeSection("risks", "Риски", "confirmed", ["adoption depends on finance workflow migration"]),
    safeSection("evidence_gaps", "Пробелы в доказательствах", "needs_input", [], ["Для GTM не хватает доказательств канала.", "Есть противоречие по условиям пилота."]),
    safeSection("diligence_questions", "Вопросы для проверки", "confirmed", [], ["Уточните, кто владелец бюджета у целевой аудитории.", "Подтвердите условия платного пилота."]),
    safeSection("action_plan", "План действий", "confirmed", [], ["Проверьте разделы без достаточных доказательств.", "Одобрите Gate 4 по текущей версии данных."]),
  ],
  metric_cards: {},
  improvement_proposals: [],
  technical_appendix: {
    methodology_ru: ["Отчёт построен по агрегированным разделам анализа."],
    sources_ru: ["Использованы материалы, загруженные в рабочую область."],
  },
  analytics: {
    metric_points: [],
    market_points: [],
    readiness_dimensions: [],
  },
} as const satisfies StartupReportSnapshotResponse;

function safeSection(
  key: StartupReportSnapshotResponse["main_sections"][number]["key"],
  title_ru: string,
  status: StartupReportSnapshotResponse["main_sections"][number]["status"],
  known_facts_ru: readonly string[] = [],
  blockers_ru: readonly string[] = [],
) {
  return {
    key,
    title_ru,
    status,
    status_label_ru:
      status === "confirmed"
        ? "Подтверждено"
        : status === "partial"
          ? "Частично"
          : status === "contradiction"
            ? "Противоречие"
            : "Нужно доказательство",
    summary_ru: `${title_ru}: founder-safe summary.`,
    content_heading_ru:
      key === "risks" ? "Риск" : key === "business_idea_summary" ? "Название" : "Факт",
    known_facts_ru,
    blockers_ru,
    next_data_ru: [],
    unlocks_ru: [],
  };
}

test("projects the 12 canonical main report sections in backend order", () => {
  const presentation = buildFounderReportPresentation(reportSnapshot);

  assert.deepEqual(
    presentation.sections.map((section) => section.key),
    REPORT_MAIN_SECTION_ORDER,
  );
  assert.equal(presentation.sections.length, 12);
  assert.deepEqual(
    presentation.sections.map((section) => section.status),
    [
      "supported",
      "supported",
      "needs_evidence",
      "partial",
      "partial",
      "supported",
      "partial",
      "partial",
      "supported",
      "needs_evidence",
      "supported",
      "supported",
    ],
  );
  assert.deepEqual(presentation.sections[0]?.rows, [
    ["Название", "FounderCo"],
    ["Название", "SMB finance teams"],
  ]);
  assert.deepEqual(presentation.sections[10]?.items, [
    "Уточните, кто владелец бюджета у целевой аудитории.",
    "Подтвердите условия платного пилота.",
  ]);
  assert.equal("lineage" in presentation, false);
});

test("keeps methodology, source appendix, and private raw material out of the main projection", () => {
  const presentation = buildFounderReportPresentation(reportSnapshot);
  const projected = JSON.stringify(presentation);

  assert.doesNotMatch(projected, /methodology|source_appendix/u);
  assert.doesNotMatch(projected, /profile_id|gtm_snapshot_id/u);
  assert.doesNotMatch(projected, /C:\\Users\\Akana|private\\deck\.pdf/u);
  assert.doesNotMatch(projected, /\b(raw excerpt|prompt|token)\b/iu);
  assert.doesNotMatch(projected, /\b(score|chart|forecast)\b/iu);
  assert.equal("score" in presentation, false);
  assert.equal("charts" in presentation, false);
  assert.equal("forecast" in presentation, false);
});

test("projects founder report content into safe Russian business copy", () => {
  const presentation = buildFounderReportPresentation(reportSnapshot);
  const projected = JSON.stringify(presentation);

  assert.deepEqual(
    presentation.sections.map((section) => section.title),
    [
      "Идея бизнеса",
      "Проблема и решение",
      "Размер рынка",
      "Конкуренты",
      "Защитимость",
      "Выход на рынок",
      "Метрики",
      "Финансовые предположения",
      "Риски",
      "Пробелы в доказательствах",
      "Вопросы для проверки",
      "План действий",
    ],
  );
  assert.match(projected, /Уточните размер рынка/u);
  assert.match(projected, /Проверьте разделы без достаточных доказательств/u);
  assert.match(projected, /FounderCo|SMB finance teams/u);
  assert.doesNotMatch(
    projected,
    /Business Idea Summary|Problem \/ Solution|Market Size|Evidence Gaps|Diligence Questions|Action Plan|Resolve MISSING sections|Approve Gate 4|MISSING|sha256|00000000-0000-4000-8000|readiness:|profile_contradiction|startup_name|section_ref|gtm_snapshot|prompt|token|raw excerpt/iu,
  );
});

test("uses founder-safe known facts as primary items for diligence questions and action plan only", () => {
  const snapshot = {
    ...reportSnapshot,
    main_sections: reportSnapshot.main_sections.map((section) => {
      if (section.key === "diligence_questions") {
        return {
          ...section,
          known_facts_ru: [
            "Какие источники и расчёт подтверждают TAM / SAM / SOM?",
            "Какой клиентский сегмент и канал продаж имеют приоритет на первом цикле?",
            "Какой риск самый высокий и какой план снижения риска уже готов?",
            "Какие источники и расчёт подтверждают TAM / SAM / SOM?",
          ],
          blockers_ru: ["Проверьте разделы без достаточных доказательств."],
          next_data_ru: ["Добавьте первичные интервью."],
          unlocks_ru: ["Зафиксируйте owner review."],
        };
      }
      if (section.key === "action_plan") {
        return {
          ...section,
          known_facts_ru: [
            "7 дней: закрыть TAM / SAM / SOM и подтвердить расчёт источниками.",
            "30 дней: провести 10 интервью с приоритетным сегментом.",
            "60 дней: запустить платный пилот с двумя якорными клиентами.",
            "90 дней: пересчитать unit economics по фактическим данным пилота.",
          ],
          blockers_ru: ["Проверьте разделы без достаточных доказательств."],
          next_data_ru: ["Добавьте первичные интервью."],
          unlocks_ru: ["Зафиксируйте owner review."],
        };
      }
      return section;
    }),
  } as const satisfies StartupReportSnapshotResponse;

  const presentation = buildFounderReportPresentation(snapshot);
  const marketSize = presentation.sections.find((section) => section.key === "market_size");
  const questions = presentation.sections.find((section) => section.key === "diligence_questions");
  const actionPlan = presentation.sections.find((section) => section.key === "action_plan");

  assert.ok(marketSize);
  assert.ok(questions);
  assert.ok(actionPlan);
  assert.deepEqual(marketSize.items, ["Уточните размер рынка"]);
  assert.deepEqual(questions.items.slice(0, 3), [
    "Какие источники и расчёт подтверждают TAM / SAM / SOM?",
    "Какой клиентский сегмент и канал продаж имеют приоритет на первом цикле?",
    "Какой риск самый высокий и какой план снижения риска уже готов?",
  ]);
  assert.equal(
    questions.items.indexOf("Проверьте разделы без достаточных доказательств."),
    3,
  );
  assert.deepEqual(actionPlan.items.slice(0, 4), [
    "7 дней: закрыть TAM / SAM / SOM и подтвердить расчёт источниками.",
    "30 дней: провести 10 интервью с приоритетным сегментом.",
    "60 дней: запустить платный пилот с двумя якорными клиентами.",
    "90 дней: пересчитать unit economics по фактическим данным пилота.",
  ]);
  assert.equal(
    actionPlan.items.indexOf("Проверьте разделы без достаточных доказательств."),
    4,
  );
});

test("fails closed for compound internal markers and relative private filenames", () => {
  const unsafeSnapshot = {
    ...reportSnapshot,
    main_sections: reportSnapshot.main_sections.map((section) =>
      section.key === "risks"
        ? {
            ...section,
            known_facts_ru: [
              "MISSING_DATA",
              "API_TOKEN",
              "TRACE_ID",
              "PROMPT_TEMPLATE",
              "private/deck.pdf",
              "private\\deck.pdf",
              "adoption depends on finance workflow migration",
            ],
            blockers_ru: [
              "MISSING_DATA",
              "api_token",
              "TRACE_ID",
              "Prompt template",
              "private/deck.pdf",
              "private\\deck.pdf",
              "Check migration risk with two finance leads.",
            ],
          }
        : section,
    ),
  } as const;

  const presentation = buildFounderReportPresentation(unsafeSnapshot);
  const projected = JSON.stringify(presentation);
  const risks = presentation.sections.find((section) => section.key === "risks");

  assert.ok(risks);
  assert.deepEqual(risks.rows, [["Риск", "adoption depends on finance workflow migration"]]);
  assert.deepEqual(risks.items, ["Check migration risk with two finance leads."]);
  assert.match(projected, /Риски/u);
  assert.doesNotMatch(
    projected,
    /MISSING_DATA|API_TOKEN|TRACE_ID|PROMPT_TEMPLATE|Prompt template|private[\\/]deck\.pdf/iu,
  );
});
