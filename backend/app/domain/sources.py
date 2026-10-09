"""Sources externes (étape 24, cahier des charges complet §116-117) : ce que le code décide.

Ludifun cherche, l'IA lit. Le code choisit les sites autorisés, découpe les pages en extraits,
garde les plus proches de la question et vérifie que chaque citation de l'IA figure vraiment dans
l'extrait qu'elle cite. Une information qui n'a pas de citation vérifiée n'est jamais montrée ;
une information retenue reste marquée comme un apport externe (`SOURCE_EXTERNAL_KNOWLEDGE`),
jamais comme venant de la leçon.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.domain.child_safety import unsafe_reason
from app.domain.text import fuzzy_contains, normalize

# Sites éducatifs de confiance, du plus adapté aux enfants au plus général. Modifiable par
# LUDIFUN_WEB_SOURCES ; un sous-domaine d'un site autorisé l'est aussi.
DEFAULT_SITES = (
    "fr.vikidia.org",
    "www.lumni.fr",
    "eduscol.education.gouv.fr",
    "www.education.gouv.fr",
    "sesamath.net",  # manuels et cahiers libres du collège (pages et PDF)
    "fr.wikipedia.org",
)
EXCERPT_CHARS = 800  # un extrait : quelques paragraphes, assez court pour une petite IA locale
MIN_PARAGRAPH = 60  # en dessous : titre, légende ou menu, rattaché au suivant
MAX_ANSWER = 600
MIN_QUOTE = 15  # une citation trop courte (« en 1789 ») ne prouve rien

# Mots vides : ils ne disent rien du sujet de la question.
_STOP = {
    normalize(w)
    for w in [
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "du",
        "de",
        "d",
        "l",
        "au",
        "aux",
        "et",
        "ou",
        "en",
        "a",
        "à",
        "est",
        "sont",
        "pour",
        "par",
        "sur",
        "dans",
        "que",
        "qui",
        "quoi",
        "quel",
        "quelle",
        "quels",
        "quelles",
        "comment",
        "pourquoi",
        "ce",
        "cet",
        "cette",
        "ces",
        "il",
        "elle",
        "ils",
        "elles",
        "on",
        "se",
        "sa",
        "son",
        "ses",
        "leur",
        "leurs",
        "ne",
        "pas",
        "plus",
        "avec",
        "sans",
        "y",
        "t",
    ]
}
_WORD = re.compile(r"[\wÀ-ÖØ-öø-ÿ]+")


@dataclass(frozen=True)
class Excerpt:
    """Un extrait numéroté d'une page d'un site autorisé, donné à lire à l'IA."""

    number: int
    url: str
    title: str
    text: str

    @property
    def site(self) -> str:
        return site_of(self.url)


@dataclass(frozen=True)
class Quote:
    source: int  # numéro de l'extrait cité
    text: str


@dataclass(frozen=True)
class SourcedAnswer:
    """Réponse retenue : chaque source affichée a au moins une citation vérifiée."""

    text: str
    sources: list[Excerpt]
    quotes: list[Quote]
    origin: str = "SOURCE_EXTERNAL_KNOWLEDGE"  # §117 : jamais confondu avec la leçon


def site_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def allowed(url: str, sites: Iterable[str]) -> bool:
    """Page en https d'un site autorisé (ou d'un de ses sous-domaines)."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host:
        return False
    return any(host == site or host.endswith("." + site) for site in sites)


def search_words(text: str) -> list[str]:
    """Les mots utiles d'une question, accents gardés (pour la recherche plein texte)."""
    words = re.findall(r"[a-zà-öø-ÿ0-9]+", text.lower())
    return sorted({w for w in words if len(w) > 1 and normalize(w) not in _STOP})


def _singular(word: str) -> str:
    """Pluriel simple ramené au singulier (« éruptions » → « éruption »), pour comparer les mots."""
    return word[:-1] if len(word) > 4 and word[-1] in "sx" else word


def keywords(text: str) -> set[str]:
    return {_singular(w) for w in _WORD.findall(normalize(text)) if w not in _STOP and len(w) > 1}


