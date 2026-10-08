"""Structure normalisée d'une leçon (cahier des charges §6.2 et §6.3).

C'est le contrat entre l'IA et le reste de l'application : l'analyse produit une
`LessonAnalysis` (notions et compétences), l'enrichissement un `KnowledgeMaterial` par
notion, et le moteur d'activités ne connaît que ces objets.
"""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
KnowledgeId = Annotated[str, StringConstraints(pattern=r"^k\d+$")]
SkillId = Annotated[str, StringConstraints(pattern=r"^s\d+$")]
PASSAGE_MAX_LENGTH = 400  # passage de la leçon montré avec une question
ANALYSIS_SCHEMA_VERSION = "2.0"  # 2.0 : compétences


class Subject(StrEnum):
    FRENCH = "french"
    MATH = "math"
    HISTORY = "history"
    GEOGRAPHY = "geography"
    SCIENCE = "science"
    ENGLISH = "english"
    CIVICS = "civics"
    OTHER = "other"


class Grade(StrEnum):
    CP = "CP"
    CE1 = "CE1"
    CE2 = "CE2"
    CM1 = "CM1"
    CM2 = "CM2"
    SIXIEME = "6e"
    CINQUIEME = "5e"
    QUATRIEME = "4e"
    TROISIEME = "3e"


class KnowledgeType(StrEnum):
    DATE = "date"
    PERSON = "person"
    PLACE = "place"
    EVENT = "event"
    TERM = "term"
    RULE = "rule"
    FORMULA = "formula"
    FACT = "fact"
    PROCESS = "process"
    CLASSIFICATION = "classification"


class SkillVerb(StrEnum):
    """Ce que l'élève doit savoir faire (niveaux de compréhension, spécification technique §5.1)."""

    RECOGNIZE = "recognize"
    RECALL = "recall"
    APPLY = "apply"
    EXPLAIN = "explain"
    TRANSFER = "transfer"


class RelationType(StrEnum):
    HAPPENED_IN = "happened_in"
    PART_OF = "part_of"
    OPPOSITE_OF = "opposite_of"
    EXAMPLE_OF = "example_of"
    CAUSES = "causes"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


# --------------------------------------------------------------------------- #
# Attributs propres à chaque type de notion
# --------------------------------------------------------------------------- #


class DateAttributes(_Model):
    value: NonEmpty
    precision: Annotated[str, StringConstraints(pattern="^(year|day)$")]
    event: NonEmpty


class PersonAttributes(_Model):
    role: NonEmpty


class PlaceAttributes(_Model):
    description: NonEmpty


class EventAttributes(_Model):
    date: NonEmpty | None = None
    place: NonEmpty | None = None


class TermAttributes(_Model):
    definition: NonEmpty


class RuleAttributes(_Model):
    statement: NonEmpty
    example: NonEmpty


class FormulaAttributes(_Model):
    expression: NonEmpty
    variables: dict[str, str] = Field(default_factory=dict)  # symbole → signification


class FactAttributes(_Model):
    pass


class ProcessAttributes(_Model):
    steps: list[NonEmpty] = Field(min_length=2)


class Category(_Model):
    name: NonEmpty
    members: list[NonEmpty] = Field(min_length=1)


class ClassificationAttributes(_Model):
    categories: list[Category] = Field(min_length=2)


ATTRIBUTE_MODELS: dict[KnowledgeType, type[_Model]] = {
    KnowledgeType.DATE: DateAttributes,
    KnowledgeType.PERSON: PersonAttributes,
    KnowledgeType.PLACE: PlaceAttributes,
    KnowledgeType.EVENT: EventAttributes,
    KnowledgeType.TERM: TermAttributes,
    KnowledgeType.RULE: RuleAttributes,
    KnowledgeType.FORMULA: FormulaAttributes,
    KnowledgeType.FACT: FactAttributes,
    KnowledgeType.PROCESS: ProcessAttributes,
    KnowledgeType.CLASSIFICATION: ClassificationAttributes,
}


