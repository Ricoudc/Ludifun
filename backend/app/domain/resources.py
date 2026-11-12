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
- **Les Fondamentaux** (Réseau Canopé, opérateur du ministère de l'Éducation nationale, droits
  réservés) : des films d'animation du CP à la 6e, proposés tels quels.
- **Maître Lucas** (site gratuit d'enseignants, du CP au CM2, sans licence de réutilisation
  publiée) : rien n'est copié ni lu par l'IA ; ses pages de leçon (vidéo, fiche) sont proposées
  telles quelles, comme un lien.

- **Calcul@TICE** (académie de Lille, avec Sésamath) : des jeux de calcul mental du CP à la 6e,
  pour les leçons de mathématiques.
- **Sésamath** (manuels libres du collège) : les pages du manuel en ligne sur la notion ; ses
  cahiers PDF servent aussi aux explications et questions « D'après… » (`sources.DEFAULT_SITES`).

- **Les sites choisis par la famille** (§5.60) : Logiciel Éducatif et Bout de Gomme (exercices
  et jeux de l'école), Mathador (calcul mental), Khan Academy en français (vidéos et exercices
  de maths), La Main à la Pâte et l'Espace Juniors de la Cité des sciences (sciences),
  Vie-publique et Géoconfluences (éducation civique, géographie, au collège), Annabac (fiches
  du brevet) et les partenaires d'Éduthèque ouverts sans compte (Louvre, BnF, INA, CNES,
  Météo-France, château de Versailles). Tous en consultation : rien n'est copié.

Pour ces sites, le moteur de recherche du serveur trouve les pages ; le code ne garde que celles
qui parlent de la leçon (`linked_resource`). Un PDF n'est jamais proposé dans la visionneuse (le
téléphone ne l'affiche pas) : il sert seulement de source de texte.

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
    FONDAMENTAUX = "fondamentaux"
    MAITRE_LUCAS = "maitrelucas"
    CALCULATICE = "calculatice"
    SESAMATH = "sesamath"
    LOGICIEL_EDUCATIF = "logicieleducatif"
    BOUT_DE_GOMME = "boutdegomme"
    MATHADOR = "mathador"
    KHAN_ACADEMY = "khanacademy"
    LAMAP = "lamap"
    CITE_SCIENCES = "citesciences"
    VIE_PUBLIQUE = "viepublique"
    GEOCONFLUENCES = "geoconfluences"
    ANNABAC = "annabac"
    LOUVRE = "louvre"
    BNF = "bnf"
    INA = "ina"
    CNES = "cnes"
    METEO_FRANCE = "meteofrance"
    VERSAILLES = "versailles"


class ResourceKind(StrEnum):
    EXERCISE = "exercise"  # exercice interactif noté (MathALÉA)
    QUIZ = "quiz"
    VIDEO = "video"
    ARTICLE = "article"
    LESSON = "lesson"  # une page de leçon, souvent avec sa vidéo (Maître Lucas, Sésamath)
    GAME = "game"  # un jeu d'entraînement en ligne, non noté par Ludifun (Calcul@TICE)


