"""Formats de sortie demandés à l'IA (sorties structurées, cahier des charges §6).

Ces modèles décrivent la *forme* attendue ; ils restent volontairement souples (pas
de bornes, champs facultatifs) pour que le modèle puisse toujours répondre. La
validation métier est faite ensuite par `app.domain.validation`, élément par élément.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.errors import ErrorType
from app.domain.knowledge import (
    ANALYSIS_SCHEMA_VERSION,
    Grade,
    KnowledgeType,
    RelationType,
    SkillVerb,
    Subject,
)

# --------------------------------------------------------------------------- #
# ① OCR
# --------------------------------------------------------------------------- #


class UncertainOut(BaseModel):
    text: str = Field(description="Le passage douteux tel que tu l'as transcrit (ou « [illisible] »).")
    context: str = Field(
        description="6 à 12 mots de ta transcription qui contiennent ce passage, recopiés exactement."
    )


class OcrPage(BaseModel):
    index: int = Field(description="Numéro de la page, à partir de 0, dans l'ordre des images.")
    quality: Literal["good", "partial", "unreadable"]
    text: str = Field(description="Transcription fidèle ; « [illisible] » pour un passage illisible.")
    uncertain: list[UncertainOut] = Field(
        default_factory=list,
        description="Passages importants dont la lecture est douteuse (0 à 5) ; vide si tout est sûr.",
    )


class OcrResult(BaseModel):
    pages: list[OcrPage]
    language: str = Field(description="Code de langue principal de la leçon, par exemple « fr ».")
    warnings: list[str] = Field(description="Remarques sur la lecture (photo floue, page coupée…).")

    @property
    def text(self) -> str:
        return "\n\n".join(
            p.text.strip() for p in sorted(self.pages, key=lambda p: p.index) if p.text.strip()
        )

    @property
    def unreadable(self) -> bool:
        return not self.text or all(p.quality == "unreadable" for p in self.pages)


# --------------------------------------------------------------------------- #
# ② Analyse pédagogique
# --------------------------------------------------------------------------- #


class Variable(BaseModel):
    symbol: str
    meaning: str


class CategoryOut(BaseModel):
    name: str
    members: list[str]


class AttributesOut(BaseModel):
    """Attributs selon le type de notion ; les champs qui ne s'appliquent pas valent null."""

    value: str | None = Field(None, description="date : la date, par exemple « 1789 ».")
    precision: Literal["year", "day"] | None = Field(None, description="date : année seule ou jour précis.")
    event: str | None = Field(None, description="date : ce qui se passe à cette date.")
    role: str | None = Field(None, description="person : son rôle.")
    description: str | None = Field(None, description="place : ce qu'est ce lieu.")
    date: str | None = Field(None, description="event : quand il a lieu.")
    place: str | None = Field(None, description="event : où il a lieu.")
    definition: str | None = Field(None, description="term : la définition.")
    statement: str | None = Field(None, description="rule : l'énoncé de la règle.")
    example: str | None = Field(None, description="rule : un exemple tiré de la leçon.")
    expression: str | None = Field(None, description="formula : la formule.")
    variables: list[Variable] | None = Field(None, description="formula : signification des lettres.")
    steps: list[str] | None = Field(None, description="process : les étapes dans l'ordre.")
    categories: list[CategoryOut] | None = Field(None, description="classification : catégories.")

    def to_dict(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        if "variables" in data:
            data["variables"] = {v["symbol"]: v["meaning"] for v in data["variables"]}
        return data


class RelationOut(BaseModel):
    type: RelationType
    target: str = Field(description="Identifiant de l'autre notion, par exemple « k1 ».")


class KnowledgeOut(BaseModel):
    id: str = Field(description="k1, k2, k3… dans l'ordre de la leçon.")
    type: KnowledgeType
    label: str = Field(description="Nom court de la notion.")
    statement: str = Field(description="La phrase à retenir, simple, au niveau de l'enfant.")
    importance: int = Field(description="5 = sera forcément demandée … 1 = détail.")
    attributes: AttributesOut
    source_excerpt: str = Field(description="Citation EXACTE du texte de la leçon qui justifie la notion.")
    relations: list[RelationOut]


class SkillOut(BaseModel):
    id: str = Field(description="s1, s2, s3…")
    label: str = Field(description="Ce que l'élève doit savoir faire, commençant par un verbe.")
    verb: SkillVerb = Field(
        description="recognize reconnaître, recall se rappeler, apply appliquer, "
        "explain expliquer, transfer réutiliser dans une situation nouvelle."
    )
    importance: int = Field(description="5 = sera forcément évaluée … 1 = secondaire.")
    knowledge_ids: list[str] = Field(description='Notions nécessaires, par exemple ["k2", "k3"].')
    source_excerpt: str = Field(
        description="Citation EXACTE du texte de la leçon qui justifie la compétence."
    )


class LessonInfoOut(BaseModel):
    subject: Subject
    grade: Grade
    grade_confidence: float = Field(description="Confiance dans le niveau, entre 0 et 1.")
    title: str
    objective: str = Field(description="Objectif de révision formulé pour l'enfant.")
    summary: str = Field(description="Résumé en 2-3 phrases adaptées à l'enfant.")


class AnalysisOutput(BaseModel):
    is_lesson: bool = Field(description="false si le texte n'est pas une leçon à réviser.")
    lesson: LessonInfoOut | None
    knowledge: list[KnowledgeOut]
    skills: list[SkillOut]
    warnings: list[str]

    def to_raw(self) -> dict[str, Any]:
        """Format attendu par `validate_analysis` (§6.2)."""
        data = self.model_dump(mode="json")
        data["schema_version"] = ANALYSIS_SCHEMA_VERSION
        for item, knowledge in zip(data["knowledge"], self.knowledge, strict=True):
            item["attributes"] = knowledge.attributes.to_dict()
        return data


# --------------------------------------------------------------------------- #
# ③ Matériel pédagogique par notion
# --------------------------------------------------------------------------- #


class DistractorOut(BaseModel):
    text: str
    misconception: ErrorType | None = Field(
        description="L'erreur que révèle ce choix : confusion (avec une autre notion), calculation, "
        "method, reading, imprecision (presque juste), knowledge (ne sait pas) ; null si aucune."
    )


class QuestionOut(BaseModel):
    difficulty: int = Field(description="1 reconnaître, 2 se rappeler, 3 relier / appliquer.")
    stem: str = Field(description="L'énoncé, qui ne doit pas contenir la réponse.")
    answer: str
    distractors: list[DistractorOut] = Field(
        description="Exactement 3 mauvaises réponses plausibles, de même nature."
    )
    passage: str | None = Field(
        None, description="Passage de la leçon recopié mot pour mot, si la question porte sur un texte lu."
    )


class ClozeOut(BaseModel):
    text: str = Field(description="Phrase avec exactement un « ___ » à la place du mot à trouver.")
    answers: list[str] = Field(description="Réponses acceptées (variantes d'écriture).")


class PairOut(BaseModel):
    left: str = Field(description="40 caractères au plus.")
    right: str = Field(description="60 caractères au plus.")


class FlashcardOut(BaseModel):
    front: str
    back: str


class WorkedExampleOut(BaseModel):
    question: str = Field(description="Un exercice semblable, avec d'autres valeurs que celles de la leçon.")
    answer: str
    why: str | None


class HelpOut(BaseModel):
    """Aides graduées « Je n'ai pas compris » ; aucune ne doit donner la réponse d'un exercice."""

    hint: str | None = Field(description="Niveau 1 : un indice qui met sur la piste, 120 caractères au plus.")
    reminder: str | None = Field(description="Niveau 2 : le rappel de la leçon utile, sans la réponse.")
    example: WorkedExampleOut | None = Field(description="Niveau 3 : un exemple semblable résolu.")
    steps: list[str] = Field(description="Niveau 4 : la démarche en 2 à 4 étapes courtes.")


class OpenQuestionOut(BaseModel):
    level: int = Field(
        description="3 appliquer, 4 expliquer pourquoi, 5 réutiliser dans une situation nouvelle."
    )
    prompt: str = Field(description="La question, à laquelle l'enfant répond en une ou deux phrases.")
    key_points: list[str] = Field(description="1 à 4 points clés attendus, courts, tirés de la leçon.")
    model_answer: str = Field(description="Une réponse modèle, au niveau de l'enfant.")
    passage: str | None = Field(
        None, description="Passage de la leçon recopié mot pour mot, si la question porte sur un texte lu."
    )


class SortingBoxOut(BaseModel):
    name: str
    members: list[str] = Field(description="2 à 4 éléments, chacun dans une seule case.")


class SortingOut(BaseModel):
    prompt: str = Field(description="La consigne du jeu de tri.")
    categories: list[SortingBoxOut] = Field(description="2 ou 3 cases.")


class SequenceOut(BaseModel):
    prompt: str = Field(description="La consigne (« Range du plus petit au plus grand »).")
    items: list[str] = Field(description="3 à 6 éléments, dans le bon ordre.")


class SpellingOut(BaseModel):
    word: str = Field(description="Le mot à savoir écrire, exactement comme dans la leçon.")
    sentence: str | None = Field(
        None, description="Une phrase courte qui utilise le mot, remplacé par « ___ » ; sinon null."
    )


class MaterialOut(BaseModel):
    knowledge_id: str
    questions: list[QuestionOut]
    true_statements: list[str]
    false_statements: list[str] = Field(description="Clairement fausses, jamais une simple négation.")
    cloze: ClozeOut | None
    pair: PairOut | None
    flashcard: FlashcardOut | None
    tip: str | None = Field(description="Astuce pour retenir, 120 caractères au plus, sans rien inventer.")
    explanation: str = Field(description="Explication courte et bienveillante.")
    help: HelpOut | None
    open_questions: list[OpenQuestionOut] = Field(description="0 à 2 questions ouvertes.")
    sorting: SortingOut | None = Field(None, description="Jeu de tri (étape 25), sinon null.")
    sequence: SequenceOut | None = Field(None, description="Éléments à remettre dans l'ordre, sinon null.")
    spelling: SpellingOut | None = Field(None, description="Mot à savoir écrire, sinon null.")


class MaterialBatchOutput(BaseModel):
    materials: list[MaterialOut]


# --------------------------------------------------------------------------- #
# ④ Correction d'une réponse rédigée
# --------------------------------------------------------------------------- #


class EvaluationOutput(BaseModel):
    score: float = Field(description="Entre 0 et 1 : part des points clés présents dans la réponse.")
    key_points_found: list[str] = Field(description="Points clés présents, recopiés tels quels.")
    missing: list[str] = Field(description="Points clés absents, recopiés tels quels.")
    error_type: ErrorType | None = Field(description="Principale erreur si la réponse n'est pas complète.")
    confidence: float = Field(description="Confiance dans la correction, entre 0 et 1.")
    feedback: str = Field(description="Un retour bienveillant de 1 à 2 phrases, en tutoyant l'enfant.")


class SourceQuote(BaseModel):
    source: int = Field(description="Numéro de l'extrait cité (attribut numero de la balise <source>).")
    text: str = Field(description="Phrase recopiée mot pour mot depuis cet extrait.")


class PictureProposal(BaseModel):
    """Étape 28 : l'image d'une notion concrète, pour les jeux « apprendre par l'image »."""

    notion: str | None = Field(None, description="La notion montrée : N1, N2…")
    scene: str | None = Field(None, description="En anglais, UNE chose concrète, bien reconnaissable.")
    alt: str | None = Field(None, description="En français, ce que montre l'image, pour le parent.")


class IllustrationOutput(BaseModel):
    """Étapes 27 et 28 : une image aide-t-elle, et lesquelles ; le code construit seul les prompts
    d'image. `useful` et `pictures` (prompt v2) sont facultatifs : une réponse v1 reste lisible."""

    useful: bool | None = Field(
        None, description="Une image aide-t-elle vraiment à retenir la leçon ? Dans le doute, non."
    )
    why: str | None = Field(None, description="En français, pourquoi, en une phrase pour le parent.")
    scene: str | None = Field(
        None,
        description="En anglais, une scène simple et concrète à dessiner (sans texte ni chiffres), "
        "ou null si rien ne s'illustre bien.",
    )
    alt: str | None = Field(None, description="En français, une phrase qui décrit l'image pour le parent.")
    pictures: list[PictureProposal] = Field(
        default_factory=list, description="Images des notions concrètes, 4 au plus."
    )


class SourcedAnswerOutput(BaseModel):
    """Étape 24 : réponse expliquée à partir des extraits fournis, avec ses citations."""

    found: bool = Field(description="true si les extraits contiennent la réponse, sinon false.")
    answer: str = Field(description="Réponse de 1 à 4 phrases, adaptée à la classe, en tutoyant l'enfant.")
    quotes: list[SourceQuote] = Field(description="1 à 3 citations exactes qui justifient la réponse.")