# --------------------------------------------------------------------------- #
# Leçon et notions (sortie de l'analyse, §6.2)
# --------------------------------------------------------------------------- #


class Relation(_Model):
    type: RelationType
    target: KnowledgeId


class KnowledgeItem(_Model):
    id: KnowledgeId
    type: KnowledgeType
    label: NonEmpty
    statement: NonEmpty  # la phrase « à retenir »
    importance: int = Field(ge=1, le=5)
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_excerpt: NonEmpty  # citation exacte du texte OCR (garde-fou contre les inventions)
    relations: list[Relation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _attributes_match_type(self) -> "KnowledgeItem":
        ATTRIBUTE_MODELS[self.type].model_validate(self.attributes)
        return self

    def typed_attributes(self) -> _Model:
        return ATTRIBUTE_MODELS[self.type].model_validate(self.attributes)

    def corpus(self) -> str:
        """Tout le texte connu de la notion (pour vérifier qu'une astuce n'invente rien)."""
        parts = [self.label, self.statement, self.source_excerpt]
        parts.extend(_flatten(self.attributes))
        return " ".join(parts)


def _flatten(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in (str(k), *_flatten(v))]
    if isinstance(value, list):
        return [s for v in value for s in _flatten(v)]
    return [str(value)]


class LessonInfo(_Model):
    subject: Subject
    grade: Grade
    grade_confidence: float = Field(ge=0, le=1)
    title: NonEmpty
    objective: NonEmpty
    summary: NonEmpty


class Skill(_Model):
    """Une compétence visée par la leçon (« Comparer deux fractions »), reliée à ses notions."""

    id: SkillId
    label: NonEmpty
    verb: SkillVerb
    importance: int = Field(ge=1, le=5)
    knowledge_ids: list[KnowledgeId] = Field(min_length=1)
    source_excerpt: NonEmpty  # citation exacte du texte OCR, comme pour les notions


class LessonAnalysis(_Model):
    schema_version: str = ANALYSIS_SCHEMA_VERSION
    is_lesson: bool
    lesson: LessonInfo | None
    knowledge: list[KnowledgeItem]
    skills: list[Skill] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def item(self, knowledge_id: str) -> KnowledgeItem:
        return next(k for k in self.knowledge if k.id == knowledge_id)


# --------------------------------------------------------------------------- #
# Matériel pédagogique par notion (sortie de l'enrichissement, §6.3)
# --------------------------------------------------------------------------- #


class QuestionSource(_Model):
    """Question tirée d'un site éducatif de confiance (étape 29) : d'où elle vient, et la phrase
    de la page qui prouve la réponse. Jamais confondue avec la leçon (§117)."""

    site: NonEmpty
    url: NonEmpty
    quote: NonEmpty
    licence: str | None = None  # à citer avec la question (CC BY-SA de Vikidia, étape 30)


class MaterialQuestion(_Model):
    difficulty: int = Field(ge=1, le=3)
    stem: NonEmpty
    answer: NonEmpty
    distractors: list[NonEmpty] = Field(min_length=3, max_length=3)
    # Passage de la leçon à relire, affiché avec la question : l'enfant n'a plus la fiche.
    passage: str | None = Field(default=None, max_length=PASSAGE_MAX_LENGTH)
    # Type d'erreur que révèle chaque distracteur (même ordre), quand l'IA l'a indiqué.
    misconceptions: list[str | None] = Field(default_factory=list)
    # Absente : question tirée de la leçon. Présente : d'un site de confiance (étape 29).
    source: QuestionSource | None = None

    def misconception_of(self, distractor: str) -> str | None:
        index = self.distractors.index(distractor)
        return self.misconceptions[index] if index < len(self.misconceptions) else None


class Cloze(_Model):
    text: NonEmpty  # contient exactement un « ___ »
    answers: list[NonEmpty] = Field(min_length=1)


class Pair(_Model):
    left: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    right: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class Flashcard(_Model):
    front: NonEmpty
    back: NonEmpty


class WorkedExample(_Model):
    """Un exemple semblable, résolu (aide de niveau 3)."""

    question: NonEmpty
    answer: NonEmpty
    why: NonEmpty | None = None


class HelpLadder(_Model):
    """Aides graduées du bouton « Je n'ai pas compris » (spécification technique §5.4).

    Niveau 1 indice, 2 rappel, 3 exemple semblable, 4 étapes ; le niveau 5 (la réponse) vient
    de l'activité elle-même.
    """

    hint: NonEmpty | None = None
    reminder: NonEmpty | None = None
    example: WorkedExample | None = None
    steps: list[NonEmpty] = Field(default_factory=list)


class OpenQuestion(_Model):
    """Question à réponse rédigée, corrigée d'après ses points clés (§6.2, §6.4)."""

    level: int = Field(ge=3, le=5)  # 3 appliquer, 4 expliquer, 5 transférer
    prompt: NonEmpty
    key_points: list[NonEmpty] = Field(min_length=1, max_length=5)
    model_answer: NonEmpty
    passage: str | None = Field(default=None, max_length=PASSAGE_MAX_LENGTH)


class SortingBox(_Model):
    name: NonEmpty
    members: list[NonEmpty] = Field(min_length=2)


class Sorting(_Model):
    """Jeu de tri proposé par l'IA pour n'importe quelle notion (« Nom ou verbe ? ») : étape 25."""

    prompt: NonEmpty
    categories: list[SortingBox] = Field(min_length=2)


class Sequence(_Model):
    """Éléments à remettre dans l'ordre (« du plus petit au plus grand ») : étape 25."""

    prompt: NonEmpty
    items: list[NonEmpty] = Field(min_length=3)


class Spelling(_Model):
    """Un mot à savoir écrire (liste de mots, dictée à préparer) : jeux « Mot éclair » et
    « Lettres mélangées ». `sentence` : une phrase d'exemple où le mot est remplacé par « ___ »."""

    word: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=40)]
    sentence: NonEmpty | None = None


