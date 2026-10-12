"""Validateurs automatiques des sorties de l'IA (cahier des charges §6.4).

Principe : on écarte l'élément fautif, pas la leçon entière. Chaque rejet est
tracé (`Rejection`) pour mesurer la qualité de l'IA pendant les tests.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.domain.child_safety import unsafe_reason
from app.domain.equivalence import all_different, same_answer, separate_boxes, statement_truth
from app.domain.errors import ErrorType
from app.domain.knowledge import (
    ATTRIBUTE_MODELS,
    Cloze,
    Flashcard,
    HelpLadder,
    KnowledgeItem,
    KnowledgeMaterial,
    KnowledgeType,
    LessonAnalysis,
    LessonInfo,
    MaterialQuestion,
    OpenQuestion,
    Pair,
    Sequence,
    Skill,
    Sorting,
    Spelling,
    Subject,
    WorkedExample,
    theme_fits,
)
from app.domain.text import (
    clean_markup,
    compatible_natures,
    contains_words,
    fuzzy_contains,
    gives_away,
    normalize,
    strip_markup,
)

TIP_MAX_LENGTH = 120
HELP_TEXT_MAX_LENGTH = 300
OPEN_QUESTIONS_MAX = 2
SORTING_BOXES = (2, 3)  # cases du jeu de tri
SORTING_MEMBERS = (2, 4)  # éléments par case
SEQUENCE_ITEMS = (3, 6)  # éléments à remettre dans l'ordre
BLANK = "___"
# Les photos des leçons ne sont jamais gardées (§15) : l'enfant ne verra pas l'image dont
# parlerait une question. Tout élément qui y renvoie est écarté.
_PICTURE = re.compile(
    r"\b(image|images|dessin|dessins|illustration|illustrations|photo|photos|schéma|schémas|"
    r"vignette|vignettes)\b|ci-dessus|ci-dessous|ci-contre|\b(regarde|observe|observez|regardez)\b",
    re.IGNORECASE,
)
PICTURE_REASON = "renvoie à une image de la leçon, que l'enfant ne verra pas"


def needs_picture(text: str) -> bool:
    return bool(_PICTURE.search(text))


# Plus largement, la fiche n'est plus devant l'enfant (photo prise sur Internet, dans un cahier…) :
# une question qui renvoie au texte lu, au tableau ou à l'exercice de la fiche est sans réponse
# possible. Les données utiles doivent être dans la question, ou dans le passage montré avec elle.
_SUPPORT = (
    r"textes?|documents?|fiches?|extraits?|récits?|poèmes?|tableaux?|graphiques?|frises?|"
    r"exercices?|pages?|lectures?|leçons?|listes?|étiquettes?|cases?|cadres?|encadrés?"
)
_ABSENT_SUPPORT = re.compile(
    rf"\b(ce|cet|cette|ces)\s+({_SUPPORT})\b"
    rf"|\b(d'après|d’après|selon|dans|sur)\s+(le|la|les|l'|l’)\s*({_SUPPORT})\b"
    r"|\b(de\s+la|de\s+l'|de\s+l’|du)\s*(liste|fiche|leçon|texte|tableau)\b"
    r"|\b(le|la|l'|l’)\s*(texte|histoire|récit|poème|extrait)\s+(lu|lue|étudié|étudiée|précédent|précédente)\b"
    r"|\b(que tu as lu|que tu viens de lire|lu en classe|lue en classe)\b"
    r"|\b(exercice|question)\s+(n°\s*)?\d",
    re.IGNORECASE,
)
SUPPORT_REASON = "renvoie à la fiche ou à un texte que l'enfant n'aura plus sous les yeux"
PAIR_REASON = "les deux côtés de la paire sont pareils, ou l'un contient l'autre : rien à chercher"
PASSAGE_REASON = "le passage à relire n'est pas recopié de la leçon"


def needs_support(text: str) -> bool:
    """Le texte renvoie à la fiche photographiée (texte lu, tableau, exercice…)."""
    return bool(_ABSENT_SUPPORT.search(text))


def _absent(text: str) -> str | None:
    """Raison du rejet d'un texte montré seul à l'enfant, ou None s'il se suffit à lui-même."""
    if needs_picture(text):
        return PICTURE_REASON
    if needs_support(text):
        return SUPPORT_REASON
    return None


