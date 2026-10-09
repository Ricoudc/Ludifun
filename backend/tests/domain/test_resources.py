"""Étape 30 : ressources des sites de confiance. MathALÉA : choisir dans le catalogue ; Vikidia :
lire les quiz ; Lumni : reconnaître une vidéo ou un quiz ; la visionneuse reste sur le site."""

import pytest

from app.domain.knowledge import Grade, KnowledgeItem
from app.domain.resources import (
    CatalogueEntry,
    Provider,
    ResourceKind,
    catalogue_entries,
    choose_mathalea,
    clean_wiki,
    host_allowed,
    lumni_resource,
    mathalea_url,
    parse_quiz,
    quiz_material,
    vikidia_page_url,
)

# Extrait du référentiel de MathALÉA (même forme que le JSON public).
REFERENTIAL = {
    "CAN": {
        "CM1/CM2": {
            "c3C": {
                "canc3C03": {
                    "id": "canc3C03",
                    "uuid": "bdb11",
                    "titre": "Trouver le nombre dans une table de multiplication",
                    "tags": {"interactif": True},
                },
                "canc3C04": {
                    "id": "canc3C04",
                    "uuid": "aaa11",
                    "titre": "Calculer le double",
                    "tags": {"interactif": True},
                },
            }
        },
        "6e": {
            "6M": {
                "can6M06": {
                    "id": "can6M06",
                    "uuid": "e52ba",
                    "titre": "Calculer le périmètre d’une figure",
                    "tags": {"interactif": True},
                }
            }
        },
    },
    "CM1/CM2": {
        "c3C2": {
            "c3C20": {
                "id": "c3C20",
                "uuid": "f0f0f",
                "titre": "Opérations simples avec des fractions",
                "tags": {"interactif": True},
            },
            "c3C21": {
                "id": "c3C21",
                "uuid": "f1f1f",
                "titre": "Colorier des fractions",
                "tags": {"interactif": False},
            },
        }
    },
}


def notion(key: str, label: str, statement: str) -> KnowledgeItem:
    return KnowledgeItem(
        id=key,
        type="term",
        label=label,
        statement=statement,
        importance=3,
        attributes={"definition": statement},
        source_excerpt=statement,
    )


def test_the_catalogue_is_read_with_its_rubrics() -> None:
    entries = catalogue_entries(REFERENTIAL)
    assert len(entries) == 5
    table = next(e for e in entries if e.ref == "canc3C03")
    assert table.rubric == "CAN/CM1/CM2/c3C" and table.interactive and table.uuid == "bdb11"


def test_mathalea_exercises_match_the_lesson_and_the_class() -> None:
    entries = catalogue_entries(REFERENTIAL)
    fractions = [notion("k1", "Fraction", "Une fraction a un numérateur et un dénominateur.")]
    chosen = choose_mathalea(entries, "math", "CM2", "Les fractions", fractions)
    assert [r.title for r in chosen] == ["Opérations simples avec des fractions"]  # pas celui à colorier
    [resource] = chosen
    assert resource.provider is Provider.MATHALEA and resource.kind is ResourceKind.EXERCISE
    assert resource.url.startswith("https://coopmaths.fr/alea/?uuid=f0f0f&id=c3C20&n=5&i=1&v=eleve")
    assert host_allowed(resource.url, Provider.MATHALEA)
    # Le périmètre de 6e n'est pas proposé en CM2 ; une leçon de français, jamais ; avant le CM1, rien.
    perimeter = [notion("k1", "Périmètre", "Le périmètre est la longueur du contour.")]
    assert choose_mathalea(entries, "math", "CM2", "Le périmètre", perimeter) == []
    assert [r.title for r in choose_mathalea(entries, "math", "6e", "Le périmètre", perimeter)] == [
        "Calculer le périmètre d’une figure"
    ]
    assert choose_mathalea(entries, "french", "CM2", "Les fractions", fractions) == []
    assert choose_mathalea(entries, "math", "CE1", "Les fractions", fractions) == []


def test_a_generic_word_is_not_enough() -> None:
    """« Calculer » ou « nombre » ne disent pas le sujet : « le double » n'est pas une leçon
    sur le calcul de durées."""
    entries = catalogue_entries(REFERENTIAL)
    durations = [notion("k1", "Calculer une durée", "On calcule une durée avec les heures.")]
    assert choose_mathalea(entries, "math", "CM1", "Les durées", durations) == []


def test_mathalea_url_is_the_pupil_view() -> None:
    entry = CatalogueEntry("6C10-1", "665a0", "Tables", "6e", True)
    assert mathalea_url(entry, 3) == (
        "https://coopmaths.fr/alea/?uuid=665a0&id=6C10-1&n=3&i=1&v=eleve&es=0111&title=Ludifun"
    )


QUIZ_PAGE = """Un petit quiz sur les '''volcans'''.
<quiz display=simple>
{Comment s'appelle la roche fondue qui sort d'un [[volcan]] ?
|type="()"}
+ La [[lave|lave]]
- Le sable
- La neige
- Le charbon

{Un volcan peut-il être endormi ?
|type="()"}
+ Vrai
- Faux

{Cite deux volcans.
|type="{}"}
{ Etna }

{Quels pays ont des volcans ?
|type="[]"}
+ Italie
+ Islande
- Belgique

{Combien de pattes a une araignée ?
|type="()"}
+ Huit
- Six
- Quatre
- Dix
</quiz>
"""


