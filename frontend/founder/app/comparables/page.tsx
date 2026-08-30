import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowLeft,
  BarChart3,
  Building2,
  ChartNoAxesColumnIncreasing,
  CircleDollarSign,
  Compass,
  Flag,
  PieChart,
  ShieldAlert,
} from "lucide-react";

import { PublicComparablesPanel } from "@/components/public-comparables-panel";

export const metadata: Metadata = {
  title: "Публичные аналоги · Аналитика для основателя",
};

const comparisonLenses = [
  ["Рынок", "Сегменты, драйверы и публичные ориентиры.", PieChart],
  ["Бизнес-модель", "Монетизация, маржинальность и ориентиры экономики продукта.", CircleDollarSign],
  ["Темп роста", "Динамика выручки, капиталоёмкость и качество роста.", ChartNoAxesColumnIncreasing],
  ["Риски", "Концентрация, регуляторика и противоречия в источниках.", ShieldAlert],
] as const;

export default function PublicComparablesPage() {
  return (
    <main className="founder-comparables-console">
      <aside className="comparables-console-sidebar" aria-label="Навигация по публичным аналогам">
        <Link className="comparables-console-brand" href="/">
          <Compass aria-hidden="true" strokeWidth={1.75} />
          <span>Рынок<br />проекта</span>
        </Link>
        <nav>
          <a aria-current="page" href="#market">
            <PieChart aria-hidden="true" strokeWidth={1.75} />
            Рынок
          </a>
          <a href="#lenses">
            <BarChart3 aria-hidden="true" strokeWidth={1.75} />
            Метрики
          </a>
          <a href="#boundary">
            <Flag aria-hidden="true" strokeWidth={1.75} />
            Граница
          </a>
        </nav>
        <Link className="comparables-back-link" href="/">
          <ArrowLeft aria-hidden="true" strokeWidth={1.75} />
          К рабочему столу
        </Link>
      </aside>

      <section className="comparables-console-main" id="market">
        <header className="comparables-console-hero">
          <div>
            <span>Рынок и конкуренты</span>
            <h1>Публичные аналоги как отдельный слой, без операторских трасс.</h1>
            <p>
              Этот экран показывает доступность публичных аналогов и объясняет,
              какие рыночные линзы будут применены после безопасного подключения.
            </p>
          </div>
          <article className="comparables-console-card">
            <Building2 aria-hidden="true" strokeWidth={1.75} />
            <strong>Публичные аналоги</strong>
            <p>Отдельно от технической диагностики и служебных данных.</p>
          </article>
        </header>

        <section className="comparables-status-panel">
          <PublicComparablesPanel />
        </section>

        <section className="comparables-lens-grid" id="lenses" aria-label="Направления сравнения">
          {comparisonLenses.map(([title, detail, Icon], index) => (
            <article key={title}>
              <span>0{index + 1}</span>
              <Icon aria-hidden="true" strokeWidth={1.75} />
              <h2>{title}</h2>
              <p>{detail}</p>
            </article>
          ))}
        </section>

        <aside className="comparables-console-boundary" id="boundary">
          <strong>Честная граница демо</strong>
          <p>
            Если данных или подключения к актуальным источникам недостаточно, экран не подменяет результат
            фиктивным анализом. Он показывает, что можно добавить вручную или
            исследовать публично после явного согласия.
          </p>
        </aside>
      </section>
    </main>
  );
}
