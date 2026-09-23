"""Formats structurés échangés avec l'IA (sorties JSON validées)."""

from typing import Literal

from pydantic import BaseModel, Field

NotionKind = Literal[
    "date",
    "vocabulaire",
    "definition",
    "personnage",
    "evenement",
    "lieu",
    "regle",
    "formule",
    "calcul",
    "concept",
]
Importance = Literal["essentielle", "importante", "complementaire"]
QuestionKind = Literal[
    "qcm", "vrai_faux", "texte_a_trous", "flashcard", "association", "question_ouverte"
]


class AnalyzedNotion(BaseModel):
    label: str = Field(description="Nom court de la notion, ex. « 1789 » ou « Louis XVI ».")
    kind: NotionKind
    content: str = Field(description="Ce que l'enfant doit retenir, en une ou deux phrases.")
    importance: Importance


class LessonAnalysis(BaseModel):
    """IA 1 + IA 2 : lecture de la photo et structuration pédagogique."""

    readable: bool = Field(description="False si la photo est illisible ou n'est pas une leçon.")
    subject: str = Field(description="Matière : Français, Mathématiques, Histoire, ...")
    grade: str = Field(description="Niveau estimé : CP, CE1, CE2, CM1, CM2, 6e, 5e, 4e, 3e.")
    title: str
    summary: str = Field(description="Résumé de la leçon en 2-3 phrases adaptées à l'enfant.")
    source_text: str = Field(description="Texte de la leçon retranscrit fidèlement.")
    notions: list[AnalyzedNotion]


class Pair(BaseModel):
    left: str
    right: str


class GeneratedQuestion(BaseModel):
    notion_index: int = Field(description="Index (0-based) de la notion ciblée.")
    kind: QuestionKind
    difficulty: int = Field(description="1 reconnaître, 2 se rappeler, 3 appliquer, 4 expliquer.")
    prompt: str
    choices: list[str] = Field(description="4 choix pour qcm, [\"Vrai\",\"Faux\"] pour vrai_faux, sinon vide.")
    answer: str = Field(description="Bonne réponse exacte (texte d'un des choix pour qcm/vrai_faux).")
    explanation: str = Field(description="Explication courte et bienveillante affichée après la réponse.")
    pairs: list[Pair] = Field(description="Paires à associer (association uniquement), sinon vide.")


class QuestionBank(BaseModel):
    questions: list[GeneratedQuestion]


class OpenAnswerEvaluation(BaseModel):
    """IA 4 : évaluation d'une réponse libre."""

    score: float = Field(description="Entre 0 et 1.")
    feedback: str = Field(description="Retour bienveillant, 1-2 phrases, tutoiement.")
    missing_points: list[str] = Field(description="Éléments importants oubliés.")