def _passage(raw: Any, source: str) -> tuple[str | None, str | None]:
    """Passage à relire montré avec la question : recopié de la leçon, sinon la question est
    écartée (l'IA pourrait inventer le texte sur lequel elle interroge)."""
    if not isinstance(raw, str) or not raw.strip():
        return None, None
    passage = raw.strip()
    if not fuzzy_contains(source, passage):
        return None, PASSAGE_REASON
    return passage, None


class AnalysisError(ValueError):
    """La sortie de l'analyse est inexploitable dans son ensemble (pas seulement une notion)."""


@dataclass(frozen=True)
class Rejection:
    element: str  # "k3", "questions[1]", "cloze"…
    reason: str


@dataclass(frozen=True)
class AnalysisValidation:
    analysis: LessonAnalysis
    rejected: list[Rejection] = field(default_factory=list)


@dataclass(frozen=True)
class MaterialValidation:
    material: KnowledgeMaterial
    rejected: list[Rejection] = field(default_factory=list)

    @property
    def kept(self) -> int:
        """Nombre d'éléments de matériel conservés."""
        m = self.material
        optional = (m.cloze, m.pair, m.flashcard, m.tip, m.sorting, m.sequence, m.spelling)
        return (
            len(m.questions)
            + len(m.true_statements)
            + len(m.false_statements)
            + sum(x is not None for x in optional)
            + len(m.open_questions)
            + (m.help is not None)
        )

    @property
    def rejection_rate(self) -> float:
        total = self.kept + len(self.rejected)
        return len(self.rejected) / total if total else 0.0


def _first_error(exc: ValidationError) -> str:
    error = exc.errors()[0]
    location = ".".join(str(part) for part in error["loc"])
    return f"{location}: {error['msg']}" if location else error["msg"]


# --------------------------------------------------------------------------- #
# Analyse de la leçon
# --------------------------------------------------------------------------- #


def validate_analysis(raw: Mapping[str, Any], ocr_text: str) -> AnalysisValidation:
    raw, ocr_text = clean_markup(dict(raw)), strip_markup(ocr_text)
    if not isinstance(raw.get("is_lesson"), bool):
        raise AnalysisError("is_lesson manquant")
    if not raw["is_lesson"]:
        return AnalysisValidation(LessonAnalysis(is_lesson=False, lesson=None, knowledge=[]))
    try:
        lesson = LessonInfo.model_validate(raw.get("lesson"))
    except ValidationError as exc:
        raise AnalysisError(f"leçon invalide ({_first_error(exc)})") from exc

    rejected: list[Rejection] = []
    repairs: list[str] = []
    items: list[KnowledgeItem] = []
    raw_items = raw.get("knowledge")
    for index, raw_item in enumerate(raw_items if isinstance(raw_items, list) else []):
        name = raw_item.get("id") if isinstance(raw_item, dict) else None
        element = str(name) if name else f"knowledge[{index}]"
        raw_item, repaired = repair_attributes(raw_item)
        if repaired:
            repairs.append(f"{element} : {repaired}")
        raw_item, theme_problem = _check_theme(raw_item, lesson.subject)
        if theme_problem:
            repairs.append(f"{element} : {theme_problem}")
        try:
            item = KnowledgeItem.model_validate(raw_item)
        except ValidationError as exc:
            rejected.append(Rejection(element, _first_error(exc)))
            continue
        if any(existing.id == item.id for existing in items):
            rejected.append(Rejection(element, "identifiant en double"))
        elif reason := unsafe_reason(item.model_dump(mode="json"), ocr_text):
            rejected.append(Rejection(element, reason))
        elif not fuzzy_contains(ocr_text, item.source_excerpt):
            rejected.append(Rejection(element, "source_excerpt introuvable dans le texte de la leçon"))
        else:
            items.append(item)

    # Une relation vers une notion absente (ou rejetée) est retirée, la notion est gardée.
    known = {item.id for item in items}
    warnings = [w for w in raw.get("warnings", []) if isinstance(w, str)] + repairs
    cleaned: list[KnowledgeItem] = []
    for item in items:
        relations = [r for r in item.relations if r.target in known and r.target != item.id]
        if len(relations) != len(item.relations):
            warnings.append(f"{item.id} : relation vers une notion inconnue retirée")
        cleaned.append(item.model_copy(update={"relations": relations}))

    skills = _validate_skills(raw.get("skills"), known, ocr_text, rejected, warnings)
    analysis = LessonAnalysis(
        schema_version=str(raw.get("schema_version", "1.0")),
        is_lesson=True,
        lesson=lesson,
        knowledge=cleaned,
        skills=skills,
        warnings=warnings,
    )
    return AnalysisValidation(analysis, rejected)


