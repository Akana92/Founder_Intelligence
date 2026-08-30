import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8");
const layout = readFileSync(new URL("./layout.tsx", import.meta.url), "utf8");
const shell = readFileSync(
  new URL("../components/founder-shell.tsx", import.meta.url),
  "utf8",
);
const analysisCss = readFileSync(
  new URL("../components/founder-analysis-pages.module.css", import.meta.url),
  "utf8",
);
const strategyCss = readFileSync(
  new URL("../components/founder-strategy-pages.module.css", import.meta.url),
  "utf8",
);
const advisorCss = readFileSync(
  new URL("../components/founder-advisor-pages.module.css", import.meta.url),
  "utf8",
);
const copilotCss = readFileSync(
  new URL("../components/case-copilot-panel.module.css", import.meta.url),
  "utf8",
);
const uploadCss = readFileSync(
  new URL("../components/upload-entry.module.css", import.meta.url),
  "utf8",
);

test("desktop shell uses the full viewport and reserves a fluid Copilot rail", () => {
  assert.match(
    css,
    /\.founder-dashboard-shell\s*\{[\s\S]*?grid-template-columns:\s*var\(--fi-sidebar-width\) minmax\(0,\s*1fr\) clamp\(24rem,\s*26vw,\s*32rem\);[\s\S]*?gap:\s*var\(--fi-content-gap\);[\s\S]*?max-width:\s*none;[\s\S]*?padding:\s*8px 28px 8px 8px;[\s\S]*?width:\s*100%;/u,
  );
  assert.doesNotMatch(css, /\.founder-dashboard-shell\s*\{[\s\S]*?max-width:\s*var\(--fi-shell-max-width\)/u);
  assert.match(
    css,
    /\.founder-sidebar\s*\{[\s\S]*?border-radius:\s*var\(--fi-radius-shell\);[\s\S]*?min-height:\s*calc\(100vh - 16px\);[\s\S]*?top:\s*8px;/u,
  );
  assert.match(
    css,
    /\.founder-dashboard-main\s*\{[\s\S]*?align-content:\s*start;[\s\S]*?padding:\s*28px 0 16px;/u,
  );
  assert.doesNotMatch(css, /body\s*\{[\s\S]*?min-width:\s*1440px;/u);
  assert.match(css, /body\s*\{[\s\S]*?overflow-x:\s*clip;/u);
  assert.match(
    css,
    /\.founder-dashboard-main\s*\{[\s\S]*?min-width:\s*0;[\s\S]*?overflow-x:\s*clip;/u,
  );
});

test("open Copilot shell becomes a drawer at 1440 and a fluid rail at 1920", () => {
  const viewportWidth = 1440;
  const sidebarWidth = 232;
  const shellHorizontalPadding = 8 + 28;
  const shellGaps = 24;
  const drawerMainWidth = viewportWidth - shellHorizontalPadding - shellGaps - sidebarWidth;

  assert.equal(drawerMainWidth, 1148);
  assert.match(css, /\.founder-dashboard-shell\s*\{[\s\S]*?padding:\s*8px 28px 8px 8px;/u);
  assert.match(copilotCss, /\.panel\s*\{[\s\S]*?inline-size:\s*100%;/u);
  assert.match(copilotCss, /@media\s*\(max-width:\s*100rem\)\s*\{[\s\S]*?\.shellWithCopilot\s*\{[\s\S]*?grid-template-columns:\s*var\(--fi-sidebar-width\) minmax\(0,\s*1fr\);/u);
  assert.match(copilotCss, /@media\s*\(max-width:\s*100rem\)[\s\S]*?\.panel\s*\{[\s\S]*?width:\s*min\(420px,\s*calc\(100vw - 32px\)\);/u);
  assert.doesNotMatch(copilotCss, /\.rail\s*\{/u);
  assert.doesNotMatch(copilotCss, /\.drawer\s*\{/u);
  assert.match(css, /\.dashboard-bottom-row > \.dashboard-card\s*\{[\s\S]*?min-height:\s*382px;/u);
  assert.match(
    copilotCss,
    /\.shellWithCopilot\s+:global\(\.dashboard-bottom-row\)\s*\{[\s\S]*?gap:\s*12px;[\s\S]*?grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\);/u,
  );
  assert.match(
    copilotCss,
    /\.shellWithCopilot\s+:global\(\.dashboard-bottom-row > \.dashboard-card\)\s*\{[\s\S]*?min-height:\s*0;[\s\S]*?overflow:\s*visible;[\s\S]*?padding:\s*16px;/u,
  );
  const insightDetailRule = copilotCss.match(
    /\.shellWithCopilot\s+:global\(\.dashboard-card--insights li p\)\s*\{([\s\S]*?)\}/u,
  );
  assert.ok(insightDetailRule?.[1]);
  assert.doesNotMatch(insightDetailRule[1], /display:\s*none;/u);
});

test("the 1440 drawer dims and blocks the workspace while the wide rail stays inline", () => {
  const panel = readFileSync(
    new URL("../components/case-copilot-panel.tsx", import.meta.url),
    "utf8",
  );

  assert.match(panel, /className=\{styles\.drawerBackdrop\}/u);
  assert.match(panel, /aria-label="Закрыть помощника и вернуться к рабочей области"/u);
  assert.match(copilotCss, /\.drawerBackdrop\s*\{[\s\S]*?display:\s*none;/u);
  assert.match(
    copilotCss,
    /@media\s*\(max-width:\s*100rem\)[\s\S]*?\.drawerBackdrop\s*\{[\s\S]*?display:\s*block;[\s\S]*?inset:\s*0;[\s\S]*?position:\s*fixed;[\s\S]*?z-index:\s*39;/u,
  );
});

test("Case Copilot starts closed so the workspace is readable before an explicit owner action", () => {
  assert.match(shell, /const \[caseCopilotOpen, setCaseCopilotOpen\] = useState\(false\);/u);
  assert.match(shell, /function openCaseCopilot\(\)\s*\{[\s\S]*?setCaseCopilotOpen\(true\);/u);
});

test("metric cards keep natural height instead of stretching to pixel-locked rows", () => {
  assert.match(
    analysisCss,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.metricCardsTop\s*\{[\s\S]*?align-items:\s*start;/u,
  );
  assert.match(
    analysisCss,
    /\.page\[data-founder-analysis-page="metrics"\]\s+\.metricCard\s*\{[\s\S]*?grid-template-rows:\s*none;[\s\S]*?min-height:\s*auto;/u,
  );
});

test("closed Copilot keeps state mounted without intercepting the main workspace", () => {
  const drawerRuleStart = copilotCss.search(/@media\s*\(max-width:\s*100rem\)[\s\S]*?\.panel\s*\{/u);
  const closedRuleStart = copilotCss.search(/\.panelClosed\s*\{/u);

  assert.ok(drawerRuleStart >= 0);
  assert.ok(closedRuleStart > drawerRuleStart);
  assert.match(
    copilotCss,
    /\.shellCopilotClosed\s*\{[\s\S]*?grid-template-columns:\s*var\(--fi-sidebar-width\) minmax\(0,\s*1fr\);[\s\S]*?padding-right:\s*8px;/u,
  );
  assert.match(
    copilotCss,
    /@media\s*\(min-width:\s*64rem\)[\s\S]*?\.shellCopilotClosed\s*\{[\s\S]*?padding-right:\s*76px;/u,
  );
  assert.match(
    copilotCss,
    /\.panelClosed\s*\{[\s\S]*?display:\s*grid;[\s\S]*?overflow:\s*hidden;[\s\S]*?position:\s*fixed;[\s\S]*?right:\s*16px;[\s\S]*?top:\s*16px;[\s\S]*?width:\s*52px;[\s\S]*?z-index:\s*40;/u,
  );
  assert.match(copilotCss, /\.panelClosed\s*>\s*:not\(\.panelHeader\)\s*\{[\s\S]*?display:\s*none;/u);
  assert.match(copilotCss, /\.panelClosed\s+\.panelHeader\s*\{[\s\S]*?grid-template-columns:\s*1fr;[\s\S]*?place-items:\s*center;/u);
  assert.match(copilotCss, /\.panelClosed\s+\.panelHeader\s+div\s*\{[\s\S]*?display:\s*none;/u);
  assert.match(copilotCss, /\.panelClosed\s+\.panelHeader\s+button\s*\{[\s\S]*?justify-self:\s*center;/u);
});

test("open Copilot dashboard avoids false-fit clipping in the 1440x1000 browser gate", () => {
  const bottomCardRule = copilotCss.match(
    /\.shellWithCopilot\s+:global\(\.dashboard-bottom-row > \.dashboard-card\)\s*\{([\s\S]*?)\}/u,
  );

  const bottomCardBody = bottomCardRule?.[1] ?? "";
  assert.ok(bottomCardBody);
  assert.doesNotMatch(bottomCardBody, /\bheight:\s*\d+px;/u);
  assert.doesNotMatch(bottomCardBody, /\boverflow:\s*hidden;/u);
  assert.match(bottomCardBody, /\bmin-height:\s*0;/u);
  assert.match(bottomCardBody, /\boverflow:\s*visible;/u);

  const compactMainRule = copilotCss.match(
    /\.shellWithCopilot\s+:global\(\.founder-dashboard-main\)\s*\{([\s\S]*?)\}/u,
  );

  const compactMainBody = compactMainRule?.[1] ?? "";
  assert.ok(compactMainBody);
  assert.match(compactMainBody, /\bgap:\s*12px;/u);
  assert.match(compactMainBody, /\bpadding:\s*14px 0 8px;/u);
  const panelRule = copilotCss.match(/\.panel\s*\{([\s\S]*?)\}/u);
  const panelBody = panelRule?.[1] ?? "";
  assert.ok(panelBody);
  assert.doesNotMatch(panelBody, /\bmax-height:/u);
  assert.doesNotMatch(panelBody, /\boverflow:\s*auto;/u);
  assert.match(copilotCss, /@media\s*\(max-width:\s*100rem\)[\s\S]*?\.panel\s*\{[\s\S]*?max-height:\s*calc\(100vh - 32px\);[\s\S]*?overflow:\s*auto;/u);
});

test("open Copilot dashboard compacts natural content before the browser gate", () => {
  assert.match(
    copilotCss,
    /\.shellWithCopilot\s+:global\(\.founder-dashboard-title-row h1\)\s*\{[\s\S]*?font-size:\s*34px;/u,
  );
  assert.match(
    copilotCss,
    /\.shellWithCopilot\s+:global\(\.founder-ask-bar\)\s*\{[\s\S]*?min-height:\s*54px;/u,
  );
  assert.match(
    copilotCss,
    /\.shellWithCopilot\s+:global\(\.dashboard-grid\)\s*\{[\s\S]*?gap:\s*12px;/u,
  );
  assert.match(
    copilotCss,
    /\.shellWithCopilot\s+:global\(\.dashboard-card--project\)\s*\{[\s\S]*?gap:\s*14px;[\s\S]*?min-height:\s*300px;/u,
  );
  assert.match(
    copilotCss,
    /\.shellWithCopilot\s+:global\(\.project-outcomes\)\s*\{[\s\S]*?gap:\s*7px;[\s\S]*?padding:\s*12px 0 0;/u,
  );
  assert.match(
    copilotCss,
    /\.shellWithCopilot\s+:global\(\.dashboard-card--insights li p\)\s*\{[\s\S]*?font-size:\s*12px;[\s\S]*?line-height:\s*1\.3;/u,
  );
  assert.doesNotMatch(copilotCss, /-webkit-line-clamp/u);
});

test("analysis surfaces keep the approved 1440x1000 vertical rhythm", () => {
  assert.match(analysisCss, /\.page\s*\{[\s\S]*?gap:\s*14px;/u);
  assert.match(
    analysisCss,
    /\.hero\s*\{[\s\S]*?gap:\s*12px;[\s\S]*?min-height:\s*50px;[\s\S]*?padding:\s*0 4px;/u,
  );
  assert.match(
    analysisCss,
    /\.hero h1\s*\{[\s\S]*?font-size:\s*clamp\(28px, 2\.15vw, 38px\);[\s\S]*?margin:\s*0 0 6px;/u,
  );
  assert.match(analysisCss, /\.hero p\s*\{[\s\S]*?font-size:\s*15px;/u);
  assert.match(
    analysisCss,
    /\.progressRail\s*\{[\s\S]*?min-height:\s*96px;[\s\S]*?padding:\s*12px 30px;/u,
  );
  assert.match(
    analysisCss,
    /\.agentPanel,[\s\S]*?\.financialProblem\s*\{[\s\S]*?padding:\s*20px;/u,
  );
});

test("dashboard overrides legacy cyan controls with the approved pink palette", () => {
  assert.match(
    css,
    /\.founder-dashboard-shell \.button--primary\s*\{[\s\S]*?linear-gradient\(180deg, #ffa7d5, #f48bc1\)[\s\S]*?color:\s*#160912;/u,
  );
  assert.match(
    css,
    /\.founder-dashboard-shell \.button--secondary\s*\{[\s\S]*?border:\s*1px solid rgba\(245, 161, 207, 0\.3\);[\s\S]*?color:\s*var\(--dash-pink\);/u,
  );
});

test("global shell no longer exposes the old cyan terminal dossier layer", () => {
  assert.doesNotMatch(
    `${layout}\n${css}`,
    /\bdossier\b|\bcyan\b|no ornamental glow|one-pixel rules|structure 7/iu,
  );
  assert.doesNotMatch(
    css,
    /--ink-|--cyan(?:-deep)?\b|\.analysis-dossier\b|\.analysis-board\b|\.analysis-horizon\b|\.domain-cell\b|\.case-brief\b|\.honesty-strip\b|\.workflow-dashboard-card\b/u,
  );
  assert.doesNotMatch(css, /#25d7f3\b|#0bb6d0\b|#8cecff\b|rgb\(37 215 243/u);
});

test("all 14 founder states share one desktop-only design token system", () => {
  for (const token of [
    "--fi-bg: #080808",
    "--fi-surface: rgba(24, 22, 25, 0.86)",
    "--fi-border: rgba(255, 255, 255, 0.14)",
    "--fi-text: #fbf7f9",
    "--fi-muted: #b8b0b5",
    "--fi-accent: #f5a1cf",
    "--fi-success: #8bd98c",
    "--fi-warning: #ecc257",
    "--fi-danger: #ff747a",
    "--fi-sidebar-width: 232px",
    "--fi-content-gap: 24px",
    "--fi-radius-shell: 20px",
    "--fi-radius-card: 16px",
    "--fi-card-blur: 24px",
  ]) {
    assert.match(css, new RegExp(token.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "u"));
  }

  for (const scopedCss of [analysisCss, strategyCss, advisorCss, uploadCss]) {
    assert.match(scopedCss, /var\(--fi-accent\)/u);
    assert.match(scopedCss, /var\(--fi-border\)/u);
  }

  for (const desktopOnlyCss of [analysisCss, advisorCss, uploadCss]) {
    assert.doesNotMatch(desktopOnlyCss, /@media\s*\(max-width:/u);
  }
  assert.match(
    strategyCss,
    /@media\s*\(max-width:\s*720px\)[\s\S]*?\.researchConsentBackdrop[\s\S]*?\.researchConsentDialog/u,
  );
  assert.equal(
    strategyCss.match(/@media\s*\(max-width:/gu)?.length,
    1,
    "only the consent dialog may use the narrow responsive override",
  );

  assert.doesNotMatch(css, /@media\s*\(max-width:/u);
  assert.doesNotMatch(shell, /Алексей|Welcome,|Nadia/iu);
  assert.match(shell, /<h1>Добро пожаловать<\/h1>/u);
});

test("empty dashboard explains the next value without synthetic project results", () => {
  assert.doesNotMatch(shell, /Последний проект|Недавние проекты/u);
  assert.match(
    shell,
    /Добавьте материалы[^<]*я смогу уточнить[^<]*рассчитать[^<]*риски/u,
  );
  assert.match(shell, /после вашего разрешения[^<]*публичные источники/u);
  assert.doesNotMatch(
    shell,
    /Уверенность AI<\/dt>|Готовность<\/dt>|Проект появится после загрузки/u,
  );
  assert.match(
    shell,
    /<ul className="project-outcomes">[\s\S]*?<li><span><strong>Продукт и клиент<\/strong>/u,
  );
});

test("premium cards and controls use the approved type, depth, and action hierarchy", () => {
  assert.match(
    css,
    /--fi-font:\s*"Segoe UI Variable",\s*"Aptos",\s*"Segoe UI",\s*sans-serif/u,
  );
  assert.match(css, /body\s*\{[\s\S]*?font-size:\s*14px;/u);
  assert.match(
    css,
    /\.founder-sidebar__nav button,[\s\S]*?font-size:\s*16px;[\s\S]*?font-weight:\s*520;[\s\S]*?min-height:\s*50px;/u,
  );
  assert.match(
    css,
    /\.dashboard-card\s*\{[\s\S]*?backdrop-filter:\s*blur\(var\(--fi-card-blur\)\) saturate\(1\.12\);[\s\S]*?border-radius:\s*var\(--fi-radius-card\);[\s\S]*?box-shadow:\s*var\(--fi-shadow-card\);[\s\S]*?padding:\s*20px;/u,
  );
  assert.match(
    css,
    /\.founder-dashboard-shell \.button--primary\s*\{[\s\S]*?min-height:\s*48px;/u,
  );
  assert.match(css, /\.founder-ask-bar\s*\{[\s\S]*?min-height:\s*64px;/u);
  assert.match(css, /\.dashboard-card--project\s*\{[\s\S]*?min-height:\s*340px;/u);
});

test("data room preserves the approved full-height composition even before files exist", () => {
  assert.match(
    css,
    /\.data-room-layout\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\) minmax\(480px, 0\.71fr\);/u,
  );
  assert.match(
    css,
    /\.data-room-card\s*\{[\s\S]*?min-height:\s*calc\(100vh - 168px\);/u,
  );
  assert.match(
    css,
    /\.coverage-card\s*\{[\s\S]*?min-height:\s*352px;/u,
  );
  assert.match(
    css,
    /\.privacy-card\s*\{[\s\S]*?min-height:\s*356px;/u,
  );
});
