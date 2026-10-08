"""Ressources des sites éducatifs de confiance (étape 30) : ce que le code décide.

Trois sites, trois façons de faire, toutes dans l'application :

- **MathALÉA** (Coopmaths, logiciel libre AGPL) : des exercices de mathématiques à données
  aléatoires, interactifs. Ludifun ne copie rien : il choisit dans le catalogue public les
  exercices qui correspondent à la leçon et à la classe, et l'application les ouvre dans sa
  visionneuse ; MathALÉA renvoie le score (bonnes réponses sur nombre de questions).
- **Vikidia** (encyclopédie pour enfants, CC BY-SA) : ses quiz (balise `<quiz>`) sont lus, et les
  questions qui parlent d'une notion de la leçon deviennent des questions Ludifun, avec la source
  et la licence ; la page du quiz peut aussi s'ouvrir dans la visionneuse.
- **Lumni** (France Télévisions, droits réservés) : rien n'est copié ; ses vidéos et quiz sur la
  notion sont proposés tels quels, dans la visionneuse.

La visionneuse ne quitte jamais le site de la ressource (`ALLOWED_HOSTS`) : un lien vers un autre
site, une publicité, un réseau social n'est pas ouvert.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import quote, urlsplit

from app.domain.knowledge import Grade, KnowledgeItem, Subject
from app.domain.sources import keywords
from app.domain.text import normalize


class Provider(StrEnum):
    MATHALEA = "mathalea"
    VIKIDIA = "vikidia"
    LUMNI = "lumni"


class ResourceKind(StrEnum):
    EXERCISE = "exercise"  # exercice interactif noté (MathALÉA)
    QUIZ = "quiz"
    VIDEO = "video"
    ARTICLE = "article"


# Sites que la visionneuse peut afficher, par fournisseur (les sous-domaines aussi).
ALLOWED_HOSTS: dict[Provider, tuple[str, ...]] = {
    Provider.MATHALEA: ("coopmaths.fr",),
    Provider.VIKIDIA: ("vikidia.org",),
    Provider.LUMNI: ("lumni.fr",),
}
LICENCES: dict[Provider, str] = {
    Provider.MATHALEA: "MathALÉA, Coopmaths (logiciel libre AGPL)",
    Provider.VIKIDIA: "Vikidia, CC BY-SA 3.0 : contributeurs de Vikidia",
    Provider.LUMNI: "Lumni, France Télévisions (droits réservés, consultation seulement)",
}
PER_PROVIDER = 3  # ressources proposées au plus par site et par leçon


@dataclass(frozen=True)
class Resource:
    provider: Provider
    kind: ResourceKind
    title: str
    url: str
    knowledge_id: str | None = None  # la notion travaillée, si une seule

    @property
    def licence(self) -> str:
        return LICENCES[self.provider]


def host_allowed(url: str, provider: Provider) -> bool:
    """Adresse https du site du fournisseur (ou d'un de ses sous-domaines)."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(
        host == site or host.endswith("." + site) for site in ALLOWED_HOSTS[provider]
    )


# --------------------------------------------------------------------------- #
# MathALÉA : choisir dans le catalogue
# --------------------------------------------------------------------------- #

MATHALEA_URL = "https://coopmaths.fr/alea/"
MATHALEA_QUESTIONS = 5
# Rubriques du catalogue de MathALÉA pour chaque classe (« CAN » : course aux nombres, du calcul
# mental). Avant le CM1, MathALÉA ne propose rien.
MATHALEA_LEVELS: dict[Grade, tuple[str, ...]] = {
    Grade.CM1: ("CM1/CM2", "CAN/CM1/CM2"),
    Grade.CM2: ("CM1/CM2", "CAN/CM1/CM2"),
    Grade.SIXIEME: ("6e", "CAN/6e", "CM1/CM2"),
    Grade.CINQUIEME: ("5e", "CAN/5e"),
    Grade.QUATRIEME: ("4e", "CAN/4e"),
    Grade.TROISIEME: ("3e", "CAN/3e"),
}


