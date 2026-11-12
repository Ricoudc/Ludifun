"""Deux écritures d'une même réponse (cahier des charges §9.1) : un enfant qui a juste ne doit
jamais lire « faux », et une faute ne doit jamais passer pour juste.

- Réponse écrite (`written_match`) : « 0,5 » vaut « 0.50 », « 1 000 » vaut « 1000 », « 8 + 7 »
  vaut « 7 + 8 », « quinze » vaut « 15 » (sauf si la consigne parle d'écrire en lettres ou en
  chiffres, ou en français). Une petite faute de frappe est tolérée, jamais sur un nombre ni sur
  un signe (« 1788 » n'est pas « en 1789 », « -3 » n'est pas « 3 »). En français, l'orthographe
  est ce qui est appris : pas de faute tolérée, les accents comptent (« chanté » n'est pas
  « chanter », « à » n'est pas « a »).
- Choix proposés (`same_answer`) : un distracteur égal à la réponse (« 8 + 7 » pour « 7 + 8 »,
  « 1/2 » pour « 0,5 ») rendrait la question fausse ; elle est écartée.
- Affirmations (`statement_truth`) : « 8 + 7 = 15 » rangée parmi les fausses est écartée.
"""

import re
from collections.abc import Iterable, Sequence
from fractions import Fraction

from app.domain.arithmetic import equality_holds, evaluate
from app.domain.knowledge import KnowledgeMaterial
from app.domain.text import damerau_levenshtein, normalize

# Espaces des milliers : espace, espace insécable, espace fine insécable.
_SPACES = re.compile(r"[   ]+")
_DECIMAL = re.compile(r"^([+-]?)(\d{1,3}(?: \d{3})+|\d+)(?:[.,](\d+))?$")
_FRACTION = re.compile(r"^(\d+) ?/ ?(\d+)$")
_TOKEN = re.compile(r"\d+(?:[.,]\d+)?|[+\-−–×x*÷:/=]")
# Une seule écriture par signe : « 4 x 3 » et « 3 × 4 » sont le même calcul.
_SAME_SIGN = {"x": "×", "*": "×", ":": "÷", "−": "-", "–": "-"}
_LETTERS_OR_DIGITS = re.compile(r"\b(en lettres|en chiffres|ecris le nombre|ecrire le nombre)\b")
_DIGITS = re.compile(r"\d+")
# Les signes gardés dans une réponse écrite, sous un nom qui survit à `normalize`.
_SIGNS = {
    "+": " plus ",
    "=": " egal ",
    "<": " inferieur ",
    ">": " superieur ",
    "≤": " inferieur ou egal ",
    "≥": " superieur ou egal ",
    "%": " pourcent ",
    "×": " fois ",
    "÷": " divise ",
}
_MINUS = re.compile(r"(?<=\d)\s*[-−–]\s*(?=\d)|(?<![\w-])[-−–]\s*(?=\d)")
_TIMES = re.compile(r"(?<=\d)\s*[x*]\s*(?=\d)")

_UNITS = {
    "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
    "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13,
    "quatorze": 14, "quinze": 15, "seize": 16, "trente": 30, "quarante": 40, "cinquante": 50,
    "soixante": 60, "septante": 70, "huitante": 80, "octante": 80, "nonante": 90,
}  # fmt: skip


def decimal_value(text: str) -> Fraction | None:
    """« 1 000,5 », « 0.50 », « -3 » → la valeur exacte ; autre chose → None."""
    compact = _SPACES.sub(" ", text.strip()).replace("−", "-").replace("–", "-")
    found = _DECIMAL.match(compact)
    if found is None:
        return None
    sign, whole, decimals = found.groups()
    value = Fraction(f"{whole.replace(' ', '')}.{decimals or '0'}")
    return -value if sign == "-" else value


def _tokens(text: str) -> list[str] | None:
    """« 7+8 », « 7 × 8 » → les nombres et les signes ; None si le texte n'est pas qu'un calcul."""
    compact = _SPACES.sub(" ", text.strip()).rstrip(" .")
    tokens = _TOKEN.findall(compact)
    if not tokens or "".join(tokens) != compact.replace(" ", ""):
        return None
    return [_SAME_SIGN.get(t, t) for t in tokens]


