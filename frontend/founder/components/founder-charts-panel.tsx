import {
  buildFounderChartsPresentation,
  founderChartBarWidth,
} from "@/lib/chart-presentation";
import type { StartupReportSnapshotResponse } from "@/lib/contracts";

export function FounderChartsPanel({
  reportSnapshot,
}: Readonly<{ reportSnapshot: StartupReportSnapshotResponse | null }>) {
  const charts = buildFounderChartsPresentation(reportSnapshot);
  if (!reportSnapshot) return null;
  const maxValueByChart = new Map(
    charts
      .filter((chart) => chart.scale === "shared")
      .map((chart) => [
        chart.key,
        Math.max(...chart.points.map((point) => point.value), 1),
      ]),
  );

  return (
    <section className="founder-charts" aria-labelledby="founder-charts-title">
      <div className="founder-charts__head">
        <span className="section-kicker">Отчет</span>
        <h2 id="founder-charts-title">Визуализация данных из документов</h2>
        <p>
          Графики построены из канонического снимка JSON/HTML/PDF. Значения
          метрик, заявленных в документах, сохраняют исходные единицы измерения, поэтому их
          нужно читать независимо друг от друга; внутренние служебные строки,
          операторская телеметрия, промпты, токены и приватные пути не выводятся.
        </p>
        <a href="/admin">Техническая проверка доступна в кабинете администратора</a>
      </div>
      {charts.length === 0 ? (
        <div className="founder-charts__empty" role="status">
          Графики появятся после получения согласованного снимка отчета.
        </div>
      ) : (
        <div className="founder-charts__grid">
          {charts.map((chart) => {
            const maxValue = maxValueByChart.get(chart.key) ?? 1;
            return (
              <article
                className="founder-chart"
                data-chart-key={chart.key}
                data-chart-scale={chart.scale}
                data-founder-chart
                key={chart.key}
              >
                <div className="founder-chart__title">
                  <h3>{chart.title}</h3>
                  <p>{chart.description}</p>
                  {chart.scale === "independent" ? (
                    <p className="founder-chart__scale-note">
                      Разные единицы показаны без общей сравнительной шкалы.
                    </p>
                  ) : null}
                </div>
                <ul className="founder-chart__points">
                  {chart.points.map((point) => {
                    const width = founderChartBarWidth(point.value, maxValue);
                    return (
                      <li data-chart-point={point.key} key={point.key}>
                        <span className="founder-chart__label">{point.label}</span>
                        {chart.scale === "shared" ? (
                          <span className="founder-chart__bar" aria-hidden="true">
                            <span style={{ width }} />
                          </span>
                        ) : null}
                        <strong>{point.displayValue}</strong>
                        <small>{point.detail}</small>
                      </li>
                    );
                  })}
                </ul>
                <p className="founder-chart__lineage">
                  Техническое происхождение графика доступно в кабинете
                  администратора.
                </p>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