def _check_theme(raw_item: Any, subject: Subject) -> tuple[Any, str | None]:
    """Thème hors de la liste ou d'une autre matière : retiré, la notion est gardée (§5.47)."""
    if not isinstance(raw_item, dict) or raw_item.get("theme") is None:
        return raw_item, None
    proposed = raw_item["theme"]
    theme = theme_fits(proposed, subject)
    cleaned = {**raw_item, "theme": theme}
    if theme is None:
        return cleaned, f"thème « {str(proposed)[:40]} » retiré (hors liste ou autre matière)"
    return cleaned, None


# Un seul texte manquant, que la phrase « à retenir » dit déjà (petits modèles : souvent oublié).
_FROM_STATEMENT = {
    KnowledgeType.TERM: "definition",
    KnowledgeType.PERSON: "role",
    KnowledgeType.PLACE: "description",
}


def repair_attributes(raw_item: Any) -> tuple[Any, str | None]:
    """Attributs incomplets (champ oublié par l'IA) : la notion est gardée plutôt qu'écartée.

    Un texte manquant est repris de la phrase « à retenir » (définition d'un mot, rôle d'un
    personnage, description d'un lieu) ; sinon la notion devient un simple fait, sans attribut
    (elle perd seulement les jeux propres à son type : frise, étapes, rangement…). Rien n'est
    inventé : la notion reste tirée de la leçon et doit toujours citer le texte.
    """
    if not isinstance(raw_item, dict):
        return raw_item, None
    try:
        kind = KnowledgeType(str(raw_item.get("type")))
    except ValueError:
        return raw_item, None
    attributes = raw_item.get("attributes")
    attributes = dict(attributes) if isinstance(attributes, dict) else {}
    try:
        ATTRIBUTE_MODELS[kind].model_validate(attributes)
        return raw_item, None
    except ValidationError:
        pass
    statement = raw_item.get("statement")
    field_name = _FROM_STATEMENT.get(kind)
    if field_name and isinstance(statement, str) and statement.strip():
        filled = {**attributes, field_name: statement.strip()}
        try:
            ATTRIBUTE_MODELS[kind].model_validate(filled)
            return {
                **raw_item,
                "attributes": filled,
            }, f"« {field_name} » absent, repris de la phrase à retenir"
        except ValidationError:
            pass
    return (
        {**raw_item, "type": KnowledgeType.FACT.value, "attributes": {}},
        f"attributs de « {kind.value} » incomplets : gardée comme simple fait",
    )


def _validate_skills(
    raw_skills: Any, known: set[str], ocr_text: str, rejected: list[Rejection], warnings: list[str]
) -> list[Skill]:
    """Une compétence doit citer la leçon et s'appuyer sur au moins une notion retenue."""
    skills: list[Skill] = []
    for index, raw_skill in enumerate(raw_skills if isinstance(raw_skills, list) else []):
        name = raw_skill.get("id") if isinstance(raw_skill, dict) else None
        element = str(name) if name else f"skills[{index}]"
        if isinstance(raw_skill, dict) and isinstance(raw_skill.get("knowledge_ids"), list):
            ids = [k for k in raw_skill["knowledge_ids"] if isinstance(k, str)]
            linked = list(dict.fromkeys(k for k in ids if k in known))
            if len(linked) != len(ids):
                warnings.append(f"{element} : lien vers une notion inconnue retiré")
            raw_skill = {**raw_skill, "knowledge_ids": linked}
        try:
            skill = Skill.model_validate(raw_skill)
        except ValidationError as exc:
            rejected.append(Rejection(element, _first_error(exc)))
            continue
        if any(existing.id == skill.id for existing in skills):
            rejected.append(Rejection(element, "identifiant en double"))
        elif not fuzzy_contains(ocr_text, skill.source_excerpt):
            rejected.append(Rejection(element, "source_excerpt introuvable dans le texte de la leçon"))
        else:
            skills.append(skill)
    return skills


