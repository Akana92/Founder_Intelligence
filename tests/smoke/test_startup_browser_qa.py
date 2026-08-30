from __future__ import annotations

import subprocess
from pathlib import Path


SCRIPT = Path("scripts/smoke_founder_workspace.ps1")
CAPTURE_HELPER = Path("scripts/capture_founder_screenshots.mjs")
FOUNDER_NEXT_CONFIG = Path("frontend/founder/next.config.ts")


def test_browser_qa_contract_uses_same_origin_urls_and_fixed_artifact_paths() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "http://127.0.0.1:3000/" in text
    assert "http://127.0.0.1:8501/" in text
    assert "http://127.0.0.1:3000/admin" not in text
    assert "http://127.0.0.1:3000/comparables" in text
    assert "http://127.0.0.1:8000/docs" in text
    assert "artifacts/ui/founder-desktop.png" in text
    assert "artifacts/ui/founder-desktop-states" in text
    assert "artifacts/ui/founder-mobile.png" not in text
    assert "scripts/capture_founder_screenshots.mjs" in text
    assert "FOUNDER_API_BASE_URL" in text
    assert "localhost:" not in text


def test_browser_qa_can_isolate_runtime_screenshots_from_committed_baselines() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "[string] $ScreenshotDir" in text
    assert "Resolve-FounderScreenshotRoot" in text
    assert "$ResolvedScreenshotRoot" in text


def test_desktop_state_capture_uses_exact_cdp_viewport_and_rejects_horizontal_overflow() -> None:
    helper = CAPTURE_HELPER.read_text(encoding="utf-8")

    assert "Emulation.setDeviceMetricsOverride" in helper
    assert "document.documentElement.scrollWidth" in helper
    assert "horizontal_overflow" in helper
    assert "width: 1440" in helper
    assert "height: 1000" in helper
    assert "CANONICAL_DESKTOP_STATE_SCREENSHOTS" in helper
    assert "founder_14_desktop_states_written" in helper


def test_cdp_capture_uses_the_current_scroll_offset_for_visible_report_pixels() -> None:
    helper = CAPTURE_HELPER.read_text(encoding="utf-8")

    assert "scrollX: window.scrollX" in helper
    assert "scrollY: window.scrollY" in helper
    assert "x: geometry.scrollX" in helper
    assert "y: geometry.scrollY" in helper


def test_offline_browser_qa_drives_the_real_founder_gtm_panel() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    helper = CAPTURE_HELPER.read_text(encoding="utf-8")

    assert "$env:FOUNDER_CASE_FIXTURE_MODE" in script
    assert '"--fixture=$FixturePath"' in script
    assert '"--desktop-states=$desktopStatesPath"' in script
    assert '"--require-desktop-state-suite=true"' in script
    assert '"--admin-url=$AdminBaseUrl/"' in script
    assert "DOM.setFileInputFiles" in helper
    assert "startup-gtm-title" in helper
    assert "gtm_panel_contract_mismatch" in helper
    assert "founder_gtm_panel_visible" in helper


def test_offline_browser_qa_renders_the_canonical_founder_profile() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    helper = CAPTURE_HELPER.read_text(encoding="utf-8")

    assert '/profile"' in script
    assert "smoke_profile_contract_mismatch" in script
    assert "startup-profile-title" in helper
    assert ".startup-profile__grid .profile-field" in helper
    assert "profile_panel_contract_mismatch" in helper
    assert "founder_profile_panel_visible" in helper


def test_offline_browser_qa_renders_exact_canonical_report_sections() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    helper = CAPTURE_HELPER.read_text(encoding="utf-8")

    assert '/report/json"' in script
    assert "smoke_report_contract_mismatch" in script
    assert "founder-report-title" in helper
    assert "[data-report-section]" in helper
    assert "report_panel_contract_mismatch" in helper
    assert "founder_report_panel_visible" in helper
    assert "sections=12" in helper
    assert "validateFounderSafeReportPayload" in helper
    assert "validateReportMetadata" in helper
    assert "reportHtmlText.includes(parsedJson.id)" not in helper


