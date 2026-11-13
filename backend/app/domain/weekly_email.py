"""Le bilan de la semaine, par e-mail (§5.93) : le texte, à partir de ce que le tableau de bord
montre déjà (« En bref » et « Cette semaine »). Domaine pur : ni base, ni envoi.

Un e-mail par parent, le dimanche, avec chaque enfant de la famille. Rien n'y est décidé pour
l'enfant : c'est un compte rendu, et ce qu'on peut faire cette semaine.
"""

from dataclasses import dataclass, field

SEND_WEEKDAY = 6  # dimanche (lundi = 0)
MIN_DAYS_BETWEEN = 6  # jamais deux bilans la même semaine


@dataclass(frozen=True)
class ChildWeek:
    name: str
    summary: list[str] = field(default_factory=list)
    actions: list[tuple[str, str]] = field(default_factory=list)  # (titre, détail)


def subject(children: list[ChildWeek]) -> str:
    names = ", ".join(c.name for c in children[:3])
    return f"Ludifun : la semaine de {names}" if names else "Ludifun : votre semaine"


def body(first_name: str | None, children: list[ChildWeek], app_hint: str) -> str:
    lines = [f"Bonjour {first_name}," if first_name else "Bonjour,", ""]
    lines.append("Voici le bilan de la semaine.")
    for child in children:
        lines += ["", f"— {child.name} —"]
        lines += [f"• {line}" for line in child.summary] or ["• Pas de révision cette semaine."]
        if child.actions:
            lines += ["", "Cette semaine, vous pouvez :"]
            lines += [f"  – {title} : {detail}" for title, detail in child.actions[:3]]
    lines += [
        "",
        app_hint,
        "",
        "Vous recevez ce message parce que vous l'avez demandé dans Ludifun (Objectifs et "
        "contrôles → « Bilan de la semaine par e-mail »). Vous pouvez l'arrêter au même endroit.",
    ]
    return "\n".join(lines)
