"""Illustration d'une leçon (étape 27) : l'IA propose une scène, le code décide de l'image.

L'IA de texte ne propose que la scène à dessiner (en anglais, la langue des modèles d'image) et
une phrase qui la décrit au parent. Le code contrôle cette proposition (longueur, mots interdits
pour des enfants, aucune demande de texte dans l'image), puis construit seul le prompt : style
Ludifun, âge de l'enfant, format carré, texte interdit. Une proposition refusée ne produit pas
d'image : la leçon, elle, reste entière.

L'image est facultative et décorative : aucune question n'en dépend. Elle n'est montrée à
l'enfant qu'une fois validée par le parent (statuts ci-dessous).
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from app.domain.knowledge import Grade

SCENE_MAX = 300  # caractères : une scène simple, que le modèle d'image peut suivre
ALT_MAX = 200
SIZE = 1024  # carré ; SDXL est entraîné à cette taille
REMARK_MAX = 300


class ImageStatus(StrEnum):
    GENERATING = "generating"  # en préparation
    TO_REVIEW = "to_review"  # prête, en attente du parent
    APPROVED = "approved"  # validée : l'enfant la voit
    REJECTED = "rejected"  # refusée par le parent (il peut demander de la refaire)
    FAILED = "failed"  # moteur absent, scène refusée par les contrôles…


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

STYLE = (
    "children's educational book illustration, soft flat colors, clean simple shapes, "
    "friendly and calm, plain light background, high quality"
)
# Ce que l'image ne doit jamais contenir. Le texte surtout : les modèles d'image l'écrivent faux.
NEGATIVE = (
    "text, letters, words, numbers, writing, caption, label, watermark, signature, logo, "
    "speech bubble, scary, horror, violent, blood, gore, weapon, nudity, photo, photorealistic, "
    "deformed, extra limbs, blurry"
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
    if not caption or len(caption) > ALT_MAX:
        return None, "description pour le parent absente ou trop longue"
    return Scene(text.rstrip("."), caption), ""


def age_of(grade: str | None) -> int:
    try:
        return AGES[Grade(grade)] if grade else 9
    except ValueError:
        return 9


def build_prompt(scene: Scene, grade: str | None) -> ImagePrompt:
    """Le prompt d'image : la scène, puis le style et les règles de Ludifun, toujours les mêmes."""
    return ImagePrompt(
        prompt=f"{scene.description}. {STYLE}, made for a {age_of(grade)}-year-old child, no text",
        negative=NEGATIVE,
    )


def clean_remark(remark: str | None) -> str | None:
    """Remarque du parent pour refaire l'image : une donnée, jamais une consigne (§142-143)."""
    text = " ".join((remark or "").split())[:REMARK_MAX]
    return text.replace("<", "‹").replace(">", "›") or None
