"""Mode « Enseigne-moi » (cahier des charges §83, §26) : l'enfant devient professeur.

Ludi, l'élève joué par l'IA, demande à l'enfant de lui expliquer une notion de sa leçon, puis
pose une ou deux questions de relance (« Et pourquoi… ? »). L'IA propose, à chaque explication :
les points clés qu'elle y reconnaît (recopiés de la liste donnée), une réaction d'élève et sa
question suivante. Le code décide :

- les points clés attendus (ceux d'une question « expliquer » de la notion, sinon la phrase « à
  retenir ») ; un point cité par l'IA qui n'est pas dans la liste est ignoré ;
- le nombre de tours (`teach.follow_ups` questions de relance), puis la fin ;
- le niveau « expliquer » validé si l'enfant a dit au moins `teach.explain_ratio` des points
  clés, et seulement pour une notion déjà travaillée en séance ;
- ce que Ludi dit à l'enfant : contrôlé (§141), sinon remplacé par une phrase écrite par le code.

Sans IA (panne, délai dépassé), les points clés sont reconnus par leurs mots (comme une question
rédigée) et Ludi relance avec une phrase du code : l'enfant n'est jamais bloqué.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.activities.open_question import point_found
from app.domain.child_safety import unsafe_reason
from app.domain.decisions import Reason, Rule, reason
from app.domain.knowledge import KnowledgeItem, KnowledgeMaterial, KnowledgeUnit
from app.domain.mastery import Mastery
from app.domain.rules import RULES
from app.domain.understanding import CognitiveLevel

FOLLOW_UPS = RULES.teach.follow_ups
EXPLAIN_RATIO = RULES.teach.explain_ratio
KEY_POINTS_MAX = 5
ANSWER_MAX_LENGTH = 1000
LUDI_MAX_LENGTH = 220

FALLBACK_REACTION = "Merci, je comprends un peu mieux !"
FALLBACK_QUESTIONS = (
    "Tu peux me donner un exemple ?",
    "Et pourquoi c'est comme ça ? Je ne suis pas sûr d'avoir compris.",
    "Tu peux me le redire autrement, avec tes mots ?",
)


def key_points(item: KnowledgeItem, material: KnowledgeMaterial | None) -> list[str]:
    """Ce qu'une bonne explication contient : les points clés d'une question « expliquer » de la
    notion s'il y en a une, sinon la phrase « à retenir »."""
    if material is not None:
        explain = [q for q in material.open_questions if q.level == CognitiveLevel.EXPLAIN]
        for question in explain or material.open_questions:
            return list(dict.fromkeys(question.key_points))[:KEY_POINTS_MAX]
    return [item.statement]


def opening(label: str) -> str:
    return (
        f"Bonjour, je suis Ludi, ton élève ! Explique-moi « {label} », "
        "comme si je n'en avais jamais entendu parler."
    )


