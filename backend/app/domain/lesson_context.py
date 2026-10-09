"""Les notions d'une leçon telles que l'enfant les joue : avec la matière et la classe de la leçon
(jeux de maths, de français…), et en maths sans exercice d'orthographe, avec les exercices
calculés par le code à la classe de l'enfant (§5.41). Utilisé par l'application
(`lesson_store.load_units`) et par l'évaluation sur de vraies leçons (`app.tools`), pour qu'elles
proposent les mêmes jeux.
"""

from collections.abc import Sequence

from app.domain.knowledge import Grade, KnowledgeUnit, Subject
from app.domain.math_generator import generated_questions, math_only


def in_context(
    units: Sequence[KnowledgeUnit], subject: Subject | None, grade: Grade | None
) -> list[KnowledgeUnit]:
    """Jamais deux fois la même question dans la leçon : une question calculée qui existe déjà
    (dans cette notion ou une précédente) n'est pas ajoutée."""
    math_grade = grade if subject == Subject.MATH else None
    stems: set[str] = set()
    result = []
    for unit in units:
        material = math_only(unit.material) if subject == Subject.MATH else unit.material
        stems.update(q.stem for q in material.questions)
        if math_grade is not None and (created := generated_questions(unit.item, math_grade, stems)):
            stems.update(q.stem for q in created)
            material = material.model_copy(update={"questions": [*material.questions, *created]})
        result.append(unit.model_copy(update={"material": material, "subject": subject, "grade": grade}))
    return result
