"""Séances de référence (§5.79) : non-régression pédagogique du moteur.

Pour chaque leçon de référence (`reference_lessons/`) et trois situations (première séance,
révision mêlée, notions fragiles), le moteur compose une séance, graine fixée. Le résultat, lisible
(bloc, jeu, difficulté, notions, raison), est enregistré dans `tests/golden/reference_sessions.txt`.
Le test `tests/domain/test_reference_sessions.py` recompose et compare : une modification du moteur
qui change une séance fait échouer le test, avec la différence en clair. Si le changement est
voulu, on la relit, puis :

    uv run python -m app.tools.reference_sessions --update

et le fichier modifié passe dans la PR, où la différence se relit comme le reste du code.
"""

import argparse
import difflib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.domain.activities.registry import default_registry
from app.domain.composer import SessionComposer, SessionPlan
from app.domain.decisions import describe
from app.domain.knowledge import KnowledgeUnit
from app.domain.mastery import Mastery
from app.domain.rules import ENGINE_VERSION
from app.domain.validation import validate_analysis, validate_material

ROOT = Path(__file__).resolve().parents[2]
LESSONS = ROOT / "reference_lessons"
GOLDEN = ROOT / "tests" / "golden" / "reference_sessions.txt"
NOW = datetime(2026, 11, 9, 17, 0, tzinfo=UTC)
ALL_LEVELS = frozenset({1, 2, 3, 4, 5})


def _units(path: Path) -> list[KnowledgeUnit]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    analysis = validate_analysis(raw["analysis"], raw["ocr_text"]).analysis
    return [
        KnowledgeUnit(item=item, material=validate_material(item, raw["material"][item.id]).material)
        for item in analysis.knowledge
    ]


def _mastery(score: int, due_in_days: float) -> Mastery:
    return Mastery(
        score=score,
        box=2,
        next_review_at=NOW + timedelta(days=due_in_days),
        last_practiced_at=NOW - timedelta(days=3),
        levels=frozenset({1, 2}) if score < 80 else ALL_LEVELS,
    )


def _scenarios(units: list[KnowledgeUnit]) -> dict[str, dict[str, Mastery]]:
    mixed_scores = (30, 65, 95)
    return {
        "première séance": {},
        "révision mêlée": {
            u.id: _mastery(mixed_scores[i % 3], -1 if i % 3 else -2) for i, u in enumerate(units)
        },
        "notions fragiles": {u.id: _mastery(40, -1) for u in units},
    }


def _lines(plan: SessionPlan) -> list[str]:
    lines = [f"  durée estimée {round(plan.estimated_duration_s / 60)} min, express={plan.express}"]
    for item in plan.items:
        a = item.activity
        lines.append(
            f"  {item.position:>2} {item.block.value:<11} {a.type.value:<18} d{a.difficulty} "
            f"{','.join(a.knowledge_ids):<18} {describe(item.reason) or '-'}"
        )
    return lines


def render() -> str:
    """Toutes les séances de référence, dans un texte stable (même code → même texte)."""
    registry = default_registry()
    out = [f"# Séances de référence — moteur {ENGINE_VERSION}", ""]
    for path in sorted(LESSONS.glob("*.json")):
        units = _units(path)
        for seed, (name, masteries) in enumerate(_scenarios(units).items(), 1):
            plan = SessionComposer(registry).compose(units, masteries, NOW, seed=seed)
            out += [f"## {path.stem} — {name}", *_lines(plan), ""]
    return "\n".join(out).rstrip("\n")


def difference(expected: str, actual: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            expected.splitlines(), actual.splitlines(), "enregistré", "moteur actuel", lineterm="", n=1
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--update", action="store_true", help="enregistrer les séances du moteur actuel")
    args = parser.parse_args(argv)
    actual = render()
    if args.update:
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(actual + "\n", encoding="utf-8")
        print(f"Séances de référence enregistrées : {GOLDEN.relative_to(ROOT)}")
        return 0
    expected = GOLDEN.read_text(encoding="utf-8").rstrip("\n") if GOLDEN.exists() else ""
    if expected == actual:
        print("Séances de référence : identiques.")
        return 0
    print(difference(expected, actual))
    return 1


if __name__ == "__main__":
    sys.exit(main())
