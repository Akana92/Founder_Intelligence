from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_reviewer_guide_documents_clone_to_pdf_owner_journey() -> None:
    guide = _read("GITHUB_REVIEWER_GUIDE_RU.md")

    required_fragments = (
        "https://github.com/Akana92/Founder_Intelligence",
        "Copy-Item .env.docker.example .env",
        "OPENAI_API_KEY",
        "LANGSMITH_API_KEY",
        "docker compose up --build",
        "docker compose --profile admin up --build",
        "http://127.0.0.1:3000/",
        "http://127.0.0.1:8501/",
        "Новый анализ",
        "Выбрать файлы",
        "Загрузить проект",
        "Запустить анализ выбранных материалов",
        "Подтвердить и продолжить",
        "Copilot",
        "Ответ",
        "Документ",
        "Онлайн-ресерч",
        "Офлайн-демо",
        "Разрешаю онлайн-ресерч",
        "Запустить онлайн-ресерч",
        "выберите `Публичный поиск`, затем",
        "Gate 2",
        "Gate 3",
        "Gate 4",
        "Принять рекомендацию",
        "Изменить допущения",
        "Сформировать отчёт",
        "Открыть PDF",
        "PDF",
        "HTML",
        "JSON",
        "caseId",
        "Admin",
        "LangSmith",
        "founder_statement",
        "public_benchmark",
        "ai_scenario",
        "source_fact",
        "кеш",
        "Troubleshooting",
        "git ls-files .env",
        "git check-ignore .env",
        "docker compose config --quiet",
    )

    for fragment in required_fragments:
        assert fragment in guide


def test_readme_points_reviewers_to_current_live_docker_contract() -> None:
    readme = _read("README.md")

    assert "GITHUB_REVIEWER_GUIDE_RU.md" in readme
    assert "по умолчанию запускает live workflow" in readme
    assert "FOUNDER_CASE_FIXTURE_MODE=deterministic_offline" in readme
    assert "санитизированный LangSmith exporter" in readme
    assert "DDA_LANGSMITH_TRACING=true" in readme
    assert "Docker-образы и build cache не кладутся в GitHub" in readme


def test_gitignore_excludes_local_runtime_weight_without_hiding_authored_assets() -> None:
    gitignore = _read(".gitignore")

    required_patterns = (
        ".env",
        ".env.*",
        "!.env.example",
        "!.env.docker.example",
        "*.pem",
        "*.key",
        "*id_rsa*",
        "*id_ed25519*",
        "/.codex*/",
        "/.diag*/",
        "/.diagnostic*/",
        "/artifacts/acceptance/",
        "/artifacts/tmp/",
        "/artifacts/test-runs/",
        "/frontend/founder/.next*/",
    )
    for pattern in required_patterns:
        assert pattern in gitignore

    assert "!/artifacts/ui/*.png" in gitignore


def test_frontend_tsconfig_does_not_reference_generated_owner_dist_dirs() -> None:
    tsconfig = json.loads(_read("frontend/founder/tsconfig.json"))

    include = "\n".join(tsconfig["include"])
    assert ".next-owner-" not in include