def _calculation(text: str) -> Fraction | None:
    """Valeur d'un calcul écrit seul (« 7 + 8 », « 3/4 », « 2 × 6 ») ; None sinon."""
    tokens = _tokens(text)
    if tokens is None or len(tokens) < 3 or "=" in tokens:
        return None
    return evaluate(tokens)


def value_of(text: str) -> Fraction | None:
    """Valeur d'une réponse qui est un nombre, une fraction ou un calcul ; None sinon."""
    decimal = decimal_value(text)
    if decimal is not None:
        return decimal
    if (fraction := _FRACTION.match(_SPACES.sub(" ", text.strip()))) and int(fraction.group(2)):
        return Fraction(int(fraction.group(1)), int(fraction.group(2)))
    return _calculation(text)


def french_number(text: str) -> int | None:
    """« quinze » → 15, « quatre-vingt-dix-neuf » → 99, « deux mille vingt-six » → 2026."""
    words = [w for w in re.split(r"[\s-]+", normalize(text)) if w and w != "et"]
    if not words:
        return None
    total = current = 0
    for word in words:
        if word in _UNITS:
            current += _UNITS[word]
        elif word in ("vingt", "vingts"):
            # « quatre-vingts » : 4 × 20 ; sinon « vingt » s'ajoute.
            current = current - 4 + 80 if current % 100 == 4 else current + 20
        elif word in ("cent", "cents"):
            hundreds = current % 100
            current = current - hundreds + max(1, hundreds) * 100
        elif word in ("mille", "mil"):
            total += max(1, current) * 1000
            current = 0
        else:
            return None
    return total + current


def same_answer(a: str, b: str) -> bool:
    """Deux choix disent la même chose : même texte, ou même valeur (« 8 + 7 » et « 7 + 8 »,
    « 1/2 » et « 0,5 », « 15 » et « quinze »). Un QCM qui les proposerait tous les deux aurait
    deux bonnes réponses."""
    if normalize(a) == normalize(b):
        return True
    va, vb = value_of(a), value_of(b)
    # Un nombre en lettres face à un nombre en chiffres seulement : « un » et « une » sont aussi
    # des articles, deux choix différents.
    if va is None and vb is not None and (n := french_number(a)) is not None:
        va = Fraction(n)
    if vb is None and va is not None and (n := french_number(b)) is not None:
        vb = Fraction(n)
    return va is not None and va == vb


def statement_truth(text: str) -> bool | None:
    """Une affirmation qui n'est qu'une égalité (« 8 + 7 = 15 ») : juste ou fausse, calculée.
    None pour toute autre phrase, que seule la leçon peut trancher."""
    tokens = _tokens(text)
    return equality_holds(tokens) if tokens is not None else None


def _with_signs(text: str) -> str:
    """Le texte normalisé, en gardant les signes : « -3 » → « moins 3 », « 7+8 » → « 7 plus 8 »."""
    text = _MINUS.sub(" moins ", text)
    text = _TIMES.sub(" fois ", text)
    for sign, word in _SIGNS.items():
        text = text.replace(sign, word)
    # « 15cm », « 3h30 » : le nombre et l'unité séparés, comme « 15 cm », « 3 h 30 ».
    text = re.sub(r"(?<=\d)(?=[^\W\d_])|(?<=[^\W\d_])(?=\d)", " ", text)
    # « 1 000 » comme « 1000 ».
    text = re.sub(r"(?<=\d)[   ](?=\d{3}\b)", "", text)
    return normalize(text)


def _typos(expected: str) -> int:
    """Fautes tolérées (§9.1) : aucune jusqu'à 4 caractères, 1 jusqu'à 8, 2 au-delà."""
    length = len(expected)
    return 0 if length <= 4 else 1 if length <= 8 else 2


def _same_spelling(given: str, expected: str) -> bool:
    """Orthographe exacte, sans compter les majuscules, l'apostrophe typographique, les espaces,
    la ponctuation finale ni « oe » tapé pour « œ » (clavier du téléphone)."""

    def clean(text: str) -> str:
        text = text.replace("’", "'").replace("ʼ", "'").casefold()
        text = text.replace("œ", "oe").replace("æ", "ae")
        return " ".join(text.split()).strip(" .!?;:,")

    if (value := decimal_value(expected)) is not None:  # « 1 000 » pour « 1000 »
        return decimal_value(given) == value
    return clean(given) == clean(expected)


