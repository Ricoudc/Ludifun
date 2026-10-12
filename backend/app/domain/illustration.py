"""Illustration d'une leçon (étape 27) : l'IA propose une scène, le code décide de l'image.

L'IA de texte ne propose que la scène à dessiner (en anglais, la langue des modèles d'image) et
une phrase qui la décrit au parent. Le code contrôle cette proposition (longueur, mots interdits
pour des enfants, aucune demande de texte dans l'image), puis construit seul le prompt : style
Ludifun, âge de l'enfant, format carré, texte interdit. Une proposition refusée ne produit pas
d'image : la leçon, elle, reste entière.

Ce qui doit être exact (une figure de géométrie, un schéma légendé, une carte) n'est jamais
demandé au moteur d'images : le code le dessine (`app.domain.diagrams`, §5.61). Le moteur fait
le reste, dans le style d'un manuel scolaire : la chose à retenir, juste et bien visible, plutôt
qu'une scène de livre d'histoires.

L'image est facultative : l'IA dit d'abord si une image aide vraiment à retenir la leçon
(une leçon de conjugaison ou de calcul mental s'en passe très bien) ; sinon, rien n'est dessiné
et le parent le voit (« pas utile »), libre d'en demander une quand même. Les notions concrètes
(un volcan, une chenille, un château fort) peuvent avoir chacune leur image : elles servent aux
jeux « apprendre par l'image » (étape 28). Toute image n'est montrée à l'enfant qu'une fois
validée par le parent (statuts ci-dessous).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.knowledge import Grade
from app.domain.rules import RULES

SCENE_MAX = 300  # caractères : une scène simple, que le modèle d'image peut suivre
ALT_MAX = 200
SIZE = 1024  # carré ; SDXL est entraîné à cette taille
REMARK_MAX = 300
# Images des notions dessinées par leçon (le temps de la carte graphique) : engine_rules.toml.
PICTURES_PER_LESSON = RULES.pictures.per_lesson
NOT_NEEDED_DEFAULT = "une image n'aiderait pas à retenir cette leçon"


class ImageStatus(StrEnum):
    GENERATING = "generating"  # en préparation
    TO_REVIEW = "to_review"  # prête, en attente du parent
    APPROVED = "approved"  # validée : l'enfant la voit
    REJECTED = "rejected"  # refusée par le parent (il peut demander de la refaire)
    FAILED = "failed"  # moteur absent, scène refusée par les contrôles…
    NOT_NEEDED = "not_needed"  # l'IA juge qu'une image n'aiderait pas (le parent peut insister)


AGES: dict[Grade, int] = {
    Grade.CP: 6,
    Grade.CE1: 7,
    Grade.CE2: 8,
    Grade.CM1: 9,
    Grade.CM2: 10,
    Grade.SIXIEME: 11,
    Grade.CINQUIEME: 12,
    Grade.QUATRIEME: 13,
    Grade.TROISIEME: 14,
}

# Image d'une notion, pour les jeux : un seul sujet, bien reconnaissable.
SINGLE_SUBJECT = "one single clear main subject in the center, easy to recognize"
# Style d'un manuel scolaire (§5.61) : la chose à apprendre, juste et lisible, pas un décor.
STYLE = (
    "clear educational textbook illustration, accurate shapes and true proportions, realistic "
    "natural colors, clean outlines, the key feature clearly visible, plain white background, "
    "high quality"
)
# Ce que l'image ne doit jamais contenir. Le texte surtout : les modèles d'image l'écrivent faux.
NEGATIVE = (
    "text, letters, words, numbers, writing, caption, label, watermark, signature, logo, "
    "speech bubble, scary, horror, violent, blood, gore, weapon, nudity, photo, photorealistic, "
    "deformed, extra limbs, blurry, fantasy, cute mascot, smiling objects, decorative border, "
    "cluttered background"
)
# Une scène qui en parle est refusée (images pour des enfants de 6 à 14 ans).
_FORBIDDEN = re.compile(
    r"\b(blood|bloody|gore|gory|corpse|dead body|kill|killing|murder|torture|naked|nude|nudity|"
    r"sexy|sexual|horror|scary|terrifying|gun|guns|rifle|pistol|knife|knives|bomb|drug|drugs|"
    r"alcohol|beer|wine|cigarette|smoking)\b",
    re.IGNORECASE,
)
# Demander du texte dans l'image : les modèles l'écrivent mal, et l'enfant le lirait faux.
_TEXT_REQUEST = re.compile(
    r"\b(text|word|words|letter|letters|written|writing|caption|label|labels|title|sign that says|"
    r"says|spelled|number|numbers|digit|digits)\b|[\"«»“”]",
    re.IGNORECASE,
)


# Un schéma, une carte, une figure exacte : le moteur d'images les dessine faux ; le code les
# dessine (`app.domain.diagrams`).
_DIAGRAM_REQUEST = re.compile(
    r"\b(diagrams?|charts?|graphs?|infographics?|maps?|blueprints?|worksheets?|geometric|geometry|"
    r"cross[- ]sections?|cutaway|labell?ed|rhombus|parallelograms?|trapezoids?|polygons?|cuboids?|"
    r"right angles?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Scene:
    description: str  # en anglais, pour le modèle d'image
    alt: str  # en français, pour le parent (et la lecture d'écran)


@dataclass(frozen=True)
class ImagePrompt:
    prompt: str
    negative: str
    width: int = SIZE
    height: int = SIZE


def validate_scene(description: str | None, alt: str | None) -> tuple[Scene | None, str]:
    """La scène proposée par l'IA, ou la raison de son refus."""
    text = " ".join((description or "").split())
    caption = " ".join((alt or "").split())
    if not text:
        return None, "aucune scène proposée"
    if len(text) > SCENE_MAX:
        return None, f"scène trop longue (> {SCENE_MAX} caractères)"
    if _FORBIDDEN.search(text):
        return None, "la scène contient un mot interdit pour des enfants"
    if _TEXT_REQUEST.search(text):
        return None, "la scène demande du texte ou des chiffres dans l'image"
    if _DIAGRAM_REQUEST.search(text):
        return None, "un schéma ou une figure exacte ne se dessine pas avec le moteur d'images"
    if not caption or len(caption) > ALT_MAX:
        return None, "description pour le parent absente ou trop longue"
    return Scene(text.rstrip("."), caption), ""


