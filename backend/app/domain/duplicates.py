"""Exercices en double (demande de la famille) : à la fin de l'analyse, le code relit tout le
matériel de la leçon et retire ce que l'enfant verrait deux fois.

L'IA prépare les exercices notion par notion, souvent en plusieurs demandes : deux notions
proches reçoivent parfois la même question (« En quelle année commence la Révolution ? » pour
« 1789 » et pour « La prise de la Bastille »), ou presque la même à un mot près. Une fois sûr que
deux éléments sont le même exercice, le code garde le premier (la notion la plus importante) et
retire l'autre, avec la raison. Deux questions qui ne diffèrent que par un nombre (7 × 8, 7 × 9)
ou par leur réponse, ou par un seul mot important (« vertébré » / « invertébré ») ne sont pas
des doublons : ce sont deux exercices. Dans le doute, l'exercice reste.

Jamais au point de rendre une notion injouable : si, sans ses doublons, une notion n'a plus
aucune activité possible, son matériel reste tel quel.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from app.domain.knowledge import KnowledgeMaterial
from app.domain.rules import RULES
from app.domain.text import normalize
from app.domain.validation import Rejection

# Ressemblance des mots importants (0 à 1, engine_rules.toml) au-delà de laquelle deux longs
# textes sont le même exercice ; les textes courts doivent avoir exactement les mêmes mots.
SIMILAR = RULES.material.similar_ratio
LONG = 8  # mots importants : en dessous, un seul mot différent change la question
# Petits mots : les changer ne change pas l'exercice (« Le volcan… » / « Un volcan… »). Jamais la
# négation (« ne », « pas ») : elle change le sens.
_SMALL = frozenset(
    [
        "le",
        "la",
        "les",
        "l",
        "un",
        "une",
        "des",
        "du",
        "de",
        "d",
        "au",
        "aux",
        "a",
        "et",
        "ou",
        "en",
        "que",
        "qu",
        "qui",
        "quel",
        "quelle",
        "quels",
        "quelles",
        "est",
        "sont",
        "ce",
        "cet",
        "cette",
        "ces",
        "se",
        "s",
        "il",
        "elle",
        "ils",
        "elles",
        "on",
        "y",
    ]
)


def _words(text: str) -> list[str]:
    return [w for w in normalize(text).split() if w not in _SMALL]


def similar(a: str, b: str) -> bool:
    """Le même texte aux petits mots, à l'ordre des mots et à la ponctuation près. Jamais un
    mot important de différence sur un texte court : « vertébré » / « invertébré », « cheval »
    / « chameau », « 7 × 8 » / « 7 × 9 » sont deux exercices."""
    if normalize(a) == normalize(b):
        return True
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    if sorted(wa) == sorted(wb):
        return True
    sa, sb = set(wa), set(wb)
    if min(len(sa), len(sb)) < LONG or {w for w in sa ^ sb if w.isdigit()}:
        return False
    return len(sa & sb) / len(sa | sb) >= SIMILAR


@dataclass(frozen=True)
class Element:
    kind: str  # même sorte d'exercice : « question », « vrai », « faux », « texte à trous »…
    label: str  # « questions[1] », « cloze »… comme les refus de la validation
    texts: tuple[str, ...]  # ce qui doit se ressembler pour que ce soit le même exercice


def elements(material: KnowledgeMaterial) -> list[Element]:
    """Les exercices du matériel, chacun avec ce qui le définit pour l'enfant."""
    found = [
        Element("question", f"questions[{i}]", (q.stem, q.answer)) for i, q in enumerate(material.questions)
    ]
    found += [Element("vrai", f"true_statements[{i}]", (t,)) for i, t in enumerate(material.true_statements)]
    found += [
        Element("faux", f"false_statements[{i}]", (f,)) for i, f in enumerate(material.false_statements)
    ]
    if material.cloze is not None:
        found.append(Element("texte à trous", "cloze", (material.cloze.text,)))
    if material.pair is not None:
        found.append(Element("paire", "pair", (material.pair.left, material.pair.right)))
    if material.flashcard is not None:
        found.append(Element("carte", "flashcard", (material.flashcard.front,)))
    found += [
        Element("question ouverte", f"open_questions[{i}]", (q.prompt,))
        for i, q in enumerate(material.open_questions)
    ]
    return found


def same(a: Element, b: Element) -> bool:
    return a.kind == b.kind and all(similar(x, y) for x, y in zip(a.texts, b.texts, strict=True))


def without(material: KnowledgeMaterial, labels: set[str]) -> KnowledgeMaterial:
    """Le matériel sans les éléments nommés."""

    def keep[T](name: str, items: list[T]) -> list[T]:
        return [x for i, x in enumerate(items) if f"{name}[{i}]" not in labels]

    return material.model_copy(
        update={
            "questions": keep("questions", material.questions),
            "true_statements": keep("true_statements", material.true_statements),
            "false_statements": keep("false_statements", material.false_statements),
            "open_questions": keep("open_questions", material.open_questions),
            "cloze": None if "cloze" in labels else material.cloze,
            "pair": None if "pair" in labels else material.pair,
            "flashcard": None if "flashcard" in labels else material.flashcard,
        }
    )


@dataclass(frozen=True)
class Deduplicated:
    material: KnowledgeMaterial
    removed: list[Rejection] = field(default_factory=list)


Usable = Callable[[str, KnowledgeMaterial], bool]


def deduplicate(
    materials: Sequence[tuple[str, KnowledgeMaterial]],
    usable: Usable,
    already: Sequence[tuple[str, KnowledgeMaterial]] = (),
) -> dict[str, Deduplicated]:
    """Retire les exercices en double dans `materials` (dans l'ordre : la notion la plus
    importante d'abord), entre eux et avec `already` (matériel déjà enregistré, gardé tel quel).
    `usable(notion, matériel)` : la notion a encore au moins une activité possible."""
    seen: list[tuple[str, Element]] = [(n, e) for n, m in already for e in elements(m)]
    result: dict[str, Deduplicated] = {}
    for notion, material in materials:
        drop: dict[str, str] = {}
        mine: list[tuple[str, Element]] = []
        for element in elements(material):
            twin = next(((n, e) for n, e in seen + mine if same(element, e)), None)
            if twin is None:
                mine.append((notion, element))
                continue
            where = "dans la même notion" if twin[0] == notion else f"de la notion {twin[0]}"
            drop[element.label] = f"exercice en double ({element.kind} {where}, {twin[1].label})"
        cleaned = without(material, set(drop)) if drop else material
        if drop and not usable(notion, cleaned):
            cleaned, drop = material, {}  # la notion reste jouable, même avec un doublon
            mine = [(notion, e) for e in elements(material)]
        seen += mine
        result[notion] = Deduplicated(cleaned, [Rejection(label, reason) for label, reason in drop.items()])
    return result
