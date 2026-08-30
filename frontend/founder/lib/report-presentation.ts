import type {
  FounderReportSectionStatus,
  StartupReportSectionKey,
  StartupReportSnapshotResponse,
} from "./contracts.ts";

export const REPORT_MAIN_SECTION_ORDER = [
  "business_idea_summary",
  "problem_solution",
  "market_size",
  "competitors",
  "moat",
  "go_to_market",
  "metrics",
  "financial_assumptions",
  "risks",
  "evidence_gaps",
  "diligence_questions",
  "action_plan",
] as const satisfies readonly StartupReportSectionKey[];

export type FounderReportSectionPresentation = Readonly<{
  key: (typeof REPORT_MAIN_SECTION_ORDER)[number];
  title: string;
  summary: string;
  status: "supported" | "partial" | "needs_evidence" | "contradiction";
  statusLabel: string;
  rows: readonly (readonly string[])[];
  items: readonly string[];
}>;

export type FounderReportPresentation = Readonly<{
  sections: readonly FounderReportSectionPresentation[];
}>;

const unsafeFounderReportPattern =
  /(?:\bMISSING(?:[_-][A-Z0-9]+)*\b|sha256:[0-9a-f]{64}|[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}|[A-Za-z]:[\\/][^\s]+|(?:^|[\s"'(])(?:\.{1,2}[\\/])?(?:[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+\.[A-Za-z0-9]{2,5}(?:$|[\s"',).])|\b[A-Za-z0-9_.-]+\.(?:pdf|docx?|pptx?|xlsx?|csv|json|txt|md)\b|\b(?:prompt(?:[_-][A-Z0-9]+)*|(?:api[_-]?)?token|trace[_-]?ids?|raw excerpt|profile_id|gtm_snapshot|section_ref)\b|(?:readiness|profile_contradiction):)/iu;

export function buildFounderReportPresentation(
  snapshot: StartupReportSnapshotResponse,
): FounderReportPresentation {
  const sectionsByKey = new Map(snapshot.main_sections.map((section) => [section.key, section]));
  return {
    sections: REPORT_MAIN_SECTION_ORDER.flatMap((key) => {
      const section = sectionsByKey.get(key);
      if (!section) return [];
      return {
        key,
        title: safeFounderReportText(section.title_ru),
        summary: safeFounderReportText(section.summary_ru),
        status: founderStatus(section.status),
        statusLabel: safeFounderReportText(section.status_label_ru),
        rows: section.known_facts_ru.map((fact) => [
          safeFounderReportText(section.content_heading_ru),
          safeFounderReportText(fact),
        ]).filter((row) => row.every(Boolean)),
        items: projectFounderItems(key, section),
      };
    }),
  };
}

function founderStatus(status: FounderReportSectionStatus): FounderReportSectionPresentation["status"] {
  if (status === "confirmed") return "supported";
  if (status === "partial") return "partial";
  if (status === "contradiction") return "contradiction";
  return "needs_evidence";
}

function projectFounderItems(
  key: StartupReportSectionKey,
  section: StartupReportSnapshotResponse["main_sections"][number],
): readonly string[] {
  const roleSpecificFacts =
    key === "diligence_questions" || key === "action_plan" ? section.known_facts_ru : [];
  return uniqueSafeFounderTexts([
    ...roleSpecificFacts,
    ...section.blockers_ru,
    ...section.next_data_ru,
    ...section.unlocks_ru,
  ]);
}

function uniqueSafeFounderTexts(values: readonly string[]): readonly string[] {
  const seen = new Set<string>();
  const projected: string[] = [];
  for (const value of values) {
    const safe = safeFounderReportText(value);
    if (!safe || seen.has(safe)) continue;
    seen.add(safe);
    projected.push(safe);
  }
  return projected;
}

function safeFounderReportText(value: string): string {
  const trimmed = value.trim();
  if (unsafeFounderReportPattern.test(trimmed)) return "";
  return trimmed;
}