def test_vikidia_quizzes_are_read() -> None:
    questions = parse_quiz(QUIZ_PAGE)
    # Seules les questions à une bonne réponse sont reprises.
    assert [q.text for q in questions] == [
        "Comment s'appelle la roche fondue qui sort d'un volcan ?",
        "Un volcan peut-il être endormi ?",
        "Combien de pattes a une araignée ?",
    ]
    assert questions[0].right == ["La lave"] and questions[0].wrong == ["Le sable", "La neige", "Le charbon"]
    assert (
        clean_wiki("'''Le''' [[volcan|volcan]] {{réf}}<ref>x</ref> [https://a.fr site]") == "Le volcan site"
    )


def test_quiz_questions_go_to_the_matching_notion() -> None:
    volcano = notion("k1", "Le volcan", "Un volcan crache de la lave ; il peut être endormi.")
    material = quiz_material(parse_quiz(QUIZ_PAGE), [volcano])
    # « Vrai ou faux » : pas une question à choix ; l'araignée : aucune notion de la leçon.
    assert [m.knowledge_id for m in material] == ["k1"]
    assert material[0].question["answer"] == "La lave"
    assert material[0].question["distractors"] == ["Le sable", "La neige", "Le charbon"]


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("https://www.lumni.fr/video/les-volcans", ResourceKind.VIDEO),
        ("https://www.lumni.fr/quiz/les-volcans", ResourceKind.QUIZ),
        ("https://www.lumni.fr/article/pourquoi-les-volcans", ResourceKind.ARTICLE),
        ("https://www.lumni.fr/recherche?q=volcan", None),
        ("https://www.youtube.com/watch?v=lumni", None),
        ("http://www.lumni.fr/video/les-volcans", None),
    ],
)
def test_lumni_pages_are_recognized(url: str, kind: ResourceKind | None) -> None:
    resource = lumni_resource(url, "Les volcans - Lumni | Primaire")
    assert (resource.kind if resource else None) == kind
    if resource:
        assert resource.title == "Les volcans"


def test_the_viewer_stays_on_the_site() -> None:
    assert host_allowed("https://coopmaths.fr/alea/?uuid=1", Provider.MATHALEA)
    assert host_allowed("https://fr.vikidia.org/wiki/Volcan", Provider.VIKIDIA)
    assert not host_allowed("https://coopmaths.fr.evil.com/", Provider.MATHALEA)
    assert not host_allowed("https://www.lumni.fr/", Provider.VIKIDIA)
    assert vikidia_page_url("Quiz sur les volcans") == "https://fr.vikidia.org/wiki/Quiz_sur_les_volcans"


def test_linked_sites_keep_only_lesson_pages_about_the_topic() -> None:
    """Les Fondamentaux, Maître Lucas : une page sur la leçon, jamais l'accueil, une recherche, une
    autre leçon ni un autre site ; Maître Lucas pour l'école seulement."""
    from app.domain.resources import LINKED_SITES, Provider, ResourceKind, linked_resource
    from app.domain.sources import keywords

    fondamentaux, lucas = LINKED_SITES
    topic = keywords("Les fractions numérateur dénominateur")
    film = linked_resource(
        fondamentaux,
        "https://www.reseau-canope.fr/lesfondamentaux/discipline/mathematiques/fractions/le-numerateur.html",
        "Le numérateur - Les fondamentaux",
        topic,
    )
    assert film is not None and film.kind is ResourceKind.VIDEO and film.title == "Le numérateur"
    page = linked_resource(lucas, "https://www.maitrelucas.fr/fractions/", "Fractions | Maître Lucas", topic)
    assert page is not None and page.provider is Provider.MAITRE_LUCAS and page.kind is ResourceKind.LESSON
    video = linked_resource(lucas, "https://www.maitrelucas.fr/video-fractions/", "Fractions en vidéo", topic)
    assert video is not None and video.kind is ResourceKind.VIDEO
    for url, title in [
        ("https://www.maitrelucas.fr/", "Fractions - Maître Lucas"),
        ("https://www.maitrelucas.fr/?s=fractions", "Fractions"),
        ("https://www.maitrelucas.fr/category/maths/", "Fractions"),
        ("https://www.maitrelucas.fr/le-passe-compose/", "Le passé composé"),
        ("http://www.maitrelucas.fr/fractions/", "Fractions"),
        ("https://maitrelucas.fr.example.com/fractions/", "Fractions"),
    ]:
        assert linked_resource(lucas, url, title, topic) is None, url
    assert (
        linked_resource(
            fondamentaux, "https://www.reseau-canope.fr/boutique/fractions.html", "Fractions", topic
        )
        is None
    )
    assert Grade.CE1 in lucas.grades and Grade.CINQUIEME not in lucas.grades
    assert Grade.SIXIEME in fondamentaux.grades