# --------------------------------------------------------------------------- #
# Matériel par notion
# --------------------------------------------------------------------------- #

_NEGATION_WORDS = {"ne", "n", "pas", "jamais", "plus"}
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ'-]*")
_SENTENCE_START = re.compile(r"(^|[.!?:]\s+)$")


def _without_negation(sentence: str) -> str:
    return " ".join(w for w in normalize(sentence).split() if w not in _NEGATION_WORDS)


INCOMPLETE_REASON = "la même question a plusieurs réponses : il manque la donnée (laquelle ?)"
INSTRUCTION_REASON = "c'est une consigne d'exercice, pas une affirmation vraie ou fausse"
CLOZE_MAX_ANSWERS = 3
# Verbes de consigne : une phrase qui commence ainsi dit quoi faire, elle n'affirme rien.
_INSTRUCTION = re.compile(
    r"^(ecri(s|re|vez)|indique(r|z)?|remplace(r|z)?|complete(r|z)?|range(r|z)?|relie(r|z)?|"
    r"souligne(r|z)?|entoure(r|z)?|colorie(r|z)?|calcule(r|z)?|trouve(r|z)?|recopie(r|z)?|"
    r"coche(r|z)?|barre(r|z)?|classe(r|z)?)\b"
)


def is_instruction(text: str) -> bool:
    return _INSTRUCTION.match(normalize(text)) is not None


def _check_question(raw: Any) -> tuple[MaterialQuestion | None, str]:
    if not isinstance(raw, dict):
        return None, "format invalide"
    answer = str(raw.get("answer", "")).strip()
    stem = str(raw.get("stem", "")).strip()
    raw_distractors = raw.get("distractors")
    distractors: list[str] = []
    misconceptions: list[str | None] = []
    for d in raw_distractors if isinstance(raw_distractors, list) else []:
        # Matériel v2 : {"text", "misconception"} ; v1 : le texte seul.
        text = str(d.get("text", "") if isinstance(d, dict) else d).strip()
        kind = d.get("misconception") if isinstance(d, dict) else None
        # « 8 + 7 » pour la réponse « 7 + 8 » : deux bonnes réponses, le distracteur est écarté.
        if (
            text
            and not any(same_answer(text, seen) for seen in [answer, *distractors])
            and compatible_natures(answer, text)
        ):
            distractors.append(text)
            misconceptions.append(kind if kind in ErrorType else None)
    if answer and stem and contains_words(stem, answer):
        return None, "l'énoncé contient la réponse"
    if len(distractors) < 3:
        return None, (
            "moins de 3 distracteurs valides (distincts, de valeur différente de la réponse, de même nature)"
        )
    try:
        data = {**raw, "distractors": distractors[:3], "misconceptions": misconceptions[:3]}
        if not any(misconceptions[:3]):
            data["misconceptions"] = []
        return MaterialQuestion.model_validate(data), ""
    except ValidationError as exc:
        return None, _first_error(exc)


def check_question(raw: Any) -> tuple[MaterialQuestion | None, str]:
    """Une question à choix, contrôlée comme celles du matériel (énoncé, réponse, distracteurs)."""
    return _check_question(raw)


def _check_cloze(raw: Any) -> tuple[Cloze | None, str]:
    try:
        cloze = Cloze.model_validate(raw)
    except ValidationError as exc:
        return None, _first_error(exc)
    if cloze.text.count(BLANK) != 1:
        return None, "la phrase doit contenir exactement un « ___ »"
    if len({normalize(a) for a in cloze.answers}) > CLOZE_MAX_ANSWERS:
        return None, "trop de réponses différentes : il manque la donnée qui dit laquelle écrire"
    rest = cloze.text.replace(BLANK, " ")
    if any(contains_words(rest, answer) for answer in cloze.answers):
        return None, "la réponse apparaît ailleurs dans la phrase"
    return cloze, ""