def _number_words(given: str, expected: str, context: str) -> bool:
    """« quinze » pour « 15 » (ou l'inverse), sauf quand la consigne demande l'une des écritures."""
    if _LETTERS_OR_DIGITS.search(normalize(context)):
        return False
    g, e = decimal_value(given), decimal_value(expected)
    if g is None and (n := french_number(given)) is not None:
        g = Fraction(n)
    if e is None and (n := french_number(expected)) is not None:
        e = Fraction(n)
    return g is not None and g == e and (decimal_value(given) is None) != (decimal_value(expected) is None)


def written_match(given: str, expected: str, *, exact_spelling: bool = False, context: str = "") -> bool:
    """La réponse écrite `given` vaut la réponse attendue `expected`.

    `exact_spelling` : leçon de français, l'orthographe compte (accents compris).
    `context` : la consigne (« Écris en lettres… » interdit « 15 » pour « quinze »).
    """
    if not given.strip():
        return False
    if exact_spelling:
        return _same_spelling(given, expected)
    g, e = _with_signs(given), _with_signs(expected)
    if not g:
        return False
    if g == e:
        return True
    # Nombres : la valeur compte, pas l'écriture (« 0,5 », « 0.50 », « 1 000 »).
    dg, de = decimal_value(given), decimal_value(expected)
    if dg is not None or de is not None:
        return (dg is not None and dg == de) or _number_words(given, expected, context)
    # Calculs : « 8 + 7 » pour « 7 + 8 » (mêmes nombres, mêmes signes, même valeur).
    tg, te = _tokens(given), _tokens(expected)
    if tg is not None and te is not None:
        value = _calculation(expected)
        return value is not None and sorted(tg) == sorted(te) and _calculation(given) == value
    if _number_words(given, expected, context):
        return True
    # Une faute de frappe, jamais sur un nombre ni sur un signe.
    if _DIGITS.findall(g) != _DIGITS.findall(e) or _sign_words(g) != _sign_words(e):
        return False
    return damerau_levenshtein(g, e) <= _typos(e)


def _sign_words(text: str) -> list[str]:
    return [w for w in text.split() if w in {"plus", "moins", "egal", "fois", "divise", "pourcent"}]


def any_written_match(
    given: str, answers: Iterable[str], *, exact_spelling: bool = False, context: str = ""
) -> bool:
    return any(written_match(given, a, exact_spelling=exact_spelling, context=context) for a in answers)


def ambiguous_choices(answer: str, distractors: Sequence[str]) -> list[str]:
    """Les distracteurs qui disent la même chose que la réponse."""
    return [d for d in distractors if same_answer(answer, d)]


def all_different(texts: Sequence[str]) -> bool:
    """Aucun texte ne dit la même chose qu'un autre (« 0,5 » et « 1/2 » à ranger : ex æquo)."""
    return not any(same_answer(a, b) for i, a in enumerate(texts) for b in texts[i + 1 :])


def separate_boxes(boxes: Sequence[Sequence[str]]) -> bool:
    """Aucun élément d'une case ne vaut un élément d'une autre case. Dans la même case, c'est
    permis : « 0,5 » et « 2/4 » rangés ensemble sous « Égal à 1/2 »."""
    return not any(
        same_answer(a, b)
        for i, box in enumerate(boxes)
        for other in boxes[i + 1 :]
        for a in box
        for b in other
    )


def consistent(material: KnowledgeMaterial) -> KnowledgeMaterial:
    """Le matériel enregistré sans ce qui corrigerait faux un enfant qui a juste : une question
    dont un distracteur vaut la réponse, une affirmation que le calcul contredit, une suite ou un
    tri avec deux éléments de même valeur. Pour les leçons analysées avant ces contrôles."""
    questions = [q for q in material.questions if not ambiguous_choices(q.answer, q.distractors)]
    trues = [s for s in material.true_statements if statement_truth(s) is not False]
    falses = [s for s in material.false_statements if statement_truth(s) is not True]
    sequence = material.sequence
    if sequence is not None and not all_different(sequence.items):
        sequence = None
    sorting = material.sorting
    if sorting is not None and not separate_boxes([c.members for c in sorting.categories]):
        sorting = None
    changes = {
        "questions": questions,
        "true_statements": trues,
        "false_statements": falses,
        "sequence": sequence,
        "sorting": sorting,
    }
    if all(changes[key] == getattr(material, key) for key in changes):
        return material
    return material.model_copy(update=changes)
