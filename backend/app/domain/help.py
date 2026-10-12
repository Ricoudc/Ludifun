"""« ❓ Je n'ai pas compris » : aide progressive en 5 niveaux (cahier des charges complet §27 ;
spécification technique §5.4).

1 indice → 2 rappel → 3 exemple semblable → 4 explication étape par étape → 5 la réponse.
Avant le niveau 5, une aide qui dévoilerait la réponse de l'activité est sautée. L'aide n'est
jamais punie à l'écran (la note de la séance ne change pas) ; elle compte seulement pour la
maîtrise : une réussite après l'exemple vaut moins, après la réponse elle ne prouve rien.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.activities.base import BuiltActivity
from app.domain.knowledge import KnowledgeUnit
from app.domain.rules import RULES
from app.domain.text import contains_words, matches_with_typos, normalize
from app.domain.understanding import APPLICABLE

MAX_HELP = 5
# Part du résultat retenue pour la maîtrise, selon l'aide la plus forte utilisée avant la réponse
# (engine_rules.toml).
HELP_RESULT_FACTOR = RULES.help.result_factor
LEVEL_PROOF_MAX_HELP = RULES.help.level_proof_max_help  # au-delà, pas de niveau validé


class HelpKind(StrEnum):
    HINT = "hint"
    REMINDER = "reminder"
    EXAMPLE = "example"
    STEPS = "steps"
    ANSWER = "answer"
    SOURCED = "sourced"  # étape 24b : expliqué à partir d'une source externe citée


TITLES = {
    HelpKind.HINT: "💡 Un indice",
    HelpKind.REMINDER: "📖 Rappel de la leçon",
    HelpKind.EXAMPLE: "✏️ Un exemple",
    HelpKind.STEPS: "🪜 Étape par étape",
    HelpKind.ANSWER: "✅ La réponse",
    HelpKind.SOURCED: "📚 Expliqué autrement",
}
DEFAULT_HINT = "Relis bien la question : quel mot te met sur la piste ?"


@dataclass(frozen=True)
class HelpStep:
    level: int  # 1 à 5
    kind: HelpKind
    text: str
    lines: list[str] = field(default_factory=list)  # étapes, ou exemple (question, réponse, pourquoi)

    @property
    def title(self) -> str:
        return TITLES[self.kind]

    @property
    def last(self) -> bool:
        return self.level >= MAX_HELP


def result_with_help(result: float, help_level: int) -> float:
    return result * HELP_RESULT_FACTOR[max(0, min(MAX_HELP, help_level))]


@dataclass(frozen=True)
class ExternalHelp:
    """Explication tirée d'un site éducatif, citations vérifiées (§117 : apport externe)."""

    text: str
    site: str


def _candidates(unit: KnowledgeUnit, external: ExternalHelp | None = None) -> dict[int, HelpStep | None]:
    material, item = unit.material, unit.item
    ladder = material.help
    reminder = ladder.reminder if ladder and ladder.reminder else None
    if reminder is None and item.type in APPLICABLE:
        reminder = item.statement  # une règle se rappelle sans donner la réponse de l'exercice
    example = ladder.example if ladder else None
    steps = ladder.steps if ladder else []
    return {
        1: HelpStep(
            1,
            HelpKind.HINT,
            (ladder.hint if ladder and ladder.hint else None) or material.tip or DEFAULT_HINT,
        ),
        2: HelpStep(2, HelpKind.REMINDER, reminder) if reminder else None,
        3: HelpStep(
            3,
            HelpKind.EXAMPLE,
            example.question,
            [f"→ {example.answer}", *([example.why] if example.why else [])],
        )
        if example
        else HelpStep(3, HelpKind.SOURCED, external.text, [f"📚 En plus de ta leçon — {external.site}"])
        if external
        else None,
        4: HelpStep(4, HelpKind.STEPS, "Suis ces étapes :", list(steps)) if steps else None,
    }


def reveals(shown: str, answer: str) -> bool:
    """Le texte d'aide dévoile-t-il la réponse ? Prudent : un pluriel (« numérateurs »), une faute
    ou les mots de la réponse dans le désordre suffisent à écarter l'aide."""
    if not answer.strip():
        return False
    if contains_words(shown, answer):
        return True
    words = normalize(shown).split()
    wanted = normalize(answer).split()

    def present(expected: str) -> bool:
        if len(expected) < 4:
            return expected in words
        return any(w.startswith(expected) or matches_with_typos(w, expected) for w in words)

    return all(present(expected) for expected in wanted)


def next_help(
    unit: KnowledgeUnit, activity: BuiltActivity, current: int, external: ExternalHelp | None = None
) -> HelpStep:
    """L'aide suivant `current` (0 : aucune encore), en sautant celles qui manquent ou qui
    dévoileraient la réponse ; au bout, la réponse elle-même avec son explication. Sans exemple
    dans la leçon, une explication sourcée (`external`, étape 24b) peut en tenir lieu."""
    answer = str(activity.solution.get("display", ""))
    for level, step in _candidates(unit, external).items():
        if level <= current or step is None:
            continue
        if reveals(" ".join([step.text, *step.lines]), answer):
            continue
        return step
    explanation = activity.solution.get("explanation")
    return HelpStep(MAX_HELP, HelpKind.ANSWER, answer, [explanation] if explanation else [])
