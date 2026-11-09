"""« Que travailler avec mon enfant cette semaine ? » (§5.71) : trois actions concrètes pour le
parent, tirées des données, sans lui demander d'être enseignant.

Chaque action dit quoi faire, comment (le geste précis, en quelques minutes) et pourquoi (le
fait qui l'a fait choisir). Rien n'est décidé ici pour l'enfant : ce sont des conseils au parent.
Ordre, du plus urgent au plus général :

1. une leçon attend la relecture du parent (§5.69) : l'enfant ne peut pas la réviser avant ;
2. un contrôle dans les 7 jours ;
3. la notion la plus fragile : la lui faire expliquer avec ses mots, la phrase à retenir sous
   les yeux ;
4. l'erreur qui revient : le geste qui y répond (relire l'énoncé, poser le calcul…) ;
5. la régularité, quand l'enfant a révisé moins de 3 jours sur 7 ;
6. les révisions dues, sinon ajouter la leçon de la semaine.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.domain.errors import ErrorType

MAX_ACTIONS = 3
REGULAR_DAYS = 3  # en dessous (jours de révision sur 7), conseiller un moment fixe
DEFAULT_MINUTES = 10
DAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

# Le geste du parent face à l'erreur qui revient (sans faire à la place de l'enfant).
ERROR_GESTURES: dict[ErrorType, tuple[str, str]] = {
    ErrorType.KNOWLEDGE: (
        "Relire la leçon ensemble",
        "Cinq minutes : lisez-la à voix haute avec {child}, puis demandez-lui de vous la raconter.",
    ),
    ErrorType.CALCULATION: (
        "Poser les calculs sur papier",
        "Quand {child} révise, proposez-lui un brouillon et de vérifier chaque calcul une fois.",
    ),
    ErrorType.METHOD: (
        "Lui faire dire la méthode",
        "Avant de répondre, demandez-lui : « Comment tu t'y prends ? » ; la méthode d'abord.",
    ),
    ErrorType.READING: (
        "Lire l'énoncé deux fois",
        "Proposez à {child} de lire la question deux fois, et de dire ce qu'on lui demande.",
    ),
    ErrorType.CONFUSION: (
        "Comparer les deux notions",
        "Demandez-lui ce qui les différencie, avec un exemple de chaque : les confusions tombent.",
    ),
    ErrorType.FORGOTTEN: (
        "Réviser un peu chaque jour",
        "Ce qui s'oublie se retient mieux en petites révisions rapprochées : 5 minutes par jour.",
    ),
    ErrorType.IMPRECISION: (
        "Relire avant de valider",
        "{child} sait presque : une relecture de sa réponse (accents, unités) suffit souvent.",
    ),
    ErrorType.RANDOM: (
        "Prendre son temps",
        "{child} répond parfois trop vite : rappelez-lui que la vitesse ne compte pas.",
    ),
    ErrorType.STATEMENT: (
        "Reformuler la consigne",
        "Demandez-lui de redire la consigne avec ses mots avant de commencer.",
    ),
}


@dataclass(frozen=True)
class WeakNotion:
    label: str
    statement: str  # la phrase à retenir
    lesson: str | None = None


@dataclass(frozen=True)
class WeekFacts:
    child: str  # prénom, pour des phrases adressées au parent
    today: date
    awaiting_lessons: list[str] = field(default_factory=list)  # titres à relire (§5.69)
    exams: list[tuple[str, date]] = field(default_factory=list)  # (titre, date), les 7 jours à venir
    weak: WeakNotion | None = None
    recurring: tuple[ErrorType, str] | None = None  # (type d'erreur, notion)
    days_active: int = 0  # jours de révision sur les 7 derniers
    reviews_due: int = 0
    daily_minutes: int | None = None  # temps choisi par le parent
    lessons: int = 0  # leçons prêtes


# Sorte d'action, pour l'icône de l'application.
ActionKind = Literal["review", "exam", "explain", "error", "routine", "due", "lesson"]


@dataclass(frozen=True)
class WeekAction:
    kind: ActionKind
    title: str
    detail: str
    why: str


def _when(day: date, today: date) -> str:
    delta = (day - today).days
    if delta <= 0:
        return "aujourd'hui"
    if delta == 1:
        return "demain"
    return DAYS[day.weekday()]


def week_actions(facts: WeekFacts) -> list[WeekAction]:
    """Au plus trois actions, de la plus urgente à la plus générale."""
    child = facts.child
    actions: list[WeekAction] = []
    if facts.awaiting_lessons:
        title = facts.awaiting_lessons[0]
        more = len(facts.awaiting_lessons) - 1
        actions.append(
            WeekAction(
                "review",
                f"Relire et valider « {title} »",
                f"{child} ne peut pas la réviser avant. Vérifiez le résumé et les réponses, corrigez "
                "ce qui est faux, puis « Valider la leçon ».",
                "Leçon prête qui attend votre relecture" + (f" (et {more} autre(s))." if more > 0 else "."),
            )
        )
    for title, day in sorted(facts.exams, key=lambda e: e[1])[:1]:
        actions.append(
            WeekAction(
                "exam",
                f"Préparer le contrôle « {title} » ({_when(day, facts.today)})",
                f"Une courte séance par jour d'ici là : le plan de révision est prêt pour {child}. "
                "La veille, demandez-lui d'expliquer la leçon avec ses mots.",
                f"Contrôle prévu le {day.day:02d}/{day.month:02d}.",
            )
        )
    if facts.weak is not None:
        weak = facts.weak
        actions.append(
            WeekAction(
                "explain",
                f"Faire expliquer « {weak.label} »",
                f"Au dîner ou en voiture, demandez à {child} de vous l'expliquer avec ses mots. "
                f"Ce qu'il faut retenir : « {weak.statement} ». "
                "En cas d'hésitation, relisez la leçon ensemble.",
                "Notion la plus fragile" + (f" de « {weak.lesson} »." if weak.lesson else "."),
            )
        )
    if facts.recurring is not None:
        error, label = facts.recurring
        title, detail = ERROR_GESTURES[error]
        actions.append(
            WeekAction("error", title, detail.format(child=child), f"Erreur qui revient sur « {label} ».")
        )
    if facts.lessons and facts.days_active < REGULAR_DAYS:
        minutes = facts.daily_minutes or DEFAULT_MINUTES
        actions.append(
            WeekAction(
                "routine",
                f"Fixer un moment de {minutes} min, 4 jours cette semaine",
                f"Toujours à la même heure (après le goûter, avant le bain) : pour {child}, la "
                "régularité compte plus que la durée.",
                f"{facts.days_active} jour(s) de révision sur les 7 derniers.",
            )
        )
    if facts.reviews_due:
        actions.append(
            WeekAction(
                "due",
                "Faire les révisions du jour",
                f"La mission du jour de {child} reprend ce qui s'oublie : une séance suffit.",
                f"{facts.reviews_due} notion(s) à revoir maintenant.",
            )
        )
    if not facts.lessons or len(actions) < MAX_ACTIONS:
        actions.append(
            WeekAction(
                "lesson",
                "Ajouter la leçon de la semaine",
                f"Dès qu'une leçon est donnée en classe, photographiez-la : {child} la révise tant "
                "qu'elle est fraîche.",
                "Aucune leçon pour l'instant." if not facts.lessons else "Pour garder de l'avance.",
            )
        )
    return actions[:MAX_ACTIONS]