def _check_tip(tip: str, item: KnowledgeItem) -> str:
    if len(tip) > TIP_MAX_LENGTH:
        return f"astuce trop longue (> {TIP_MAX_LENGTH} caractères)"
    corpus = item.corpus()
    corpus_numbers = {n.replace(",", ".") for n in _NUMBER.findall(corpus)}
    for number in _NUMBER.findall(tip):
        if number.replace(",", ".") not in corpus_numbers:
            return f"l'astuce contient un nombre absent de la notion ({number})"
    corpus_words = set(normalize(corpus).split())
    for match in _WORD.finditer(tip):
        word = match.group()
        at_sentence_start = _SENTENCE_START.search(tip[: match.start()]) is not None
        if word[0].isupper() and not at_sentence_start and not set(normalize(word).split()) <= corpus_words:
            return f"l'astuce contient un nom propre absent de la notion ({word})"
    return ""


def _screen_for_child(raw: Mapping[str, Any], context: str, rejected: list[Rejection]) -> dict[str, Any]:
    """§141 : chaque élément destiné à l'enfant qui contient un passage inadapté, absent de la
    leçon, est écarté (le reste de la notion est gardé)."""
    screened: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(value, list):
            kept = []
            for i, element in enumerate(value):
                if reason := unsafe_reason(element, context):
                    rejected.append(Rejection(f"{key}[{i}]", reason))
                else:
                    kept.append(element)
            screened[key] = kept
        elif reason := unsafe_reason(value, context):
            rejected.append(Rejection(key, reason))
        else:
            screened[key] = value
    return screened