class KnowledgeMaterial(_Model):
    """Matériel validé : chaque élément présent a passé les contrôles de §6.4."""

    knowledge_id: KnowledgeId
    questions: list[MaterialQuestion] = Field(default_factory=list)
    true_statements: list[NonEmpty] = Field(default_factory=list)
    false_statements: list[NonEmpty] = Field(default_factory=list)
    cloze: Cloze | None = None
    pair: Pair | None = None
    flashcard: Flashcard | None = None
    tip: NonEmpty | None = None
    explanation: NonEmpty
    help: HelpLadder | None = None
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    sorting: Sorting | None = None
    sequence: Sequence | None = None
    spelling: Spelling | None = None

    def questions_of(self, difficulty: int) -> list[MaterialQuestion]:
        return [q for q in self.questions if q.difficulty == difficulty]

    def open_questions_of(self, level: int) -> list[OpenQuestion]:
        return [q for q in self.open_questions if q.level == level]


class KnowledgeUnit(_Model):
    """Une notion et son matériel : ce dont une activité a besoin pour être construite."""

    item: KnowledgeItem
    material: KnowledgeMaterial
    # Image qui montre la notion, validée par le parent (étape 28) : son adresse, opaque pour le
    # domaine. Absente le plus souvent : les jeux en images ne sont proposés qu'avec elle.
    picture: str | None = None

    @model_validator(mode="after")
    def _same_knowledge(self) -> "KnowledgeUnit":
        if self.item.id != self.material.knowledge_id:
            raise ValueError("le matériel ne correspond pas à la notion")
        return self

    @property
    def id(self) -> str:
        return self.item.id

    @property
    def type(self) -> KnowledgeType:
        return self.item.type
