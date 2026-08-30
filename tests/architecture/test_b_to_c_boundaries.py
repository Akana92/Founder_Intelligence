from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path
from uuid import UUID

from due_diligence_agent.presentation.api.context import RequestContext, resolve_request_context


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "src" / "due_diligence_agent"
ARCHITECTURE_DOC = ROOT / "docs" / "architecture" / (
    "2026-08-12-sales-ready-hybrid-boundaries.md"
)
CORE_FORBIDDEN_IMPORT_PREFIXES = (
    "fastapi",
    "starlette",
    "frontend",
    "next",
    "react",
    "due_diligence_agent.presentation",
)
ROUTER_FORBIDDEN_IMPORT_PREFIXES = (
    "due_diligence_agent.adapters",
    "due_diligence_agent.bootstrap",
    "due_diligence_agent.ports.repositories",
)


def test_core_layers_do_not_import_presentation_or_frontend_frameworks() -> None:
    core_roots = (
        PACKAGE_ROOT / "domain",
        PACKAGE_ROOT / "application",
        PACKAGE_ROOT / "workflows",
    )
    offenders = {
        _relative(path): sorted(
            _forbidden_imports(_imported_modules(path), CORE_FORBIDDEN_IMPORT_PREFIXES)
        )
        for path in _python_files(*core_roots)
    }

    assert not {path: imports for path, imports in offenders.items() if imports}


def test_api_routes_do_not_construct_storage_adapters_or_repositories() -> None:
    router_root = PACKAGE_ROOT / "presentation" / "api" / "routers"
    offenders: dict[str, list[str]] = {}

    for path in _python_files(router_root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = _imported_modules_from_tree(tree, package=_package_for(path))
        forbidden = sorted(_forbidden_imports(imports, ROUTER_FORBIDDEN_IMPORT_PREFIXES))
        repository_names = sorted(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
            if alias.name.endswith("Repository")
        )
        if forbidden or repository_names:
            offenders[_relative(path)] = [*forbidden, *repository_names]

    assert not offenders
    system_imports = _imported_modules(router_root / "system.py")
    assert any(module.startswith("due_diligence_agent.application.") for module in system_imports)


def test_profile_b_request_context_has_c_seams_without_claiming_identity() -> None:
    assert [field.name for field in fields(RequestContext)] == [
        "request_id",
        "actor_id",
        "workspace_id",
    ]

    request_id = "123e4567-e89b-12d3-a456-426614174000"
    context = resolve_request_context(
        {
            "X-Request-ID": request_id,
            "X-Actor-ID": "untrusted-founder",
            "X-Workspace-ID": "untrusted-workspace",
            "Authorization": "Bearer untrusted-token",
            "Cookie": "session=untrusted-cookie",
        }
    )

    assert context == RequestContext(
        request_id=UUID(request_id),
        actor_id=None,
        workspace_id=None,
    )


def test_fastapi_and_streamlit_are_sibling_presentation_adapters() -> None:
    presentation_root = PACKAGE_ROOT / "presentation"
    api_root = presentation_root / "api"
    streamlit_root = presentation_root / "streamlit"

    assert api_root.is_dir()
    assert streamlit_root.is_dir()
    assert api_root.parent == streamlit_root.parent == presentation_root

    api_imports = {
        module for path in _python_files(api_root) for module in _imported_modules(path)
    }
    streamlit_imports = {
        module for path in _python_files(streamlit_root) for module in _imported_modules(path)
    }
    assert not any(
        module.startswith("due_diligence_agent.presentation.streamlit")
        for module in api_imports
    )
    assert not any(
        module.startswith("due_diligence_agent.presentation.api")
        for module in streamlit_imports
    )


def test_c_migration_checklist_names_platform_work_without_changing_analytics() -> None:
    text = ARCHITECTURE_DOC.read_text(encoding="utf-8")
    expected_items = (
        "- [ ] Auth provider",
        "- [ ] Principal resolver",
        "- [ ] Tenant policy",
        "- [ ] PostgreSQL persistence",
        "- [ ] Object storage",
        "- [ ] Background job execution",
        "- [ ] Secrets management",
        "- [ ] Backup and restore",
        "- [ ] Rate limits",
        "- [ ] Audit retention",
        "- [ ] SLOs",
    )

    assert "## 8. C migration checklist" in text
    assert all(item in text for item in expected_items)
    assert "Analytics depth does not change between B and C." in text


def test_relative_imports_resolve_to_the_absolute_architecture_boundary() -> None:
    core_tree = ast.parse("from ..presentation.api import app")
    router_tree = ast.parse(
        "from ....adapters.local_storage.repositories import LocalCaseRepository"
    )

    core_imports = _imported_modules_from_tree(
        core_tree,
        package=("due_diligence_agent", "domain"),
    )
    router_imports = _imported_modules_from_tree(
        router_tree,
        package=("due_diligence_agent", "presentation", "api", "routers"),
    )

    assert "due_diligence_agent.presentation.api" in core_imports
    assert "due_diligence_agent.adapters.local_storage.repositories" in router_imports
    assert _forbidden_imports(core_imports, CORE_FORBIDDEN_IMPORT_PREFIXES)
    assert _forbidden_imports(router_imports, ROUTER_FORBIDDEN_IMPORT_PREFIXES)


def _python_files(*roots: Path) -> list[Path]:
    return sorted(path for root in roots for path in root.rglob("*.py"))


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return _imported_modules_from_tree(tree, package=_package_for(path))


def _imported_modules_from_tree(
    tree: ast.AST,
    *,
    package: tuple[str, ...] = (),
) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = _resolve_from_module(node, package)
            if module:
                modules.add(module)
            for alias in node.names:
                if alias.name == "*":
                    continue
                modules.add(f"{module}.{alias.name}" if module else alias.name)
    return modules


def _resolve_from_module(node: ast.ImportFrom, package: tuple[str, ...]) -> str:
    if node.level == 0:
        return node.module or ""

    parent_count = max(len(package) - (node.level - 1), 0)
    parent = package[:parent_count]
    suffix = tuple(node.module.split(".")) if node.module else ()
    return ".".join((*parent, *suffix))


def _package_for(path: Path) -> tuple[str, ...]:
    return tuple(path.relative_to(ROOT / "src").parent.parts)


def _forbidden_imports(modules: set[str], prefixes: tuple[str, ...]) -> set[str]:
    return {
        module
        for module in modules
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)
    }


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()
