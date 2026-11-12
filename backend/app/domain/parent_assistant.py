"""Assistant parent (cahier des charges §46) : des réponses aux questions du parent, calculées à
partir des données réelles de l'enfant.

« Sur quoi faire travailler Emma cette semaine ? », « Comment l'aider à la maison ? », « Le
contrôle de vendredi : où en est-elle ? », « Est-ce qu'Emma progresse ? ». Chaque réponse est
écrite par le code (pas d'IA : rien d'inventé, toujours la même réponse pour les mêmes données)
et dit sur quels faits elle s'appuie. Le prénom remplace les pronoms : on ne devine jamais le
genre d'un enfant.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.errors import ERROR_LABELS, ErrorType
from app.domain.understanding import LEVEL_LABELS, CognitiveLevel, MasteryLevel

FOCUS_MAX = 3  # notions citées en priorité
EXAM_SOON_DAYS = 14  # un contrôle plus proche est cité dans « cette semaine »
REGULAR_DAYS = 4  # jours de révision sur 7 à partir desquels le rythme est bon
PROGRESS_STEP = 0.5  # écart de note moyenne (sur 10) signalé d'une semaine à l'autre


class Question(StrEnum):
    WEEK = "week"
    HELP = "help"
    EXAM = "exam"
    PROGRESS = "progress"


@dataclass(frozen=True)
class NotionFact:
    label: str
    lesson: str | None
    importance: int
    level: int  # 0 à 5 (`MasteryLevel`), oubli estimé compris
    days_since: int | None = None  # jours depuis la dernière révision ; None : jamais travaillée
    fading: bool = False  # sans doute un peu oubliée
    missing: int | None = None  # premier niveau de compréhension exigé pas encore validé
    subject: str | None = None

    @property
    def worked(self) -> bool:
        return self.days_since is not None


@dataclass(frozen=True)
class ExamFact:
    title: str
    days_left: int
    notions: list[NotionFact]


@dataclass(frozen=True)
class AssistantFacts:
    name: str
    grade: str
    notions: list[NotionFact]
    days_active: int = 0  # jours sur 7 avec au moins une réponse
    minutes: int = 0  # ces 7 jours
    sessions: int = 0  # séances terminées ces 7 jours
    daily_minutes: int | None = None  # objectif du parent
    priority_subject: str | None = None
    recurring: list[tuple[ErrorType, str]] = field(default_factory=list)  # (erreur, notion)
    exams: list[ExamFact] = field(default_factory=list)  # le plus proche d'abord
    week_scores: list[float | None] = field(
        default_factory=list
    )  # note moyenne /10, la plus récente en dernier
    mastered_recently: list[str] = field(default_factory=list)  # notions maîtrisées, travaillées ces 7 jours


@dataclass(frozen=True)
class Answer:
    question: Question
    title: str
    lines: list[str]
    based_on: list[str]  # les faits utilisés, chiffrés


# Ce qu'un parent peut faire à la maison, selon l'erreur qui revient (sans jamais faire à la
# place de l'enfant).
HOME_TIPS: dict[ErrorType, str] = {
    ErrorType.READING: "faites relire la consigne à voix haute avant de répondre",
    ErrorType.STATEMENT: "demandez de redire la consigne avec ses mots avant de commencer",
    ErrorType.CALCULATION: "encouragez à poser le calcul et à le vérifier (par l'opération inverse)",
    ErrorType.METHOD: "faites expliquer les étapes à voix haute : on voit vite où ça coince",
    ErrorType.CONFUSION: "comparez les deux notions côte à côte : ce qui les rapproche, ce qui les distingue",
    ErrorType.FORGOTTEN: "préférez trois révisions de 5 minutes à une longue : la mémoire aime la répétition",
    ErrorType.KNOWLEDGE: "relisez ensemble la fiche de la leçon dans « Mon cahier », 5 minutes sans jeu",
    ErrorType.IMPRECISION: "faites relire la réponse avant de valider : il manque souvent un détail",
    ErrorType.RANDOM: "rappelez qu'on a le temps : mieux vaut réfléchir que répondre vite",
}

_MISSING = {
    CognitiveLevel.RECOGNIZE: "la reconnaître parmi d'autres réponses",
    CognitiveLevel.RECALL: "la retrouver sans aide",
    CognitiveLevel.APPLY: "l'appliquer dans un exercice",
    CognitiveLevel.EXPLAIN: "l'expliquer avec ses mots",
    CognitiveLevel.TRANSFER: "s'en servir dans une situation nouvelle",
}


def _quote(labels: Sequence[str]) -> str:
    quoted = [f"« {label} »" for label in labels]
    return quoted[0] if len(quoted) == 1 else ", ".join(quoted[:-1]) + " et " + quoted[-1]


def _plural(count: int, word: str, plural: str | None = None) -> str:
    return f"{count} {word if count <= 1 else plural or word + 's'}"


def _session_minutes(facts: AssistantFacts) -> int:
    """Durée d'une séance conseillée : l'objectif du parent, sinon selon l'âge."""
    if facts.daily_minutes:
        return facts.daily_minutes
    if facts.grade in ("CP", "CE1"):
        return 10
    return 15 if facts.grade in ("CE2", "CM1", "CM2") else 20