def test_offline_browser_qa_renders_report_derived_readiness_and_deep_questions() -> None:
    helper = CAPTURE_HELPER.read_text(encoding="utf-8")

    assert "founder-readiness-title" in helper
    assert "[data-analysis-stage]" in helper
    assert "[data-analysis-status]" in helper
    assert "[data-readiness-dimension]" in helper
    assert "[data-deep-section]" in helper
    assert ".founder-readiness__snapshot" in helper
    assert ".founder-readiness__warning" in helper
    assert "readiness_panel_contract_mismatch" in helper
    assert "founder_readiness_panel_visible" in helper
    assert "questions=" in helper


def test_offline_browser_qa_renders_report_derived_charts() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    helper = CAPTURE_HELPER.read_text(encoding="utf-8")

    assert '/report/html"' in script
    assert "smoke_report_html_charts_missing" in script
    assert "smoke_report_html_embedded_chart_count" in script
    assert "smoke_report_html_external_image" in script
    assert "founder-charts-title" in helper
    assert "[data-founder-chart]" in helper
    assert "[data-chart-key]" in helper
    assert "[data-chart-point]" in helper
    assert "[data-chart-lineage]" in helper
    assert "charts_panel_contract_mismatch" in helper
    assert "founder_charts_panel_visible" in helper
    assert "founder_charts_panel_in_view" in helper
    assert "founder_chart_point_in_view" in helper
    assert 'panel?.querySelectorAll("[data-founder-chart][data-chart-key]")' in helper
    assert 'document.querySelectorAll("[data-founder-chart][data-chart-key]")' not in helper
    assert "confirmed_metrics" in helper
    assert "readiness_coverage" in helper
    assert "report_coverage" in helper


def test_pdf_browser_qa_requires_truthful_available_charts_without_weakening_csv() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    helper = CAPTURE_HELPER.read_text(encoding="utf-8")

    assert "$expectedChartKeys = if ($RequirePdfUploadJourney)" in script
    assert '@("readiness_coverage", "report_coverage")' in script
    assert '@("confirmed_metrics", "readiness_coverage", "report_coverage")' in script
    assert "const requiredChartKeys = pdfUploadJourney" in helper
    assert '["readiness_coverage", "report_coverage"]' in helper
    assert '["confirmed_metrics", "readiness_coverage", "report_coverage"]' in helper
    assert "driveFounderGtmJourney(client, sessionId, fixturePath, pdfUploadJourney)" in helper


def test_pdf_browser_qa_accepts_explicit_pdf_fixture_not_a_hardcoded_case() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    helper = CAPTURE_HELPER.read_text(encoding="utf-8")

    assert "FounderCanonicalPdfFixture" not in script
    assert "CANONICAL_PDF_FIXTURE" not in helper
    assert "pdf_required_fixture_not_pdf" in script
    assert "browser_evidence_pdf_fixture_not_pdf" in helper
    assert "browser_evidence_pdf_fixture_not_canonical" not in helper


def test_desktop_state_capture_exercises_invalid_then_configured_advisor_answer() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    helper = CAPTURE_HELPER.read_text(encoding="utf-8")

    assert "[string] $AdvisorAnswer" in script
    assert "[string] $InvalidAdvisorAnswer = \"60%\"" in script
    assert '"--advisor-answer=$AdvisorAnswer"' in script
    assert '"--invalid-advisor-answer=$InvalidAdvisorAnswer"' in script
    assert "const advisorAnswer = options[\"advisor-answer\"]" in helper
    assert "const invalidAdvisorAnswer =" in helper
    assert "setManualAdvisorAnswer(invalidAdvisorAnswer)" in helper
    assert "assertManualAdvisorAnswerRejected()" in helper
    assert "founder_advisor_invalid_answer_rejected_inline" in helper
    assert "setManualAdvisorAnswer(advisorAnswer)" in helper