def age_of(grade: str | None) -> int:
    try:
        return AGES[Grade(grade)] if grade else 9
    except ValueError:
        return 9


def build_prompt(scene: Scene, grade: str | None, single_subject: bool = False) -> ImagePrompt:
    """Le prompt d'image : la scène, puis le style et les règles de Ludifun, toujours les mêmes.
    Image d'une notion (`single_subject`) : un seul sujet, au centre, pour qu'on le reconnaisse."""
    style = f"{SINGLE_SUBJECT}, {STYLE}" if single_subject else STYLE
    return ImagePrompt(
        prompt=f"{scene.description}. {style}, made for a {age_of(grade)}-year-old child, no text",
        negative=NEGATIVE,
    )


@dataclass(frozen=True)
class ProposedPicture:
    notion: str | None  # référence de la notion donnée à l'IA (N1, N2…)
    scene: str | None
    alt: str | None


@dataclass(frozen=True)
class IllustrationPlan:
    """Ce que le code retient de la proposition de l'IA."""

    cover: Scene | None  # image de la leçon
    cover_issue: str  # pourquoi pas d'image de la leçon ("" s'il y en a une)
    cover_needed: bool  # False : une image n'aiderait pas (statut « pas utile »)
    pictures: dict[str, Scene] = field(default_factory=dict)  # notion → scène
    refused: dict[str, str] = field(default_factory=dict)  # notion → raison du refus


def plan_illustrations(
    useful: bool | None,
    why: str | None,
    scene: str | None,
    alt: str | None,
    proposed: Sequence[ProposedPicture],
    notions: Sequence[str],
    limit: int = PICTURES_PER_LESSON,
) -> IllustrationPlan:
    """Contrôle la proposition : image de la leçon seulement si elle aide (`useful`), au plus
    `limit` images de notions, chacune pour une notion de la leçon, une seule fois."""
    cover: Scene | None = None
    if useful is False:
        cover_issue = " ".join((why or "").split())[:ALT_MAX] or NOT_NEEDED_DEFAULT
    else:
        cover, cover_issue = validate_scene(scene, alt)
    pictures: dict[str, Scene] = {}
    refused: dict[str, str] = {}
    for picture in proposed:
        notion = picture.notion or ""
        if notion not in notions or notion in pictures or len(pictures) >= limit:
            continue
        checked, reason = validate_scene(picture.scene, picture.alt)
        if checked is None:
            refused[notion] = reason
        else:
            pictures[notion] = checked
    return IllustrationPlan(cover, cover_issue, useful is not False, pictures, refused)


def clean_remark(remark: str | None) -> str | None:
    """Remarque du parent pour refaire l'image : une donnée, jamais une consigne (§142-143)."""
    text = " ".join((remark or "").split())[:REMARK_MAX]
    return text.replace("<", "‹").replace(">", "›") or None
