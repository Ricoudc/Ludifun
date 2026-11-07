"""Listes de mots à savoir écrire (§5.68) : le code garantit les jeux d'écriture.

Quand la famille envoie une liste de mots (mots de la semaine, dictée à préparer, mots
invariables), le but est que l'enfant sache les écrire. L'IA doit fournir pour chaque mot le
matériel « spelling » (le mot recopié de la leçon) ; un petit modèle l'oublie parfois, et sans lui
aucun jeu d'écriture n'est possible. Le code reconnaît alors lui-même les mots de la liste et
leur donne ce matériel : le mot est la notion elle-même, écrit tel quel dans la leçon.

Une notion est un mot à savoir écrire quand :
- c'est une leçon de français (ou de matière inconnue) ;
- elle est un terme de 1 à 3 mots, sans chiffre, écrit tel quel dans le texte de la leçon ;
- la leçon parle d'écrire ces mots : une compétence de la notion (« Écrire sans erreur les mots
  de la liste », « orthographier ») ou le titre et l'objectif (« dictée », « liste de mots »,
  « mots de la semaine », « mots invariables », « orthographe ») ;
- et la leçon en compte au moins 3 (une liste, pas un mot isolé).
"""

import re

from app.domain.knowledge import KnowledgeItem, KnowledgeType, LessonAnalysis, Subject
from app.domain.validation import MaterialValidation, validate_material

MIN_WORDS = 3  # moins de mots : ce n'est pas une liste
_WORD = re.compile(r"^[^\W\d_]+(?:['’\- ][^\W\d_]+){0,2}$")
_WRITING_SKILL = re.compile(r"écri|ecri|orthograph|dictée|dictee", re.IGNORECASE)
_LIST_LESSON = re.compile(
    r"dictée|dictee|liste de mots|mots? (?:à|a) (?:savoir|apprendre|écrire|ecrire)"
    r"|mots de la semaine|mots invariables|orthographe",
    re.IGNORECASE,
)


def _in_text(label: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(label)}(?!\w)", text, re.IGNORECASE) is not None


def words_to_write(analysis: LessonAnalysis, text: str) -> set[str]:
    """Les notions (identifiants) qui sont les mots d'une liste à savoir écrire."""
    lesson = analysis.lesson
    if lesson is not None and lesson.subject not in (Subject.FRENCH, Subject.OTHER):
        return set()
    list_lesson = lesson is not None and bool(_LIST_LESSON.search(f"{lesson.title} {lesson.objective}"))
    writing = {k for s in analysis.skills if _WRITING_SKILL.search(s.label) for k in s.knowledge_ids}
    found = {
        item.id
        for item in analysis.knowledge
        if item.type == KnowledgeType.TERM
        and _WORD.match(item.label.strip())
        and _in_text(item.label.strip(), text)
        and (list_lesson or item.id in writing)
    }
    return found if len(found) >= MIN_WORDS else set()


def with_spelling(
    item: KnowledgeItem, validation: MaterialValidation | None, text: str
) -> MaterialValidation:
    """Le matériel de la notion, avec le mot à savoir écrire s'il manquait. Le mot passe par les
    mêmes contrôles que celui de l'IA (`validate_material`) ; sans matériel de l'IA, le mot seul
    (et la phrase « à retenir » comme explication) suffit aux jeux d'écriture."""
    if validation is not None and validation.material.spelling is not None:
        return validation
    word = validate_material(
        item, {"explanation": item.statement, "spelling": {"word": item.label.strip()}}, text
    )
    if word.material.spelling is None:  # mot refusé par les contrôles : rien n'est ajouté
        return validation if validation is not None else word
    if validation is None:
        return word
    material = validation.material.model_copy(update={"spelling": word.material.spelling})
    return MaterialValidation(material, validation.rejected)