def validate_material(
    item: KnowledgeItem, raw: Mapping[str, Any], lesson_text: str | None = None
) -> MaterialValidation:
    """`lesson_text` : le texte de la leçon, dont un passage à relire doit être recopié (sans
    lui, le passage doit venir de la notion)."""
    rejected: list[Rejection] = []
    raw = clean_markup(dict(raw))
    source = strip_markup(lesson_text) if lesson_text is not None else item.corpus()
    raw = _screen_for_child(raw, f"{source}\n{item.corpus()}", rejected)

    questions: list[MaterialQuestion] = []
    raw_questions = raw.get("questions")
    for i, raw_question in enumerate(raw_questions if isinstance(raw_questions, list) else []):
        question, reason = _check_question(raw_question)
        if question is not None:
            passage, passage_reason = _passage(question.passage, source)
            question = question.model_copy(update={"passage": passage})
            if passage_reason:
                question, reason = None, passage_reason
            elif needs_picture(question.stem):
                question, reason = None, PICTURE_REASON
            elif passage is None and needs_support(question.stem):
                question, reason = None, SUPPORT_REASON
        if question is None:
            rejected.append(Rejection(f"questions[{i}]", reason))
        else:
            questions.append(question)

    # Une fiche d'exercices recopiée : la même consigne (« Écris la lettre qui précède. ») pour
    # plusieurs questions aux réponses différentes. Il manque la donnée (laquelle ?) : sans elle,
    # l'enfant ne peut pas répondre.
    answers_by_stem: dict[str, set[str]] = {}
    for question in questions:
        answers_by_stem.setdefault(normalize(question.stem), set()).add(normalize(question.answer))
    incomplete = {stem for stem, answers in answers_by_stem.items() if len(answers) > 1}
    kept_questions: list[MaterialQuestion] = []
    for question in questions:
        stem = normalize(question.stem)
        if stem in incomplete:
            rejected.append(Rejection("questions", INCOMPLETE_REASON))
        elif any(normalize(q.stem) == stem for q in kept_questions):
            rejected.append(Rejection("questions", "question en double"))
        else:
            kept_questions.append(question)
    questions = kept_questions

    true_statements: list[str] = []
    raw_true = raw.get("true_statements")
    for i, s in enumerate(raw_true if isinstance(raw_true, list) else []):
        text = str(s).strip()
        if not text or normalize(text) in {normalize(t) for t in true_statements}:
            rejected.append(Rejection(f"true_statements[{i}]", "vide ou en double"))
        elif (absent := _absent(text)) is not None:
            rejected.append(Rejection(f"true_statements[{i}]", absent))
        elif is_instruction(text):
            rejected.append(Rejection(f"true_statements[{i}]", INSTRUCTION_REASON))
        elif statement_truth(text) is False:
            rejected.append(Rejection(f"true_statements[{i}]", "calcul faux donné pour vrai"))
        else:
            true_statements.append(text)

    truths = [item.statement, *true_statements]
    false_statements: list[str] = []
    raw_false = raw.get("false_statements")
    for i, s in enumerate(raw_false if isinstance(raw_false, list) else []):
        text = str(s).strip()
        if not text or normalize(text) in {normalize(f) for f in false_statements}:
            rejected.append(Rejection(f"false_statements[{i}]", "vide ou en double"))
        elif (absent := _absent(text)) is not None:
            rejected.append(Rejection(f"false_statements[{i}]", absent))
        elif is_instruction(text):
            rejected.append(Rejection(f"false_statements[{i}]", INSTRUCTION_REASON))
        elif statement_truth(text) is True:
            rejected.append(Rejection(f"false_statements[{i}]", "calcul juste donné pour faux"))
        elif any(normalize(text) == normalize(t) for t in truths):
            rejected.append(Rejection(f"false_statements[{i}]", "identique à une affirmation vraie"))
        elif any(_without_negation(text) == _without_negation(t) for t in truths):
            rejected.append(Rejection(f"false_statements[{i}]", "simple négation d'une affirmation vraie"))
        else:
            false_statements.append(text)

    cloze: Cloze | None = None
    if raw.get("cloze") is not None:
        cloze, reason = _check_cloze(raw["cloze"])
        if cloze is not None and (absent := _absent(cloze.text)) is not None:
            cloze, reason = None, absent
        if cloze is None:
            rejected.append(Rejection("cloze", reason))

    pair: Pair | None = None
    if raw.get("pair") is not None:
        try:
            pair = Pair.model_validate(raw["pair"])
            if (absent := _absent(f"{pair.left} {pair.right}")) is not None:
                pair = None
                rejected.append(Rejection("pair", absent))
            elif gives_away(pair.left, pair.right):
                pair = None
                rejected.append(Rejection("pair", PAIR_REASON))
        except ValidationError as exc:
            rejected.append(Rejection("pair", _first_error(exc)))

    flashcard: Flashcard | None = None
    if raw.get("flashcard") is not None:
        try:
            flashcard = Flashcard.model_validate(raw["flashcard"])
            if normalize(flashcard.front) == normalize(flashcard.back):
                flashcard = None
                rejected.append(Rejection("flashcard", "recto et verso identiques"))
            elif (absent := _absent(flashcard.front)) is not None:
                flashcard = None
                rejected.append(Rejection("flashcard", absent))
        except ValidationError as exc:
            rejected.append(Rejection("flashcard", _first_error(exc)))

    tip: str | None = None
    if isinstance(raw.get("tip"), str) and raw["tip"].strip():
        reason = _check_tip(raw["tip"].strip(), item)
        if reason:
            rejected.append(Rejection("tip", reason))
        else:
            tip = raw["tip"].strip()

    explanation = raw.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        rejected.append(Rejection("explanation", "absente : la phrase « à retenir » est utilisée"))
        explanation = item.statement

    help_ladder = _check_help(raw.get("help"), item, rejected)
    open_questions: list[OpenQuestion] = []
    raw_open = raw.get("open_questions")
    for i, raw_question in enumerate(raw_open if isinstance(raw_open, list) else []):
        try:
            open_question = OpenQuestion.model_validate(raw_question)
            passage, passage_reason = _passage(open_question.passage, source)
            open_question = open_question.model_copy(update={"passage": passage})
            refused = (
                passage_reason
                or (PICTURE_REASON if needs_picture(open_question.prompt) else None)
                or (SUPPORT_REASON if passage is None and needs_support(open_question.prompt) else None)
            )
            if refused:
                rejected.append(Rejection(f"open_questions[{i}]", refused))
                continue
            if normalize(open_question.model_answer).startswith(normalize(open_question.prompt)):
                rejected.append(Rejection(f"open_questions[{i}]", "la réponse attendue recopie la question"))
                continue
            open_questions.append(open_question)
        except ValidationError as exc:
            rejected.append(Rejection(f"open_questions[{i}]", _first_error(exc)))

    sorting = _check_sorting(raw.get("sorting"), rejected)
    sequence = _check_sequence(raw.get("sequence"), rejected)
    spelling = _check_spelling(raw.get("spelling"), item, rejected)

    material = KnowledgeMaterial(
        knowledge_id=item.id,
        questions=questions,
        true_statements=true_statements,
        false_statements=false_statements,
        cloze=cloze,
        pair=pair,
        flashcard=flashcard,
        tip=tip,
        explanation=explanation.strip(),
        help=help_ladder,
        open_questions=open_questions[:OPEN_QUESTIONS_MAX],
        sorting=sorting,
        sequence=sequence,
        spelling=spelling,
    )
    return MaterialValidation(material, rejected)