# Sites que la visionneuse peut afficher, par fournisseur (les sous-domaines aussi).
ALLOWED_HOSTS: dict[Provider, tuple[str, ...]] = {
    Provider.MATHALEA: ("coopmaths.fr",),
    Provider.VIKIDIA: ("vikidia.org",),
    Provider.LUMNI: ("lumni.fr",),
    Provider.FONDAMENTAUX: ("reseau-canope.fr",),
    Provider.MAITRE_LUCAS: ("maitrelucas.fr",),
    Provider.CALCULATICE: ("calculatice.ac-lille.fr",),
    Provider.SESAMATH: ("sesamath.net",),
    Provider.LOGICIEL_EDUCATIF: ("logicieleducatif.fr",),
    Provider.BOUT_DE_GOMME: ("boutdegomme.fr",),
    Provider.MATHADOR: ("mathador.fr",),
    Provider.KHAN_ACADEMY: ("fr.khanacademy.org",),
    Provider.LAMAP: ("fondation-lamap.org",),
    Provider.CITE_SCIENCES: ("cite-sciences.fr",),
    Provider.VIE_PUBLIQUE: ("vie-publique.fr",),
    Provider.GEOCONFLUENCES: ("geoconfluences.ens-lyon.fr",),
    Provider.ANNABAC: ("annabac.com",),
    Provider.LOUVRE: ("louvre.fr",),
    Provider.BNF: ("bnf.fr",),
    Provider.INA: ("ina.fr",),
    Provider.CNES: ("cnes.fr",),
    Provider.METEO_FRANCE: ("meteofrance.com", "meteofrance.fr"),
    Provider.VERSAILLES: ("chateauversailles.fr",),
}
LICENCES: dict[Provider, str] = {
    Provider.MATHALEA: "MathALÉA, Coopmaths (logiciel libre AGPL)",
    Provider.VIKIDIA: "Vikidia, CC BY-SA 3.0 : contributeurs de Vikidia",
    Provider.LUMNI: "Lumni, France Télévisions (droits réservés, consultation seulement)",
    Provider.FONDAMENTAUX: "Les Fondamentaux, Réseau Canopé (droits réservés, consultation seulement)",
    Provider.MAITRE_LUCAS: "Maître Lucas (consultation seulement, rien n'est copié)",
    Provider.CALCULATICE: "Calcul@TICE, académie de Lille et Sésamath (exercices en ligne)",
    Provider.SESAMATH: "Sésamath, association de professeurs de mathématiques (licence libre)",
    Provider.LOGICIEL_EDUCATIF: "Logiciel Éducatif (jeux en ligne, consultation seulement)",
    Provider.BOUT_DE_GOMME: "Bout de Gomme, enseignante (consultation seulement, rien n'est copié)",
    Provider.MATHADOR: "Mathador, Réseau Canopé (consultation seulement)",
    Provider.KHAN_ACADEMY: "Khan Academy en français (CC BY-NC-SA, consultation)",
    Provider.LAMAP: "Fondation La Main à la Pâte (consultation seulement)",
    Provider.CITE_SCIENCES: "Cité des sciences et de l'industrie, Espace Juniors (consultation)",
    Provider.VIE_PUBLIQUE: "Vie-publique.fr, Direction de l'information légale et administrative",
    Provider.GEOCONFLUENCES: "Géoconfluences, ENS de Lyon et ministère de l'Éducation nationale",
    Provider.ANNABAC: "Annabac, Hatier (fiches gratuites, consultation seulement)",
    Provider.LOUVRE: "Musée du Louvre, partenaire d'Éduthèque (consultation seulement)",
    Provider.BNF: "Bibliothèque nationale de France, partenaire d'Éduthèque (consultation)",
    Provider.INA: "INA, partenaire d'Éduthèque (consultation seulement)",
    Provider.CNES: "CNES, partenaire d'Éduthèque (consultation seulement)",
    Provider.METEO_FRANCE: "Météo-France, partenaire d'Éduthèque (consultation seulement)",
    Provider.VERSAILLES: "Château de Versailles, partenaire d'Éduthèque (consultation seulement)",
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


# --------------------------------------------------------------------------- #
# Les Fondamentaux, Maître Lucas : des pages proposées telles quelles
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LinkedSite:
    provider: Provider
    sites: tuple[str, ...]  # pour le moteur de recherche
    search: str  # ajouté à la recherche (« les fondamentaux »)
    grades: frozenset[Grade]  # classes pour lesquelles le site est fait
    path: str = "/"  # seules les pages sous ce chemin
    site_name: str = ""  # retiré de la fin des titres
    subjects: frozenset[Subject] | None = None  # matières de la leçon ; None : toutes
    query: re.Pattern[str] | None = None  # adresses avec « ? » acceptées si la requête correspond
    kind: ResourceKind | None = None  # type imposé (sinon vidéo ou leçon, selon la page)


PRIMARY = frozenset({Grade.CP, Grade.CE1, Grade.CE2, Grade.CM1, Grade.CM2})
COLLEGE = frozenset({Grade.SIXIEME, Grade.CINQUIEME, Grade.QUATRIEME, Grade.TROISIEME})
CYCLE_3 = frozenset({Grade.CM1, Grade.CM2, Grade.SIXIEME})
ALL_GRADES = PRIMARY | COLLEGE
SCIENCES = frozenset({Subject.SCIENCE})
LINKED_SITES = (
    LinkedSite(
        Provider.FONDAMENTAUX,
        ("www.reseau-canope.fr",),
        "les fondamentaux canopé",
        PRIMARY | {Grade.SIXIEME},
        path="/lesfondamentaux/",
        site_name="Les fondamentaux",
    ),
    LinkedSite(
        Provider.MAITRE_LUCAS,
        ("www.maitrelucas.fr", "maitrelucas.fr"),
        "maître lucas",
        PRIMARY,
        site_name="Maître Lucas",
    ),
    LinkedSite(
        Provider.CALCULATICE,
        ("calculatice.ac-lille.fr",),
        "calcul@tice calcul mental",
        PRIMARY | {Grade.SIXIEME},
        site_name="Calcul@TICE",
        subjects=frozenset({Subject.MATH}),
        query=re.compile(r"^article\d+$"),  # SPIP : « spip.php?article123 », pas les rubriques
        kind=ResourceKind.GAME,
    ),
    LinkedSite(
        Provider.SESAMATH,
        ("manuel.sesamath.net", "mathenpoche.sesamath.net", "sesamath.net"),
        "sésamath manuel",
        frozenset({Grade.SIXIEME, Grade.CINQUIEME, Grade.QUATRIEME, Grade.TROISIEME}),
        site_name="Sésamath",
        subjects=frozenset({Subject.MATH}),
        query=re.compile(r"(^|&)(ouvrage|page|chapitre|exo|exercice|id)="),  # manuel numérique
        kind=ResourceKind.LESSON,
    ),
    # Les sites choisis par la famille (§5.60), du plus proche de l'école au plus général.
    LinkedSite(
        Provider.LOGICIEL_EDUCATIF,
        ("www.logicieleducatif.fr",),
        "logiciel éducatif jeu",
        PRIMARY,
        site_name="Logiciel Éducatif",
        subjects=frozenset({Subject.FRENCH, Subject.MATH, Subject.ENGLISH, Subject.GEOGRAPHY}),
        kind=ResourceKind.GAME,
    ),
    LinkedSite(
        Provider.BOUT_DE_GOMME,
        ("www.boutdegomme.fr", "boutdegomme.fr"),
        "bout de gomme exercices",
        PRIMARY,
        site_name="Bout de Gomme",
        kind=ResourceKind.LESSON,  # fiches d'exercices et leçons de l'école
    ),
    LinkedSite(
        Provider.MATHADOR,
        ("www.mathador.fr", "mathador.fr"),
        "mathador calcul mental",
        frozenset({Grade.CE2, Grade.CM1, Grade.CM2, Grade.SIXIEME, Grade.CINQUIEME}),
        site_name="Mathador",
        subjects=frozenset({Subject.MATH}),
        kind=ResourceKind.GAME,
    ),
    LinkedSite(
        Provider.KHAN_ACADEMY,
        ("fr.khanacademy.org",),
        "khan academy",
        ALL_GRADES,
        site_name="Khan Academy",
        subjects=frozenset({Subject.MATH}),
    ),
    LinkedSite(
        Provider.LAMAP,
        ("fondation-lamap.org", "www.fondation-lamap.org"),
        "la main à la pâte",
        PRIMARY | {Grade.SIXIEME, Grade.CINQUIEME},
        site_name="La main à la pâte",
        subjects=SCIENCES,
    ),
    LinkedSite(
        Provider.CITE_SCIENCES,
        ("www.cite-sciences.fr",),
        "cité des sciences juniors",
        PRIMARY | {Grade.SIXIEME},
        site_name="Cité des sciences",
        subjects=SCIENCES,
    ),
    LinkedSite(
        Provider.VIE_PUBLIQUE,
        ("www.vie-publique.fr",),
        "vie publique fiche",
        COLLEGE,
        site_name="Vie publique",
        subjects=frozenset({Subject.CIVICS, Subject.HISTORY}),
        kind=ResourceKind.ARTICLE,
    ),
    LinkedSite(
        Provider.GEOCONFLUENCES,
        ("geoconfluences.ens-lyon.fr",),
        "géoconfluences",
        frozenset({Grade.QUATRIEME, Grade.TROISIEME}),
        site_name="Géoconfluences",
        subjects=frozenset({Subject.GEOGRAPHY}),
        kind=ResourceKind.ARTICLE,
    ),
    LinkedSite(
        Provider.ANNABAC,
        ("www.annabac.com",),
        "annabac brevet fiche",
        frozenset({Grade.QUATRIEME, Grade.TROISIEME}),
        site_name="Annabac",
        kind=ResourceKind.LESSON,
    ),
    # Partenaires d'Éduthèque dont les pages s'ouvrent sans compte enseignant.
    LinkedSite(
        Provider.LOUVRE,
        ("www.louvre.fr", "collections.louvre.fr"),
        "louvre",
        CYCLE_3 | COLLEGE,
        site_name="Louvre",
        subjects=frozenset({Subject.HISTORY, Subject.OTHER}),
        kind=ResourceKind.ARTICLE,
    ),
    LinkedSite(
        Provider.BNF,
        ("essentiels.bnf.fr", "classes.bnf.fr", "expositions.bnf.fr"),
        "bnf",
        CYCLE_3 | COLLEGE,
        site_name="BnF",
        subjects=frozenset({Subject.FRENCH, Subject.HISTORY}),
        kind=ResourceKind.ARTICLE,
    ),
    LinkedSite(
        Provider.INA,
        ("fresques.ina.fr", "www.ina.fr"),
        "ina vidéo",
        CYCLE_3 | COLLEGE,
        site_name="INA",
        subjects=frozenset({Subject.HISTORY, Subject.CIVICS, Subject.GEOGRAPHY}),
        kind=ResourceKind.VIDEO,
    ),
    LinkedSite(
        Provider.CNES,
        ("cnes.fr",),
        "cnes espace",
        ALL_GRADES,
        site_name="CNES",
        subjects=SCIENCES,
        kind=ResourceKind.ARTICLE,
    ),
    LinkedSite(
        Provider.METEO_FRANCE,
        ("meteofrance.com", "meteofrance.fr"),
        "météo-france comprendre",
        ALL_GRADES,
        site_name="Météo-France",
        subjects=frozenset({Subject.SCIENCE, Subject.GEOGRAPHY}),
        kind=ResourceKind.ARTICLE,
    ),
    LinkedSite(
        Provider.VERSAILLES,
        ("www.chateauversailles.fr",),
        "château de versailles",
        CYCLE_3 | COLLEGE,
        site_name="Château de Versailles",
        subjects=frozenset({Subject.HISTORY}),
        kind=ResourceKind.ARTICLE,
    ),
)
# Pages de navigation, jamais une leçon.
_NAVIGATION = re.compile(r"/(recherche|search|tag|tags|categorie|category|page|auteur|author|contact)(/|$)")


def linked_resource(site: LinkedSite, url: str, title: str, topic: Iterable[str]) -> Resource | None:
    """Une page du site qui parle de la leçon (un mot du titre de la page dans `topic`), sinon
    None : accueil, recherche, catégories, autre site, page sans rapport."""
    if not host_allowed(url, site.provider):
        return None
    parts = urlsplit(url)
    path = parts.path or "/"
    query_ok = not parts.query or (site.query is not None and site.query.search(parts.query) is not None)
    if (
        not query_ok
        or not path.startswith(site.path)
        or path.lower().endswith(".pdf")  # la visionneuse du téléphone n'affiche pas les PDF
        or (path.rstrip("/") == site.path.rstrip("/") and not parts.query)
        or _NAVIGATION.search(path)
    ):
        return None
    if site.site_name:
        title = re.sub(rf"\s*[-|–—:]\s*{re.escape(site.site_name)}.*$", "", title, flags=re.IGNORECASE)
    title = " ".join(title.split())
    if not title or not keywords(title) & set(topic):
        return None
    video = site.provider is Provider.FONDAMENTAUX or "video" in normalize(f"{path} {title}")
    kind = site.kind or (ResourceKind.VIDEO if video else ResourceKind.LESSON)
    return Resource(site.provider, kind, title, url)
