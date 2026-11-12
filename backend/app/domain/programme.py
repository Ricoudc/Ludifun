"""Programme officiel par classe (cahier des charges §105) : Matière → Domaine → Compétence →
Sous-compétence → Notion.

Le référentiel (`programme.json`) résume les programmes de l'Éducation nationale du CP à la 3e,
par cycle : chaque sous-compétence dit à quelles classes elle appartient et par quels mots on la
reconnaît. Il est versionné : on en change le contenu en augmentant `version`, sans changer les
identifiants déjà utilisés.

Le code rattache chaque notion d'une leçon à la sous-compétence de sa matière et de la classe
de l'enfant qui partage le plus de mots avec elle (titre de la leçon, notion, phrase à retenir) ;
sinon, à celle d'une autre classe (une leçon de CE2 revue en CM1), sinon à rien. Pas d'IA : le
rattachement est le même avec toutes les IA, et il se recalcule si le référentiel change.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from app.domain.knowledge import Grade, Subject
from app.domain.sources import keywords

PROGRAMME_FILE = Path(__file__).with_name("programme.json")
GRADES = tuple(g.value for g in Grade)


@dataclass(frozen=True)
class SubCompetence:
    id: str  # « MA-07 » : stable d'une version à l'autre
    title: str
    grades: tuple[str, ...]
    words: frozenset[str]
    subject: str
    domain: str
    competence: str
    position: int  # ordre du programme, pour départager


@dataclass(frozen=True)
class Competence:
    title: str
    subs: tuple[SubCompetence, ...]


@dataclass(frozen=True)
class Domain:
    title: str
    competences: tuple[Competence, ...]


@dataclass(frozen=True)
class Programme:
    version: str
    source: str
    subjects: dict[str, tuple[Domain, ...]]

    def subs(self, subject: str, grade: str | None = None) -> list[SubCompetence]:
        """Sous-compétences d'une matière (d'une classe, si elle est donnée), dans l'ordre."""
        return [
            sub
            for domain in self.subjects.get(subject, ())
            for competence in domain.competences
            for sub in competence.subs
            if grade is None or grade in sub.grades
        ]

    def for_grade(self, subject: str, grade: str) -> list[Domain]:
        """Le programme d'une classe : seulement les domaines et compétences qui ont des
        sous-compétences dans cette classe."""
        domains = []
        for domain in self.subjects.get(subject, ()):
            competences = [
                Competence(c.title, tuple(s for s in c.subs if grade in s.grades)) for c in domain.competences
            ]
            kept = tuple(c for c in competences if c.subs)
            if kept:
                domains.append(Domain(domain.title, kept))
        return domains


@cache
def load_programme(path: Path = PROGRAMME_FILE) -> Programme:
    raw = json.loads(path.read_text(encoding="utf-8"))
    subjects: dict[str, tuple[Domain, ...]] = {}
    position = 0
    for subject, domains in raw["subjects"].items():
        built = []
        for domain in domains:
            competences = []
            for competence in domain["competences"]:
                subs = []
                for sub in competence["subs"]:
                    position += 1
                    subs.append(
                        SubCompetence(
                            id=sub["id"],
                            title=sub["title"],
                            grades=tuple(sub["grades"]),
                            words=frozenset(keywords(f"{sub['keywords']} {sub['title']}")),
                            subject=subject,
                            domain=domain["title"],
                            competence=competence["title"],
                            position=position,
                        )
                    )
                competences.append(Competence(competence["title"], tuple(subs)))
            built.append(Domain(domain["title"], tuple(competences)))
        subjects[subject] = tuple(built)
    return Programme(version=raw["version"], source=raw["source"], subjects=subjects)


@dataclass(frozen=True)
class Placement:
    """Où une notion se range dans le programme."""

    sub: SubCompetence
    grade_match: bool  # dans le programme de la classe de l'enfant


def _best(subs: Sequence[SubCompetence], words: set[str]) -> SubCompetence | None:
    scored = [(len(sub.words & words), -sub.position, sub) for sub in subs]
    scored = [s for s in scored if s[0] > 0]
    return max(scored, key=lambda s: (s[0], s[1]))[2] if scored else None


def place(programme: Programme, subject: str | None, grade: str | None, text: str) -> Placement | None:
    """La sous-compétence d'une notion (`text` : titre de la leçon, notion, phrase à retenir) :
    d'abord dans la classe de l'enfant, sinon dans une autre classe ; `None` hors programme."""
    if subject is None or subject not in programme.subjects or subject == Subject.OTHER:
        return None
    words = keywords(text)
    if grade in GRADES and (found := _best(programme.subs(subject, grade), words)) is not None:
        return Placement(found, grade_match=True)
    found = _best(programme.subs(subject), words)
    return Placement(found, grade_match=False) if found is not None else None