def test_cdp_browser_qa_blocks_and_records_external_page_requests() -> None:
    helper = CAPTURE_HELPER.read_text(encoding="utf-8")

    assert '"--disable-extensions"' in helper
    assert '"Network.enable"' in helper
    assert '"Fetch.enable"' in helper
    assert 'client.on("Fetch.requestPaused"' in helper
    assert 'client.on("Network.requestWillBeSent"' in helper
    assert '"Fetch.failRequest"' in helper
    assert "browser_network_violation" in helper
    assert "browser_network_no_egress" in helper


def test_cdp_browser_qa_is_strict_by_default_and_bounds_opt_in_injection_origin() -> None:
    helper = CAPTURE_HELPER.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")

    assert "assertServedMarkupHasNoExternalScripts" in helper
    assert "served_html_external_script" in helper
    assert '"Fetch.fulfillRequest"' not in helper
    assert '"Network.setUserAgentOverride"' in helper
    assert '"FounderOfflineSmoke/1.0"' in helper
    assert "allow-blocked-parser-script-origin" in helper
    assert "isExplicitlyQuarantinedParserInjection" in helper
    assert "if (!allowedBlockedParserScriptOrigins) return false" in helper
    assert "allowedBlockedParserScriptOrigins.has(safeRequestOrigin(requestUrl))" in helper
    assert "browser_network_injection_blocked" in helper
    assert "blockedExternalRequests" in helper
    assert "[string] $BlockedBrowserInjectionOrigin" in script
    assert "$BlockedBrowserInjectionOrigin -split" in script
    assert '"--allow-blocked-parser-script-origin=$($normalizedOrigins -join' in script


def test_founder_ui_csp_rejects_injected_external_scripts_and_frames() -> None:
    config = FOUNDER_NEXT_CONFIG.read_text(encoding="utf-8")

    assert "devIndicators: false" in config
    assert '"Content-Security-Policy"' in config
    assert "default-src 'self'" in config
    assert "script-src 'self'" in config
    assert "object-src 'none'" in config
    assert "frame-ancestors 'none'" in config


def test_offline_browser_qa_approves_gate4_and_reads_the_visible_pdf_artifact() -> None:
    helper = CAPTURE_HELPER.read_text(encoding="utf-8")

    assert 'buttonExpression("Зафиксировать версию", "ready")' in helper
    assert 'buttonExpression("Зафиксировать версию", "click")' in helper
    assert ".workflow-artifacts" in helper
    assert "PDF после фиксации" in helper
    assert "gate4_artifact_contract_mismatch" in helper
    assert "founder_gate4_pdf_ready" in helper
    assert "approvedCaseId !== draftCaseId" in helper
    assert "MAX_SMOKE_PDF_BYTES" in helper
    assert 'headers.get("content-length")' in helper
    assert "response.body?.getReader()" in helper
    assert "reader.cancel()" in helper
    assert 'Accept: "application/pdf"' in helper
    assert 'headers.get("content-type")' in helper
    assert "[37, 80, 68, 70]" in helper
    assert 'document.documentElement.style.scrollBehavior = "auto"' in helper
    assert "founder_gate4_panel_in_view" in helper


def test_offline_gtm_browser_qa_fails_closed_without_a_cdp_browser() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert "founder_gtm_journey_requires_cdp_browser" in script


def test_cdp_capture_helper_has_valid_javascript_syntax() -> None:
    result = subprocess.run(
        ["node", "--check", str(CAPTURE_HELPER)],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr


def test_cdp_capture_cleanup_retries_transient_windows_file_locks() -> None:
    helper = CAPTURE_HELPER.read_text(encoding="utf-8")

    assert "maxRetries: 10" in helper
    assert "retryDelay: 100" in helper


def test_screenshot_capture_request_fails_clearly_when_driver_is_unavailable() -> None:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Mode",
            "offline-fixture",
            "-CaptureScreenshots",
            "-ValidateOnly",
            "-BrowserCommand",
            str(Path("missing-browser-driver").resolve()),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 2
    assert "screenshot_capture_unavailable" in result.stderr