def _check_sorting(raw: Any, rejected: list[Rejection]) -> Sorting | None:
    """Jeu de tri : 2 ou 3 cases de 2 à 4 éléments, chaque élément dans une seule case."""
    if raw is None:
        return None
    try:
        sorting = Sorting.model_validate(raw)
    except ValidationError as exc:
        rejected.append(Rejection("sorting", _first_error(exc)))
        return None
    if (absent := _absent(sorting.prompt)) is not None:
        rejected.append(Rejection("sorting", absent))
        return None
    boxes = sorting.categories
    members = [normalize(m) for box in boxes for m in box.members]
    names = {normalize(box.name) for box in boxes}
    reason = (
        "il faut 2 ou 3 cases"
        if not SORTING_BOXES[0] <= len(boxes) <= SORTING_BOXES[1]
        else "il faut 2 à 4 éléments par case"
        if any(not SORTING_MEMBERS[0] <= len(box.members) <= SORTING_MEMBERS[1] for box in boxes)
        else "un élément est dans deux cases, ou deux cases ont le même nom"
        if len(set(members)) != len(members)
        or len(names) != len(boxes)
        or not separate_boxes([box.members for box in boxes])
        else "un élément porte le nom d'une case (la réponse serait donnée)"
        if names & set(members)
        else None
    )
    if reason:
        rejected.append(Rejection("sorting", reason))
        return None
    return sorting


def _check_sequence(raw: Any, rejected: list[Rejection]) -> Sequence | None:
    """Éléments à remettre dans l'ordre : 3 à 6, tous différents."""
    if raw is None:
        return None
    try:
        sequence = Sequence.model_validate(raw)
    except ValidationError as exc:
        rejected.append(Rejection("sequence", _first_error(exc)))
        return None
    if (absent := _absent(sequence.prompt)) is not None:
        rejected.append(Rejection("sequence", absent))
        return None
    items = [normalize(i) for i in sequence.items]
    if (
        not SEQUENCE_ITEMS[0] <= len(items) <= SEQUENCE_ITEMS[1]
        or len(set(items)) != len(items)
        or not all_different(sequence.items)
    ):
        rejected.append(Rejection("sequence", "il faut 3 à 6 éléments, tous différents"))
        return None
    return sequence