def to_strengthen(facts: AssistantFacts) -> list[NotionFact]:
    """Notions travaillées encore fragiles, ou maîtrisées mais sans doute un peu oubliées : la
    matière choisie par le parent d'abord, puis les plus importantes, les plus faibles."""
    weak = [n for n in facts.notions if n.worked and (n.level <= MasteryLevel.LEARNING or n.fading)]
    return sorted(
        weak,
        key=lambda n: (n.subject != facts.priority_subject, -n.importance, n.level, n.label),
    )


def _why(notion: NotionFact) -> str:
    if notion.fading and notion.level >= MasteryLevel.MASTERED:
        return f"maîtrisée mais pas revue depuis {notion.days_since} jours"
    return LEVEL_LABELS[MasteryLevel(notion.level)].lower()


def week_focus(facts: AssistantFacts) -> Answer:
    title = f"Sur quoi faire travailler {facts.name} cette semaine ?"
    worked = [n for n in facts.notions if n.worked]
    based_on = [
        f"{_plural(len(worked), 'notion travaillée', 'notions travaillées')} sur {len(facts.notions)}",
        f"Révisé {_plural(facts.days_active, 'jour')} sur 7 ({facts.minutes} min)",
    ]
    if not worked:
        new = sorted(facts.notions, key=lambda n: -n.importance)[:FOCUS_MAX]
        start = ["Pas encore assez de séances pour conseiller à partir des résultats."]
        if new:
            start.append(f"🎯 Pour commencer : {_quote([n.label for n in new])}.")
        start.append(f"👉 Une séance de {_session_minutes(facts)} minutes sur la dernière leçon suffit.")
        return Answer(Question.WEEK, title, start, based_on)
    focus = to_strengthen(facts)[:FOCUS_MAX]
    lines: list[str] = []
    if focus:
        first = focus[0]
        lesson = f" ({first.lesson})" if first.lesson else ""
        lines.append(f"🎯 En priorité : « {first.label} »{lesson}, {_why(first)}.")
        if first.missing is not None and first.level >= MasteryLevel.LEARNING:
            lines.append(
                f"   {facts.name} la connaît ; il reste à {_MISSING[CognitiveLevel(first.missing)]}."
            )
        if len(focus) > 1:
            lines.append(f"Ensuite : {_quote([n.label for n in focus[1:]])}.")
        based_on.append(f"{_plural(len(to_strengthen(facts)), 'notion')} à renforcer")
    else:
        lines.append("✅ Tout ce qui a été travaillé tient bien : une nouvelle leçon peut être ajoutée.")
    for error, label in facts.recurring[:1]:
        lines.append(f"🔁 Sur « {label} » : {ERROR_LABELS[error].lower()}.")
        based_on.append(f"Erreur qui revient : {ERROR_LABELS[error].lower()} (« {label} »)")
    soon = [e for e in facts.exams if e.days_left <= EXAM_SOON_DAYS]
    if soon:
        exam = soon[0]
        lines.append(
            f"📅 Contrôle « {exam.title} » dans {_plural(exam.days_left, 'jour')} : "
            "la mission du jour suit déjà son plan de révision."
        )
    minutes = _session_minutes(facts)
    if facts.days_active >= REGULAR_DAYS:
        lines.append(f"👉 Gardez ce rythme : {facts.days_active} jours sur 7, des séances de {minutes} min.")
    else:
        lines.append(
            f"👉 Je recommande 3 séances courtes de {minutes} min cette semaine, plutôt qu'une longue."
        )
    return Answer(Question.WEEK, title, lines, based_on)


def how_to_help(facts: AssistantFacts) -> Answer:
    title = f"Comment aider {facts.name} à la maison ?"
    name = facts.name
    lines: list[str] = []
    if facts.grade in ("CP", "CE1"):
        lines.append(
            f"👂 À cet âge, restez à côté : lisez les consignes avec {name} (ou touchez 🔊), "
            "10 minutes suffisent."
        )
    elif facts.grade in ("CE2", "CM1", "CM2"):
        lines.append(
            f"🙌 Laissez {name} travailler en autonomie, puis faites-vous raconter ce qui a été appris."
        )
    else:
        lines.append(
            f"🗓️ Laissez {name} s'organiser ; un point de 5 minutes en fin de semaine suffit "
            "(contrôles à venir, notions à revoir)."
        )
    based_on = [f"Classe : {facts.grade}"]
    tips: list[ErrorType] = []
    for error, label in facts.recurring:
        if error not in tips and error in HOME_TIPS:
            tips.append(error)
            lines.append(f"🔁 Sur « {label} », {HOME_TIPS[error]}.")
            based_on.append(f"Erreur qui revient : {ERROR_LABELS[error].lower()} (« {label} »)")
        if len(tips) == 2:
            break
    focus = to_strengthen(facts)
    if focus:
        lines.append(
            f"🧑‍🏫 Demandez à {name} de vous expliquer « {focus[0].label} » avec ses mots, ou "
            "d'utiliser « Enseigne-moi » : expliquer aide à retenir."
        )
        if focus[0].lesson:
            lines.append(f"📚 Relisez ensemble la fiche « {focus[0].lesson} » dans « Mon cahier ».")
    if facts.days_active < REGULAR_DAYS:
        lines.append(
            "⏰ Un moment fixe chaque jour (après le goûter, par exemple) aide plus qu'une longue séance."
        )
    lines.append("💬 Félicitez l'effort et la régularité plutôt que la note.")
    return Answer(Question.HELP, title, lines, based_on)


