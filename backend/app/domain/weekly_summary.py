"""« En bref » : les 7 derniers jours de l'enfant en quelques phrases, pour le parent.

Le tableau de bord montre les chiffres ; ce résumé dit ce qui compte et ce qu'on peut faire,
sans que le parent ait à tout lire. Rien n'est décidé ici pour l'enfant : c'est un compte rendu,
calculé à partir des données déjà enregistrées.
"""

from dataclasses import dataclass, field

MAX_LABELS = 3  # notions citées par phrase, au plus
MINUTES_CHANGE = 5  # écart de temps signalé par rapport aux 7 jours d'avant


@dataclass(frozen=True)
class RecentFacts:
    days_active: int  # jours (sur 7) avec au moins une réponse
    sessions: int  # séances terminées
    minutes: int
    previous_minutes: int  # les 7 jours d'avant
    mastered: list[str] = field(default_factory=list)  # notions maîtrisées, travaillées ces 7 jours
    weak: tuple[str, str | None] | None = None  # (notion, leçon) la plus fragile
    recurring: tuple[str, str] | None = None  # (type d'erreur lisible, notion)
    help_questions: int = 0
    reports_to_see: int = 0
    reviews_due: int = 0


def _plural(count: int, word: str, plural: str | None = None) -> str:
    return f"{count} {word if count <= 1 else plural or word + 's'}"


def _labels(labels: list[str]) -> str:
    shown = ", ".join(labels[:MAX_LABELS])
    more = len(labels) - MAX_LABELS
    return f"{shown} et {_plural(more, 'autre')}" if more > 0 else shown


def weekly_summary(facts: RecentFacts) -> list[str]:
    """Quelques phrases, de la plus générale à la plus utile pour agir."""
    lines: list[str] = []
    if facts.days_active == 0:
        lines.append("Aucune révision ces 7 derniers jours.")
    else:
        line = (
            f"📅 Révisé {_plural(facts.days_active, 'jour')} sur 7 : "
            f"{_plural(facts.sessions, 'séance')}, {facts.minutes} min"
        )
        change = facts.minutes - facts.previous_minutes
        if facts.previous_minutes and abs(change) >= MINUTES_CHANGE:
            line += f" ({'+' if change > 0 else '−'}{abs(change)} min par rapport aux 7 jours d'avant)"
        lines.append(line + ".")
    if facts.mastered:
        lines.append(f"✅ Bien acquis : {_labels(facts.mastered)}.")
    if facts.weak is not None:
        label, lesson = facts.weak
        lines.append(f"🟠 À renforcer : {label}" + (f" ({lesson})." if lesson else "."))
    if facts.recurring is not None:
        error, label = facts.recurring
        lines.append(f"🔁 Erreur qui revient sur « {label} » : {error.lower()}.")
    if facts.help_questions:
        lines.append(f"❓ Aide demandée sur {_plural(facts.help_questions, 'question')}.")
    if facts.reports_to_see:
        lines.append(
            f"🚩 {_plural(facts.reports_to_see, 'question signalée', 'questions signalées')} à regarder."
        )
    lines.append(_advice(facts))
    return lines


def _advice(facts: RecentFacts) -> str:
    if facts.reports_to_see:
        return "👉 Regardez d'abord les questions signalées : une question mal posée décourage."
    if facts.days_active == 0:
        return "👉 Une séance de 10 minutes suffit pour reprendre l'habitude."
    if facts.reviews_due:
        return (
            f"👉 La mission du jour reprend {_plural(facts.reviews_due, 'notion')} à revoir : "
            "quelques minutes suffisent."
        )
    if facts.weak is not None:
        return f"👉 Une séance courte sur « {facts.weak[0]} » l'aiderait."
    return "👉 Tout est à jour : une nouvelle leçon peut être ajoutée."