def _check_spelling(raw: Any, item: KnowledgeItem, rejected: list[Rejection]) -> Spelling | None:
    """Mot à savoir écrire : il vient de la notion, écrit exactement pareil (accents compris,
    c'est l'orthographe qui est apprise) ; la phrase d'exemple a un seul « ___ » et ne le
    donne pas."""
    if raw is None:
        return None
    try:
        spelling = Spelling.model_validate(raw)
    except ValidationError as exc:
        rejected.append(Rejection("spelling", _first_error(exc)))
        return None
    source = " ".join((item.label, item.statement, item.source_excerpt)).casefold().replace("’", "'")
    word = spelling.word.casefold().replace("’", "'")
    if word not in source:
        rejected.append(Rejection("spelling", "mot absent de la notion (orthographe différente ?)"))
        return None
    if normalize(spelling.word) != normalize(item.label):
        # Un mot à savoir écrire est la notion elle-même (une liste de mots), pas un mot pris
        # dans une consigne (« lettre » dans « Écrire des lettres dans l'ordre »).
        rejected.append(Rejection("spelling", "ce n'est pas le mot de la notion"))
        return None
    sentence = spelling.sentence
    if sentence is not None and (
        sentence.count("___") != 1 or word in sentence.casefold() or _absent(sentence) is not None
    ):
        spelling = spelling.model_copy(update={"sentence": None})  # le mot reste, sans la phrase
    return spelling


def _check_help(raw: Any, item: KnowledgeItem, rejected: list[Rejection]) -> HelpLadder | None:
    """Aides graduées : l'indice et le rappel n'inventent rien (comme l'astuce) ; l'exemple, lui,
    prend volontairement d'autres valeurs que la leçon. Qu'une aide ne dévoile pas la réponse
    d'un exercice est vérifié au moment de la montrer (`app.domain.help`)."""
    if not isinstance(raw, dict):
        return None
    hint = raw.get("hint") if isinstance(raw.get("hint"), str) and raw["hint"].strip() else None
    if hint is not None and (reason := _check_tip(hint.strip(), item)):
        rejected.append(Rejection("help.hint", reason.replace("astuce", "indice")))
        hint = None
    reminder = (
        raw.get("reminder") if isinstance(raw.get("reminder"), str) and raw["reminder"].strip() else None
    )
    if reminder is not None and len(reminder) > HELP_TEXT_MAX_LENGTH:
        rejected.append(Rejection("help.reminder", f"rappel trop long (> {HELP_TEXT_MAX_LENGTH} caractères)"))
        reminder = None
    example: WorkedExample | None = None
    if raw.get("example") is not None:
        try:
            example = WorkedExample.model_validate(raw["example"])
        except ValidationError as exc:
            rejected.append(Rejection("help.example", _first_error(exc)))
    raw_steps = raw.get("steps")
    steps = [str(s).strip() for s in (raw_steps if isinstance(raw_steps, list) else []) if str(s).strip()]
    ladder = HelpLadder(hint=hint, reminder=reminder, example=example, steps=steps[:6])
    return ladder if (hint or reminder or example or steps) else None


def merge_material(first: MaterialValidation, second: MaterialValidation) -> MaterialValidation:
    """Deux versions validées du matériel d'une notion : on garde tout ce qui a passé les
    contrôles dans la première, et on complète avec les éléments nouveaux de la seconde (la
    relance après refus). Les refus restants sont ceux de la seconde version."""
    a, b = first.material, second.material
    stems = {normalize(q.stem) for q in a.questions}
    questions = a.questions + [q for q in b.questions if normalize(q.stem) not in stems]
    truths = {normalize(t) for t in a.true_statements}
    falses = {normalize(f) for f in a.false_statements}
    true_statements = a.true_statements + [
        t for t in b.true_statements if normalize(t) not in truths | falses
    ]
    false_statements = a.false_statements + [
        f for f in b.false_statements if normalize(f) not in truths | falses
    ]
    prompts = {normalize(q.prompt) for q in a.open_questions}
    open_questions = a.open_questions + [q for q in b.open_questions if normalize(q.prompt) not in prompts]
    merged = a.model_copy(
        update={
            "questions": questions,
            "true_statements": true_statements,
            "false_statements": false_statements,
            "cloze": a.cloze or b.cloze,
            "pair": a.pair or b.pair,
            "flashcard": a.flashcard or b.flashcard,
            "tip": a.tip or b.tip,
            "help": a.help or b.help,
            "open_questions": open_questions[:OPEN_QUESTIONS_MAX],
            "sorting": a.sorting or b.sorting,
            "sequence": a.sequence or b.sequence,
            "spelling": a.spelling or b.spelling,
        }
    )
    return MaterialValidation(merged, second.rejected)
