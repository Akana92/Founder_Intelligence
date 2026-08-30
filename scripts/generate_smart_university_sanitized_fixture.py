from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

import fitz

DEFAULT_OUTPUT = (
    Path(__file__).parents[1]
    / "tests"
    / "fixtures"
    / "startup_smart_university_minimized"
    / "smart_university_many_blocks_sanitized.pdf"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the portable sanitized Smart University PDF fixture."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    write_fixture(args.output)


def write_fixture(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()
    document.set_metadata(
        {
            "title": "Smart University sanitized fixture",
            "author": "Capstone N3 tests",
            "subject": "Portable sanitized startup extraction fixture",
            "keywords": "smart-university,sanitized,fixture",
            "creator": "generate_smart_university_sanitized_fixture.py",
            "producer": "PyMuPDF",
            "creationDate": "D:20260826000000Z",
            "modDate": "D:20260826000000Z",
        }
    )

    for page_lines in _chunks(_semantic_lines(), 3):
        _append_page(document, page_lines)
    for page_lines in _chunks(_many_block_lines(), 34):
        _append_page(document, page_lines)

    document.save(path, garbage=4, deflate=True, no_new_id=True)
    document.close()


def _append_page(document: fitz.Document, page_lines: list[str]) -> None:
        page = document.new_page(width=595, height=842)
        text = "\n".join(page_lines)
        page.insert_textbox(
            fitz.Rect(54, 54, 541, 800),
            text,
            fontname="cour",
            fontsize=9,
            lineheight=1.08,
        )


def _semantic_lines() -> list[str]:
    return [
        "Startup Name: Smart University",
        (
            "One Line Description: AI-powered platform for university program "
            "discovery, student matching, admissions workflow, and partner analytics."
        ),
        (
            "Problem: students, parents, education agents, and universities handle "
            "program selection and admissions through fragmented manual workflows."
        ),
        (
            "Solution: AI-powered platform for university program discovery, CRM, "
            "rating, admissions workflow, analytics, and later Housing Management vertical."
        ),
        "ICP: universities and education agents serving cross-border applicants.",
        "Users: students and parents comparing programs and admissions options.",
        "Buyers: university admissions and agent partnership teams.",
        "Geography: Kazakhstan launch, then Central Asia and selected international partners.",
        "Stage: Working product / pre-scale",
        "Business Model: B2B SaaS plus success fees for education partners.",
        (
            "Pricing: Starter 240 000 KZT/month; Growth 690 000 KZT/month; "
            "Enterprise custom KZT/month; implementation fee separate."
        ),
        (
            "Channels: university pilots, education-agent partnerships, webinars, "
            "school counselor referrals, and targeted admissions campaigns."
        ),
        (
            "Competitors: manual spreadsheets, agency CRMs, university portals, "
            "marketplaces, and generic student recruitment tools."
        ),
        (
            "Market Formulas: TAM = students applying abroad * serviceable platform fee; "
            "SAM = target geographies * reachable institutions; SOM = pilots * conversion."
        ),
        (
            "Assumptions: rating methodology combines program fit, budget fit, "
            "admission probability, student outcomes, and appeal workflow."
        ),
        (
            "Assumptions: 35.2M KZT platform round funds platform work."
        ),
        (
            "Assumptions: 8.0M KZT Housing Management pilot is later gated; "
            "35.2M KZT platform round is separate."
        ),
        (
            "Assumptions: revenue and EBITDA are forecasts, not actual performance."
        ),
        (
            "Assumptions: 2027-2031 revenue and EBITDA are forecasts, not actual "
            "performance, and require separate validation."
        ),
        (
            "Weaknesses: legal basis, privacy consent, rating explainability, "
            "anti-fraud controls, appeals, data freshness, and SLA must be proven."
        ),
        (
            "Weaknesses: Housing Management no-go until legal, fire-safety, sanitary, "
            "insurance, landlord, and student-support gates pass."
        ),
        "Strengths: product modules, domain workflow, and partner economics are described.",
    ]


def _many_block_lines() -> list[str]:
    lines: list[str] = []
    for index in range(1, 701):
        note = (
            f"Smart University sanitized source block F{index:03d}: "
            "product, market, stage, roadmap, risk, and implementation notes "
            "for a university technology business plan. "
            "This block contains no private raw owner document text."
        )
        lines.extend(textwrap.wrap(note, width=92))
    return lines


def _chunks(lines: list[str], size: int) -> list[list[str]]:
    return [lines[index : index + size] for index in range(0, len(lines), size)]


if __name__ == "__main__":
    main()
