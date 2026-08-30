/* DIRECTION_CONTRACT
THESIS: A founder uploads the material they already have and receives a clear Russian-language workspace for metrics, risks, market evidence, AI recommendations, and a versioned action plan.
OWN-WORLD: Desktop-only premium graphite workspace, soft pink and plum atmosphere, generous readable typography, rounded glass panels, restrained depth, and explicit evidence states.
STORY: Upload once, confirm the primary profile, deepen the analysis, answer one useful question at a time, accept improvements, and export one consistent report.
FIRST VIEWPORT: Persistent 280px navigation, a calm welcome header, one primary upload action, current-case context, useful outcomes, and the next best step.
FORM: Fourteen approved desktop states at 1440x1000 and 1600x1000; no mobile branch; structure 14, seed key 24519428.
FINISH: Source tests, desktop build, same-viewport visual comparison, an explicit acceptance verdict, and DESIGN.md.
END_DIRECTION_CONTRACT */

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "Аналитика для основателя",
  description:
    "Понятный анализ стартапа с ИИ: метрики, рынок, риски и план улучшений.",
};

export const viewport: Viewport = {
  colorScheme: "dark",
  themeColor: "#080808",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