def passages(text: str, max_chars: int = EXCERPT_CHARS) -> list[str]:
    """Paragraphes regroupés en passages d'au plus `max_chars` signes (un paragraphe trop long
    est coupé à la fin d'une phrase)."""
    chunks: list[str] = []
    pending = ""
    for raw in re.split(r"\n\s*\n|\n", text):
        paragraph = " ".join(raw.split())
        if not paragraph:
            continue
        paragraph = pending + (" " if pending else "") + paragraph
        if len(paragraph) < MIN_PARAGRAPH:
            pending = paragraph
            continue
        pending = ""
        while len(paragraph) > max_chars:
            cut = paragraph.rfind(". ", 0, max_chars)
            cut = cut + 1 if cut > max_chars // 3 else max_chars
            chunks.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        chunks.append(paragraph)
    if pending:
        chunks.append(pending)
    return chunks


_SENTENCE = re.compile(r"[a-zà-öø-ÿ0-9)»\"]\s*[.!?](\s|$)", re.IGNORECASE)
# Mots qui annoncent une cause ou une date : ils répondent à « pourquoi » et à « quand ».
_WHY = {"car", "parce", "cause", "raison", "crise", "afin", "pour", "dette", "endette", "argent", "faute"}
_WHEN = re.compile(r"\b(1\d{3}|20\d{2}|siecle)\b")


def is_prose(passage: str) -> bool:
    """Un vrai paragraphe : au moins 8 mots et une phrase terminée. Écarte menus, légendes,
    fils d'Ariane et métadonnées (« En savoir plus Histoire05:52 Publié le… »)."""
    return len(passage.split()) >= 8 and _SENTENCE.search(passage) is not None


def _bonus(question: str, passage: str) -> float:
    asked = normalize(question)
    words = set(normalize(passage).split())
    if asked.startswith("pourquoi") and words & _WHY:
        return 0.3
    if asked.startswith(("quand", "en quelle annee")) and _WHEN.search(normalize(passage)):
        return 0.3
    return 0.0


def best_excerpts(
    question: str, pages: Sequence[tuple[str, str, str]], count: int = 3, max_chars: int = EXCERPT_CHARS
) -> list[Excerpt]:
    """Les `count` passages qui partagent le plus de mots avec la question (une cause pour
    « pourquoi », une date pour « quand »), au plus deux par page pour varier les sources.
    `pages` : (adresse, titre, texte), dans l'ordre de préférence."""
    wanted = keywords(question)
    scored: list[tuple[float, int, int, str, str, str]] = []
    for rank, (url, title, text) in enumerate(pages):
        for position, passage in enumerate(passages(text, max_chars)):
            common = len(wanted & keywords(passage))
            if common and is_prose(passage):
                # À égalité : la page la mieux classée, puis le début de la page (l'essentiel).
                score = common / len(wanted) + _bonus(question, passage)
                scored.append((score, -rank, -position, url, title, passage))
    scored.sort(reverse=True)
    chosen: list[Excerpt] = []
    per_page: dict[str, int] = {}
    for _, _, _, url, title, passage in scored:
        if per_page.get(url, 0) >= 2:
            continue
        per_page[url] = per_page.get(url, 0) + 1
        chosen.append(Excerpt(len(chosen) + 1, url, title, passage))
        if len(chosen) == count:
            break
    return chosen


def check_answer(
    answer: str, quotes: Sequence[Quote], excerpts: Sequence[Excerpt], found: bool
) -> SourcedAnswer | None:
    """La réponse n'est gardée que si l'IA dit l'avoir trouvée dans les extraits et qu'au moins
    une citation figure vraiment dans l'extrait cité. Seules les sources vérifiées sont montrées."""
    text = " ".join(answer.split())
    if not found or not text or len(text) > MAX_ANSWER:
        return None
    if unsafe_reason(text, [e.text for e in excerpts]) is not None:
        return None  # §141 : rien d'inadapté qui ne viendrait pas des extraits
    by_number = {e.number: e for e in excerpts}
    verified = [
        Quote(q.source, " ".join(q.text.split()))
        for q in quotes
        if q.source in by_number
        and len(q.text.strip()) >= MIN_QUOTE
        and fuzzy_contains(by_number[q.source].text, q.text)
    ]
    if not verified:
        return None
    used = sorted({q.source for q in verified})
    return SourcedAnswer(text, [by_number[n] for n in used], verified)