@dataclass(frozen=True)
class CatalogueEntry:
    ref: str  # « 6C10-1 »
    uuid: str
    title: str
    rubric: str  # « 6e », « CAN/6e »…
    interactive: bool


def catalogue_entries(referential: dict[str, object], path: str = "") -> list[CatalogueEntry]:
    """Les exercices du référentiel de MathALÉA (JSON imbriqué : rubrique → thème → exercice)."""
    found: list[CatalogueEntry] = []
    for key, value in referential.items():
        if not isinstance(value, dict):
            continue
        if isinstance(value.get("uuid"), str) and isinstance(value.get("titre"), str):
            tags = value.get("tags") if isinstance(value.get("tags"), dict) else {}
            found.append(
                CatalogueEntry(
                    ref=str(value.get("id") or key),
                    uuid=value["uuid"],
                    title=" ".join(value["titre"].split()),
                    rubric=path,
                    interactive=bool(tags.get("interactif")) if isinstance(tags, dict) else False,
                )
            )
        else:
            found += catalogue_entries(value, f"{path}/{key}" if path else key)
    return found


def mathalea_url(entry: CatalogueEntry, questions: int = MATHALEA_QUESTIONS) -> str:
    """Vue élève, exercice interactif, `questions` questions, correction visible après réponse."""
    return (
        f"{MATHALEA_URL}?uuid={quote(entry.uuid)}&id={quote(entry.ref)}&n={questions}&i=1"
        "&v=eleve&es=0111&title=Ludifun"
    )


def _in_rubrics(entry: CatalogueEntry, rubrics: Sequence[str]) -> bool:
    return any(entry.rubric == r or entry.rubric.startswith(r + "/") for r in rubrics)


# Mots des titres d'exercices qui ne disent pas le sujet (« Calculer », « Trouver le nombre ») :
# ils départagent, jamais ils ne suffisent.
_GENERIC = frozenset(
    normalize(w)
    for w in [
        "calculer",
        "calcul",
        "trouver",
        "déterminer",
        "connaître",
        "résoudre",
        "problème",
        "problèmes",
        "écrire",
        "lire",
        "donner",
        "utiliser",
        "comparer",
        "nombre",
        "nombres",
        "entier",
        "entiers",
        "deux",
        "trois",
        "simple",
        "simples",
        "bonne",
        "partir",
        "qcm",
        "exercice",
        "exercices",
        "plus",
        "moins",
        "grand",
        "petit",
        "avec",
        "forme",
        "formes",
    ]
)


def choose_mathalea(
    entries: Iterable[CatalogueEntry],
    subject: str | None,
    grade: str | None,
    title: str | None,
    notions: Sequence[KnowledgeItem],
    limit: int = PER_PROVIDER,
) -> list[Resource]:
    """Exercices interactifs de la classe dont le titre partage un mot du sujet avec la leçon
    (« fraction », « périmètre », « multiplication ») ; les plus proches d'abord."""
    if subject != Subject.MATH:
        return []
    try:
        rubrics = MATHALEA_LEVELS.get(Grade(grade or ""), ())
    except ValueError:
        return []
    lesson_words = keywords(" ".join([title or "", *(f"{n.label} {n.statement}" for n in notions)]))
    scored: list[tuple[int, int, int, CatalogueEntry]] = []
    for position, entry in enumerate(entries):
        if not entry.interactive or not _in_rubrics(entry, rubrics):
            continue
        common = keywords(entry.title) & lesson_words
        strong = len(common - _GENERIC)
        if strong:
            scored.append((strong, len(common), -position, entry))
    scored.sort(reverse=True)
    chosen: list[Resource] = []
    seen: set[str] = set()
    for *_, entry in scored:
        if normalize(entry.title) in seen:
            continue
        seen.add(normalize(entry.title))
        chosen.append(Resource(Provider.MATHALEA, ResourceKind.EXERCISE, entry.title, mathalea_url(entry)))
        if len(chosen) == limit:
            break
    return chosen


# --------------------------------------------------------------------------- #
# Vikidia : lire les quiz (balise <quiz> des wikis)
# --------------------------------------------------------------------------- #

