import type { StartupReportSnapshotResponse } from "@/lib/contracts";
import { buildFounderReportPresentation } from "@/lib/report-presentation";

export function FounderReportPanel({
  reportSnapshot,
}: Readonly<{ reportSnapshot: StartupReportSnapshotResponse | null }>) {
  if (!reportSnapshot) return null;
  const presentation = buildFounderReportPresentation(reportSnapshot);

  return (
    <section aria-labelledby="founder-report-title" className="founder-report">
      <header className="founder-report__header">
        <div>
          <span className="section-kicker">Канонический отчёт</span>
          <h2 id="founder-report-title">Выводы, пробелы и следующие проверки</h2>
          <p>
            Двенадцать основных разделов читаются из одного сохранённого снимка.
            Неподтверждённые сведения остаются пробелами или противоречиями.
          </p>
        </div>
        <div className="founder-report__summary">
          <strong>{presentation.sections.length} разделов</strong>
          <span>Сводка готова для основательской проверки.</span>
          <a href="/admin">Техническая проверка доступна в кабинете администратора</a>
        </div>
      </header>

      <div className="founder-report__grid">
        {presentation.sections.map((section) => (
          <article
            className={`report-section report-section--${section.status.toLowerCase()}`}
            data-report-section={section.key}
            data-report-status={section.status}
            key={section.key}
          >
            <div className="report-section__head">
              <h3>{section.title}</h3>
              <span>{section.statusLabel}</span>
            </div>
            <p>{section.summary}</p>
            {section.items.length > 0 ? (
              <ul className="report-section__items">
                {section.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}
