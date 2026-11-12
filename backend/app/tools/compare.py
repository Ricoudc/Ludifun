"""Comparer deux évaluations du pipeline sur le même corpus (§5.81) : deux versions de prompt,
deux modèles ou deux fournisseurs, et revenir à la meilleure.

    uv run python -m app.tools.evaluate ../eval/lessons --prompt analysis=v7    # A : l'ancienne
    uv run python -m app.tools.evaluate ../eval/lessons                         # B : l'actuelle
    uv run python -m app.tools.compare ../eval/results/<A> ../eval/results/<B>

Chaque évaluation a écrit `metrics.json` (mesures, configuration : fournisseur, modèles,
version de chaque prompt). L'outil met les mesures côte à côte, dit pour chacune laquelle est
meilleure, compare leçon par leçon (seulement les leçons des deux évaluations), puis conclut :
la justesse d'abord (leçons traitées, rappel des notions, notions inventées, noms personnels,
matériel rejeté), la durée et le coût ensuite. Il dit enfin quoi changer pour revenir à la
configuration retenue. Aucun texte de leçon : seulement des chiffres et des noms de dossiers.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Mesures où plus bas vaut mieux (les autres : plus haut vaut mieux).
LOWER_IS_BETTER = ("Notions inventées", "Matériel rejeté", "Durée", "Coût", "Noms personnels")
# Mesures qui décident (la justesse) ; la durée et le coût départagent.
QUALITY = (
    "Leçons traitées correctement",
    "Rappel des notions indispensables",
    "Notions inventées",
    "Noms personnels",
    "Matériel rejeté",
    "Matière correcte",
    "Niveau à ± 1 classe",
)
TIE_BREAKERS = ("Durée", "Coût")
NEUTRAL = ("Photos à faire vérifier",)  # dépend des photos, pas de la configuration
EPSILON = 0.5  # écart négligeable (points de pourcentage, secondes…)


def load(folder: Path) -> dict[str, Any]:
    path = folder / "metrics.json"
    if not path.exists():
        raise SystemExit(f"{path} introuvable : relancez l'évaluation (choix 12) avec cette version.")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _starts(name: str, prefixes: tuple[str, ...]) -> bool:
    return name.startswith(prefixes)


def better(name: str, a: float | None, b: float | None) -> str | None:
    """« A », « B » ou None (égalité, mesure neutre ou manquante)."""
    if a is None or b is None or _starts(name, NEUTRAL) or abs(a - b) <= EPSILON:
        return None
    lower = _starts(name, LOWER_IS_BETTER)
    return ("A" if a < b else "B") if lower else ("A" if a > b else "B")


@dataclass(frozen=True)
class Verdict:
    winner: str | None  # « A », « B » ou None (aucune différence nette)
    reason: str


def verdict(a: dict[str, Any], b: dict[str, Any]) -> Verdict:
    rows = _rows(a, b)
    wins = {"A": 0, "B": 0}
    for name, va, vb in rows:
        if _starts(name, QUALITY) and (w := better(name, va, vb)):
            wins[w] += 1
    if wins["A"] != wins["B"]:
        w = "A" if wins["A"] > wins["B"] else "B"
        return Verdict(w, f"justesse meilleure sur {wins[w]} mesure(s) contre {wins['AB'.replace(w, '')]}")
    for prefix in TIE_BREAKERS:
        for name, va, vb in rows:
            if _starts(name, (prefix,)) and (w := better(name, va, vb)):
                return Verdict(w, f"justesse égale ; {name.split(' (')[0].lower()} meilleure")
    return Verdict(None, "aucune différence nette : garder l'actuelle")


def _rows(a: dict[str, Any], b: dict[str, Any]) -> list[tuple[str, float | None, float | None]]:
    values_b = {m["name"]: m["value"] for m in b["metrics"]}
    return [(m["name"], m["value"], values_b.get(m["name"])) for m in a["metrics"]]


def _config_changes(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    ca, cb = a["configuration"], b["configuration"]
    changes = []
    if ca["provider"] != cb["provider"]:
        changes.append(f"fournisseur : {ca['provider']} → {cb['provider']}")
    for stage in sorted(set(ca["models"]) | set(cb["models"])):
        if ca["models"].get(stage) != cb["models"].get(stage):
            changes.append(f"modèle ({stage}) : {ca['models'].get(stage)} → {cb['models'].get(stage)}")
    for stage in sorted(set(ca["prompts"]) | set(cb["prompts"])):
        if ca["prompts"].get(stage) != cb["prompts"].get(stage):
            changes.append(f"prompt {stage} : {ca['prompts'].get(stage)} → {cb['prompts'].get(stage)}")
    return changes


def _back_to(kept: dict[str, Any], other: dict[str, Any]) -> list[str]:
    """Ce qu'il faut changer pour revenir à la configuration retenue."""
    ck, co = kept["configuration"], other["configuration"]
    steps = [
        f'- prompt `{stage}` : remettre `"{stage}": "{version}"` dans `PROMPT_VERSIONS` '
        "(`backend/app/ai/ports.py`)"
        for stage, version in sorted(ck["prompts"].items())
        if co["prompts"].get(stage) != version
    ]
    if ck["provider"] != co["provider"]:
        steps.append(f"- fournisseur : choisir « {ck['provider']} » (espace parent ou `LUDIFUN_AI_PROVIDER`)")
    steps += [
        f"- modèle de l'étape {stage} : {model} (réglage du modèle de cette étape)"
        for stage, model in sorted(ck["models"].items())
        if co["models"].get(stage) != model
    ]
    return steps or ["- rien : c'est déjà la configuration en place."]