_QUIZ = re.compile(r"<quiz[^>]*>(.*?)</quiz>", re.DOTALL | re.IGNORECASE)
_QUESTION = re.compile(r"\{(?P<text>[^{}]*?)\s*\|\s*type\s*=\s*\"(?P<type>[^\"]*)\"\s*\}", re.DOTALL)
_LINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")
_EXTERNAL = re.compile(r"\[https?://\S+\s+([^\]]*)\]")
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_TAGS = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>|<[^>]+>", re.DOTALL)


@dataclass(frozen=True)
class QuizQuestion:
    text: str
    right: list[str]
    wrong: list[str] = field(default_factory=list)


def clean_wiki(text: str) -> str:
    """Texte lisible : liens, gras, modèles et balises retirés."""
    text = _TEMPLATE.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _EXTERNAL.sub(r"\1", text)
    text = _TAGS.sub("", text)
    text = text.replace("'''", "").replace("''", "")
    return " ".join(text.split()).strip()


def parse_quiz(wikitext: str) -> list[QuizQuestion]:
    """Questions à une seule bonne réponse (« () ») des quiz de la page ; les autres types
    (plusieurs réponses, réponse à écrire) ne sont pas repris."""
    questions: list[QuizQuestion] = []
    for block in _QUIZ.findall(wikitext):
        matches = list(_QUESTION.finditer(block))
        for i, match in enumerate(matches):
            if match.group("type").strip() != "()":
                continue
            end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
            right: list[str] = []
            wrong: list[str] = []
            for line in block[match.end() : end].splitlines():
                line = line.strip()
                if line.startswith(("+", "-")) and not line.startswith("||"):
                    answer = clean_wiki(line[1:].split("||")[0])
                    if answer:
                        (right if line[0] == "+" else wrong).append(answer)
            text = clean_wiki(match.group("text"))
            if text and len(right) == 1:
                questions.append(QuizQuestion(text, right, wrong))
    return questions


@dataclass(frozen=True)
class QuizMaterial:
    """Une question du quiz pour une notion, prête à passer les contrôles du matériel."""

    knowledge_id: str
    question: dict[str, object]  # énoncé, réponse, distracteurs (forme du matériel)


def quiz_material(questions: Sequence[QuizQuestion], notions: Sequence[KnowledgeItem]) -> list[QuizMaterial]:
    """Chaque question à quatre réponses ou plus va à la notion dont elle partage le plus de mots
    importants (un au moins) ; les « vrai ou faux » et les questions hors leçon sont laissées. Les
    contrôles du matériel (`check_question`) restent à passer."""
    topics = [(n.id, keywords(f"{n.label} {n.statement}")) for n in notions]
    found: list[QuizMaterial] = []
    for q in questions:
        if len(q.wrong) < 3:
            continue
        words = keywords(f"{q.text} {q.right[0]}")
        best = max(topics, key=lambda t: len(t[1] & words), default=None)
        if best is not None and best[1] & words:
            found.append(
                QuizMaterial(
                    best[0],
                    {"difficulty": 1, "stem": q.text, "answer": q.right[0], "distractors": q.wrong[:3]},
                )
            )
    return found


def vikidia_page_url(title: str) -> str:
    return "https://fr.vikidia.org/wiki/" + quote(title.replace(" ", "_"))


# --------------------------------------------------------------------------- #
# Lumni : vidéos et quiz proposés tels quels
# --------------------------------------------------------------------------- #


def lumni_resource(url: str, title: str) -> Resource | None:
    """Une page Lumni utile à l'enfant (vidéo, quiz, article), sinon None (menus, recherche…)."""
    if not host_allowed(url, Provider.LUMNI):
        return None
    path = urlsplit(url).path
    kind = (
        ResourceKind.VIDEO
        if path.startswith("/video/")
        else ResourceKind.QUIZ
        if path.startswith("/quiz/")
        else ResourceKind.ARTICLE
        if path.startswith(("/article/", "/dossier/"))
        else None
    )
    title = " ".join(re.sub(r"\s*[-|–—]\s*Lumni.*$", "", title).split())
    return Resource(Provider.LUMNI, kind, title or "Lumni", url) if kind and title else None
