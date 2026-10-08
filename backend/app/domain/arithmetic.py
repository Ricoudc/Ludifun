"""Calculs écrits avec des étiquettes (« Démêler ») : une égalité est-elle vraie ?

Un calcul s'écrit dans plusieurs ordres justes : « 7 + 8 = 15 », « 8 + 7 = 15 », « 15 = 7 + 8 ».
Le code calcule (fractions exactes, × et ÷ avant + et −) au lieu de comparer mot à mot ; un
ordre faux avec les mêmes nombres (« 7 = 8 + 15 ») reste faux.
"""

import re
from collections.abc import Sequence
from fractions import Fraction

_NUMBER = re.compile(r"^\d+(?:[.,]\d+)?$")
_OPERATORS = {
    "+": "+",
    "-": "-",
    "−": "-",
    "–": "-",
    "×": "*",
    "x": "*",
    "*": "*",
    "÷": "/",
    ":": "/",
    "/": "/",
}
# Mots qui relient deux nombres sans ordre (« la somme de 7 et 8 »).
_COMMUTATIVE_WORDS = frozenset({"et", "+", "×", "x", "fois", "plus"})


def is_number(token: str) -> bool:
    return bool(_NUMBER.match(token.strip()))


def _evaluate(tokens: Sequence[str]) -> Fraction | None:
    """Valeur de « nombre signe nombre … » ; `None` si ce n'est pas un calcul."""
    if len(tokens) % 2 == 0:
        return None
    numbers: list[Fraction] = []
    operators: list[str] = []
    for index, token in enumerate(tokens):
        token = token.strip().lower()
        if index % 2 == 0:
            if not is_number(token):
                return None
            numbers.append(Fraction(token.replace(",", ".")))
        elif token in _OPERATORS:
            operators.append(_OPERATORS[token])
        else:
            return None
    # × et ÷ d'abord, puis + et − de gauche à droite.
    terms, signs = [numbers[0]], []
    for operator, number in zip(operators, numbers[1:], strict=True):
        if operator == "*":
            terms[-1] *= number
        elif operator == "/":
            if number == 0:
                return None
            terms[-1] /= number
        else:
            terms.append(number)
            signs.append(operator)
    total = terms[0]
    for sign, term in zip(signs, terms[1:], strict=True):
        total = total + term if sign == "+" else total - term
    return total


def equality_holds(tokens: Sequence[str]) -> bool | None:
    """Vrai si les étiquettes forment une égalité juste (« 8 + 7 = 15 »), faux si elles forment
    une égalité fausse, `None` si ce n'est pas une égalité entre deux calculs."""
    if sum(1 for t in tokens if t.strip() == "=") != 1:
        return None
    middle = [t.strip() for t in tokens].index("=")
    left, right = _evaluate(tokens[:middle]), _evaluate(tokens[middle + 1 :])
    if left is None or right is None:
        return None
    return left == right


def swapped_terms(given: Sequence[str], expected: Sequence[str]) -> bool:
    """Vrai si `given` est `expected` avec deux nombres reliés par « et » (ou +, ×) échangés :
    « la somme de 8 et 7 est 15 » pour « la somme de 7 et 8 est 15 »."""
    if len(given) != len(expected):
        return False
    different = [i for i, (a, b) in enumerate(zip(given, expected, strict=True)) if a != b]
    if len(different) != 2:
        return False
    i, j = different
    return (
        given[i] == expected[j]
        and given[j] == expected[i]
        and is_number(given[i])
        and is_number(given[j])
        and j - i >= 2
        and all(t.lower() in _COMMUTATIVE_WORDS for t in expected[i + 1 : j])
    )