def exam_ready(facts: AssistantFacts, exam: ExamFact) -> Answer:
    title = f"Le contrôle « {exam.title} » : où en est {facts.name} ?"
    ready = [n for n in exam.notions if n.level >= MasteryLevel.MASTERED and not n.fading]
    never = [n for n in exam.notions if not n.worked]
    weak = sorted(
        (n for n in exam.notions if n.worked and n not in ready), key=lambda n: (-n.importance, n.level)
    )
    when = "aujourd'hui" if exam.days_left == 0 else f"dans {_plural(exam.days_left, 'jour')}"
    lines = [f"📅 Contrôle {when}."]
    if exam.notions:
        lines.append(f"✅ Notions acquises : {len(ready)} sur {len(exam.notions)}.")
    if weak:
        lines.append(f"🟠 À revoir : {_quote([n.label for n in weak[:FOCUS_MAX]])}.")
    if never:
        lines.append(f"⚪ Pas encore travaillées : {_quote([n.label for n in never[:FOCUS_MAX]])}.")
    if not weak and not never and exam.notions:
        lines.append("👉 Tout est prêt : une révision courte la veille suffit pour garder tout en tête.")
    elif exam.days_left <= 2:
        lines.append(
            "👉 Dernière ligne droite : une séance courte par jour sur les notions à revoir, "
            "et une bonne nuit de sommeil."
        )
    else:
        lines.append("👉 La mission du jour suit le plan de révision : une séance par jour suffit.")
    based_on = [f"{len(exam.notions)} notion(s) dans les leçons du contrôle"]
    return Answer(Question.EXAM, title, lines, based_on)


def progress(facts: AssistantFacts) -> Answer:
    title = f"Est-ce que {facts.name} progresse ?"
    lines: list[str] = []
    scores = [s for s in facts.week_scores if s is not None]
    if len(facts.week_scores) >= 2 and facts.week_scores[-1] is not None and len(scores) >= 2:
        now, before = scores[-1], scores[-2]
        shown = f"{now:.1f}".replace(".", ",") + "/10"
        if now - before >= PROGRESS_STEP:
            lines.append(
                f"📈 Oui : note moyenne des séances {shown}, en hausse par rapport à la semaine d'avant."
            )
        elif before - now >= PROGRESS_STEP:
            lines.append(
                f"📉 Note moyenne des séances {shown}, un peu en baisse : des notions plus "
                "difficiles, ou de la fatigue ? Une séance plus courte peut aider."
            )
        else:
            lines.append(f"➡️ Stable : note moyenne des séances {shown}.")
    elif scores:
        lines.append("Pas encore assez de semaines pour comparer : revenez la semaine prochaine.")
    else:
        lines.append("Pas encore de séance terminée : la progression apparaîtra après quelques séances.")
    if facts.mastered_recently:
        lines.append(f"✅ Maîtrisées ces 7 jours : {_quote(facts.mastered_recently[:FOCUS_MAX])}.")
    mastered = sum(1 for n in facts.notions if n.level >= MasteryLevel.MASTERED)
    lines.append(
        f"🌟 {_plural(mastered, 'notion maîtrisée', 'notions maîtrisées')} sur {len(facts.notions)} en tout."
    )
    lines.append(f"📅 Révisé {_plural(facts.days_active, 'jour')} sur 7 ({facts.minutes} min).")
    based_on = [
        f"Notes moyennes des {len(facts.week_scores)} dernières semaines",
        f"{facts.sessions} séance(s) ces 7 jours",
    ]
    return Answer(Question.PROGRESS, title, lines, based_on)


def answers(facts: AssistantFacts) -> list[Answer]:
    """Les questions proposées au parent et leurs réponses ; un contrôle à venir ajoute la sienne."""
    found = [week_focus(facts), how_to_help(facts)]
    if facts.exams:
        found.append(exam_ready(facts, facts.exams[0]))
    found.append(progress(facts))
    return found