@dataclass(frozen=True)
class Turn:
    question: str  # ce que Ludi a demandé
    answer: str  # l'explication de l'enfant
    found: tuple[str, ...] = ()  # points clés reconnus dans cette explication
    reaction: str = ""  # ce que Ludi a répondu

    def to_json(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "found": list(self.found),
            "reaction": self.reaction,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Turn":
        return cls(data["question"], data["answer"], tuple(data.get("found", ())), data.get("reaction", ""))


def choose_notion(units: Sequence[KnowledgeUnit], masteries: Mapping[str, Mastery]) -> KnowledgeUnit | None:
    """La notion à expliquer, choisie par le code : d'abord une notion déjà bien travaillée
    (score ≥ 50) dont le niveau « expliquer » n'est pas encore validé, la plus importante ; puis
    une notion travaillée ; sinon la plus importante de la leçon."""

    def rank(unit: KnowledgeUnit) -> tuple[int, int, int]:
        mastery = masteries.get(unit.id)
        if mastery is None:
            group = 2
        elif mastery.score >= 50 and CognitiveLevel.EXPLAIN not in mastery.levels:
            group = 0
        else:
            group = 1
        return (group, -unit.item.importance, -(mastery.score if mastery else 0))

    return min(units, key=rank, default=None)


@dataclass(frozen=True)
class Reply:
    """Ce que Ludi répond à une explication, contrôlé par le code."""

    found: tuple[str, ...]
    reaction: str
    question: str | None  # None : la conversation est finie
    warnings: tuple[str, ...] = ()


def _clean(text: Any) -> str | None:
    if not isinstance(text, str):
        return None
    cleaned = " ".join(text.split())
    return cleaned if cleaned and len(cleaned) <= LUDI_MAX_LENGTH else None


def check_reply(
    raw: dict[str, Any] | None,
    points: Sequence[str],
    answer: str,
    turns_done: int,
    context: Sequence[str],
) -> Reply:
    """La réponse de Ludi au tour `turns_done` (0 : la première explication). `raw` : la
    proposition de l'IA (`None` si elle a échoué) ; `context` : le texte de la notion et de la
    leçon, d'où un mot sensible peut venir (§141)."""
    warnings: list[str] = []
    allowed = [*context, answer]
    if raw is None:
        found = tuple(p for p in points if point_found(answer, p))
        reaction, proposed = None, None
    else:
        cited = {str(p) for p in raw.get("found") or []}
        found = tuple(p for p in points if p in cited)
        if len(found) < len(cited):
            warnings.append("point clé inconnu ignoré")
        reaction, proposed = _clean(raw.get("reaction")), _clean(raw.get("question"))
        if reaction is not None and (why := unsafe_reason(reaction, allowed)):
            warnings.append(f"réaction : {why}")
            reaction = None
        if proposed is not None and (why := unsafe_reason(proposed, allowed)):
            warnings.append(f"question : {why}")
            proposed = None
        if proposed is not None and not proposed.endswith("?"):
            warnings.append("question : ce n'est pas une question")
            proposed = None
    last = turns_done >= FOLLOW_UPS
    question = None if last else proposed or FALLBACK_QUESTIONS[turns_done % len(FALLBACK_QUESTIONS)]
    return Reply(found, reaction or FALLBACK_REACTION, question, tuple(warnings))


@dataclass(frozen=True)
class Outcome:
    covered: tuple[str, ...]  # points clés dits au moins une fois
    total: int
    validated: bool  # niveau « expliquer » validé
    decision: Reason

    @property
    def message(self) -> str:
        return summary(len(self.covered), self.total)


def summary(said: int, total: int) -> str:
    """Le bilan de Ludi, à la fin de la conversation."""
    if total and said >= total:
        return f"Tu m'as tout appris : {said} point(s) sur {total} ! Tu es un super professeur. 🎓"
    if said:
        return f"Tu m'as appris {said} point(s) sur {total}. Relis ta leçon pour m'apprendre le reste !"
    return "Je n'ai pas encore bien compris : relis ta leçon et réessaie de m'expliquer !"


def outcome(points: Sequence[str], turns: Sequence[Turn], practised: bool) -> Outcome:
    """Bilan de la conversation : points clés dits, et niveau « expliquer » validé ou non (une
    notion encore jamais travaillée en séance ne reçoit pas de niveau)."""
    covered = tuple(p for p in points if any(p in t.found for t in turns))
    ratio = len(covered) / len(points) if points else 0.0
    validated = practised and ratio >= EXPLAIN_RATIO
    decision = reason(
        Rule.TEACH_EXPLAIN,
        covered=len(covered),
        total=len(points),
        threshold=EXPLAIN_RATIO,
        practised=practised,
        validated=validated,
    )
    return Outcome(covered, len(points), validated, decision)


def teach_input(grade: str, label: str, statement: str, points: Sequence[str], turns: Sequence[Turn]) -> str:
    """La notion et la conversation pour l'IA. L'explication de l'enfant est une donnée entre
    balises : s'il y écrit des consignes, elles ne sont pas suivies (§142-143)."""
    listed = "\n".join(f"- {p}" for p in points)
    conversation = []
    for turn in turns:
        safe = turn.answer.replace("<", "‹").replace(">", "›")
        conversation.append(f"Ludi : {turn.question}\n<explication_eleve>\n{safe}\n</explication_eleve>")
    return (
        f"Classe de l'élève : {grade}\n\n"
        f"Notion : {label}\nÀ retenir : {statement}\n\n"
        f"<points_cles>\n{listed}\n</points_cles>\n\n"
        + "\n\n".join(conversation)
        + f"\n\nTours restants après celui-ci : {max(0, FOLLOW_UPS - len(turns) + 1)}"
    )
