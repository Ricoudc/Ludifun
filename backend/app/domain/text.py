"""Outils de texte partagés : normalisation, distance d'édition, recherche approximative."""

import html
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

_PUNCTUATION = re.compile(r"[^\w\s/]", re.UNICODE)
_SPACES = re.compile(r"\s+")
# « 7 × 8 », « 7x8 », « 7 * 8 » : le même produit, quelle que soit l'écriture (photo ou IA).
_TIMES = re.compile(r"(\d)\s*[x×*]\s*(?=\d)")
_INTEGER = re.compile(r"^-?\d+$")
_DECIMAL = re.compile(r"^-?\d+([.,]\d+)?$")
_FRACTION = re.compile(r"^\d+\s?/\s?\d+$")
_MONTHS = (
    "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
)  # fmt: skip


# Mise en forme que l'IA (ou la lecture de la photo) glisse parfois dans le texte : « 3<sup>e</sup> »,
# « <b>mot</b> », « **mot** », « &nbsp; ». L'application affiche du texte brut : on n'en garde
# que les lettres (« 3e », « mot »).
_LINE_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(\s[^<>]*)?/?>")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINE_SPACES = re.compile(r"[ \t\u00a0]{2,}")


def strip_markup(text: str) -> str:
    """Texte sans balises HTML ni gras Markdown, entités décodées. « 3<sup>e</sup> » → « 3e »."""
    if "<" not in text and "&" not in text and "**" not in text:
        return text
    text = _LINE_BREAK.sub(" ", text)
    text = _TAG.sub("", text)
    text = _BOLD.sub(r"\1", text)
    text = html.unescape(text).replace("\u00a0", " ")
    return _LINE_SPACES.sub(" ", text)


def clean_markup(value: Any) -> Any:
    """`strip_markup` sur toutes les chaînes d'une structure JSON (dictionnaires, listes)."""
    if isinstance(value, str):
        return strip_markup(value)
    if isinstance(value, dict):
        return {key: clean_markup(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_markup(item) for item in value]
    return value


# Typographie française : « ? », « ! », « ; » et « » » jamais seuls en début de ligne. L'espace
# déjà écrite devant devient insécable (fine devant ! ? ;), rien n'est ajouté ni retiré.
_BEFORE_THIN = re.compile(r"[ \u00a0\u202f]+(?=[!?;])")
_BEFORE_COLON = re.compile(r"[ \u00a0\u202f]+(?=[:»])")
_AFTER_GUILLEMET = re.compile(r"(?<=«)[ \u00a0\u202f]+")


def french_spacing(text: str) -> str:
    """« Quelle année ? » → l'espace devant « ? » insécable, pour l'affichage seulement : la
    leçon et les réponses enregistrées gardent leur texte."""
    if not any(c in text for c in "!?;:«»"):
        return text
    text = _BEFORE_THIN.sub("\u202f", text)
    text = _BEFORE_COLON.sub("\u00a0", text)
    return _AFTER_GUILLEMET.sub("\u00a0", text)


def display_text(value: Any) -> Any:
    """Ce que voit l'enfant : sans balises (`clean_markup`), avec la typographie française, sur
    toutes les chaînes d'une structure JSON."""
    if isinstance(value, str):
        return french_spacing(strip_markup(value))
    if isinstance(value, dict):
        return {key: display_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [display_text(item) for item in value]
    return value


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize(text: str) -> str:
    """Minuscules, sans accents ni ponctuation, espaces réduits. « L'État. » → « l etat »."""
    text = strip_accents(text.lower()).replace("’", "'").replace("_", " ")
    text = _TIMES.sub(r"\1 x ", text)
    text = _PUNCTUATION.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def is_numeric(text: str) -> bool:
    return bool(_DECIMAL.match(text.strip().replace(" ", "")))


def nature(text: str) -> str:
    """Nature d'une réponse, pour vérifier que les distracteurs lui ressemblent.

    year (4 chiffres), number, fraction, date (« 14 juillet 1789 ») ou text.
    """
    compact = text.strip().replace(" ", " ")
    if _INTEGER.match(compact) and len(compact.lstrip("-")) == 4:
        return "year"
    if _DECIMAL.match(compact.replace(" ", "")):
        return "number"
    if _FRACTION.match(compact):
        return "fraction"
    words = normalize(compact).split()
    if any(w in _MONTHS for w in words) and any(w.isdigit() for w in words):
        return "date"
    return "text"


def compatible_natures(answer: str, distractor: str) -> bool:
    a, d = nature(answer), nature(distractor)
    if a == "year":
        # Une année peut avoir pour distracteur une année à 3 chiffres (ex. 476).
        return d == "year" or (d == "number" and _INTEGER.match(distractor.strip()) is not None)
    return a == d


def damerau_levenshtein(a: str, b: str) -> int:
    """Distance d'édition avec transposition de deux lettres voisines (variante OSA)."""
    previous_previous: list[int] = []
    previous = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        current = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                current[j] = min(current[j], previous_previous[j - 2] + 1)
        previous_previous, previous = previous, current
    return previous[len(b)]


def allowed_typos(expected: str) -> int:
    """Fautes tolérées (§9.1) : aucune jusqu'à 4 caractères, 1 jusqu'à 8, 2 au-delà ; nombres exacts."""
    if is_numeric(expected):
        return 0
    length = len(expected)
    if length <= 4:
        return 0
    if length <= 8:
        return 1
    return 2


def matches_with_typos(given: str, expected: str) -> bool:
    g, e = normalize(given), normalize(expected)
    if not g:
        return False
    return g == e or damerau_levenshtein(g, e) <= allowed_typos(e)


def contains_words(haystack: str, needle: str) -> bool:
    """`needle` apparaît comme suite de mots entiers dans `haystack` (texte normalisé)."""
    h, n = f" {normalize(haystack)} ", f" {normalize(needle)} "
    return n.strip() != "" and n in h


def gives_away(left: str, right: str) -> bool:
    """Les deux côtés d'une paire à relier se trahissent : identiques, ou l'un contient l'autre
    (« Tu » ↔ « Tu vois bien… »). Il n'y a alors rien à chercher."""
    return normalize(left) == normalize(right) or contains_words(left, right) or contains_words(right, left)


def fuzzy_contains(text: str, excerpt: str, min_ratio: float = 0.9) -> bool:
    """L'extrait figure dans le texte, à 10 % d'écart près (erreurs d'OCR)."""
    norm_text, norm_excerpt = normalize(text), normalize(excerpt)
    if not norm_excerpt:
        return False
    if norm_excerpt in norm_text:
        return True
    words, size = norm_text.split(), len(norm_excerpt.split())
    for width in (size - 1, size, size + 1):
        if width < 1:
            continue
        for start in range(max(1, len(words) - width + 1)):
            window = " ".join(words[start : start + width])
            if SequenceMatcher(None, window, norm_excerpt).ratio() >= min_ratio:
                return True
    return False