def render(a_dir: Path, b_dir: Path) -> str:
    a, b = load(a_dir), load(b_dir)
    icon = {"A": "◀ A", "B": "B ▶", None: "="}
    changes = [f"- {c}" for c in _config_changes(a, b)] or [
        "- rien (même configuration : écarts dus au hasard du modèle)"
    ]
    lines = [
        f"# Comparaison : A = `{a_dir.name}` · B = `{b_dir.name}`",
        "",
        "## Ce qui change de A à B",
        "",
        *changes,
        "",
        "## Mesures",
        "",
        "| Mesure | A | B | Meilleure |",
        "|---|---|---|---|",
    ]
    display_b = {m["name"]: m["display"] for m in b["metrics"]}
    for m in a["metrics"]:
        vb = next((x["value"] for x in b["metrics"] if x["name"] == m["name"]), None)
        lines.append(
            f"| {m['name']} | {m['display']} | {display_b.get(m['name'], '—')} "
            f"| {icon[better(m['name'], m['value'], vb)]} |"
        )
    common = sorted(set(a["lessons"]) & set(b["lessons"]))
    only = sorted(set(a["lessons"]) ^ set(b["lessons"]))
    lines += ["", f"## Par leçon ({len(common)} en commun)", ""]
    if only:
        lines += [f"⚠ Pas dans les deux évaluations (non comparées) : {', '.join(only)}", ""]
    lines += [
        "| Leçon | Rappel A → B | Inventées A → B | Rejets A → B | Durée A → B |",
        "|---|---|---|---|---|",
    ]
    for name in common:
        la, lb = a["lessons"][name], b["lessons"][name]

        def pct(v: float | None) -> str:
            return "—" if v is None else f"{100 * v:.0f} %"

        lines.append(
            f"| {name} | {pct(la['recall'])} → {pct(lb['recall'])} | {la['invented']} → {lb['invented']} "
            f"| {la['rejected']} → {lb['rejected']} | {la['duration_s']} s → {lb['duration_s']} s |"
        )
    v = verdict(a, b)
    kept, other = (b, a) if v.winner == "B" else (a, b)
    name = {"A": a_dir.name, "B": b_dir.name}.get(v.winner or "", "")
    lines += [
        "",
        "## Verdict",
        "",
        f"**{'À garder : ' + v.winner + ' (`' + name + '`)' if v.winner else 'Égalité'}** — {v.reason}.",
    ]
    if v.winner:
        lines += ["", "Pour revenir à cette configuration :", "", *_back_to(kept, other)]
    lines += [
        "",
        "Avant de trancher : relire quelques séances (`<leçon>.txt`) des deux évaluations avec la "
        "grille `eval/grille-evaluation.md` ; les chiffres ne voient pas tout.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.tools.compare", description=__doc__.split("\n")[0])
    parser.add_argument("a", type=Path, help="dossier de résultats de la première évaluation")
    parser.add_argument("b", type=Path, help="dossier de résultats de la seconde évaluation")
    parser.add_argument("--out", type=Path, help="écrire aussi la comparaison dans ce fichier")
    args = parser.parse_args(argv)
    text = render(args.a, args.b)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
