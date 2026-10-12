"""Règle d'architecture (§13) : le domaine est du Python pur, testable sans IA ni base."""

import ast
from pathlib import Path

DOMAIN = Path(__file__).resolve().parents[2] / "app" / "domain"
FORBIDDEN = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "asyncpg",
    "anthropic",
    "httpx",
    "app.api",
    "app.db",
)


def test_domain_has_no_infrastructure_imports() -> None:
    offenders = []
    for path in DOMAIN.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            offenders += [
                f"{path.relative_to(DOMAIN)}: {m}"
                for m in modules
                if m.split(".")[0] in FORBIDDEN or m.startswith(FORBIDDEN)
            ]
    assert offenders == []
