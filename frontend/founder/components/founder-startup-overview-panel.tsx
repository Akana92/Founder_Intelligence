import type { StartupProfileResponse } from "@/lib/contracts";
import { safeFounderText } from "@/lib/advisor-presentation";

export function FounderStartupOverviewPanel({
  profile,
}: Readonly<{ profile: StartupProfileResponse | null }>) {
  const cards = [
    ["Стартап", firstProfileValue(profile, "startup_name", "Название появится после анализа")],
    [
      "Что делает",
      firstProfileValue(profile, "one_line_description", "Краткое описание ещё не заполнено"),
    ],
    ["Проблема", firstProfileValue(profile, "problem", "Проблема требует уточнения")],
    ["Клиент", firstProfileValue(profile, "icp", "ICP ещё не заполнен")],
    [
      "Монетизация",
      firstProfileValue(
        profile,
        "pricing_revenue_model",
        firstProfileValue(profile, "business_model", "Модель выручки требует данных"),
      ),
    ],
    ["Стадия", firstProfileValue(profile, "stage", "Стадия не определена")],
  ] as const;

  const knownCount = cards.filter(([, value]) => value !== "Недостаточно данных").length;
  const gapCount = profile?.gaps.length ?? 0;
  const contradictionCount = profile?.contradictions.length ?? 0;

  return (
    <section
      aria-labelledby="startup-profile-title"
      className="founder-overview-panel"
    >
      <div className="advisor-section-head">
        <span className="section-kicker">Обзор стартапа</span>
        <h2 id="startup-profile-title">Понятная карта профиля</h2>
        <p>
          Основной интерфейс показывает бизнес-смысл профиля, а технические
          доказательства остаются в операторском контуре.
        </p>
      </div>
      <div className="founder-overview-grid">
        {cards.map(([label, value]) => (
          <article className="founder-overview-card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </div>
      <div className="founder-overview-strip" role="status">
        <span>Заполнено полей: {knownCount}</span>
        <span>Пробелы: {gapCount}</span>
        <span>Противоречия: {contradictionCount}</span>
      </div>
    </section>
  );
}

function firstProfileValue(
  profile: StartupProfileResponse | null,
  fieldName: keyof StartupProfileResponse["fields"],
  fallback: string,
): string {
  return safeFounderText(profile?.fields[fieldName]?.values[0], fallback);
}
