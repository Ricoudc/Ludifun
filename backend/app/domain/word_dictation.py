"""Dictée à partir d'une liste de mots (§5.99) : la leçon est fabriquée par le code, sans IA.

Le parent (ou l'enfant) tape les mots de la semaine, un par ligne, avec s'il le veut une phrase
qui l'emploie : « chaton : Le chaton dort sur le lit. ». Chaque mot devient une notion « mot à
savoir écrire » (§5.68), avec le matériel d'orthographe contrôlé comme celui de l'IA
(`validate_material`) : mot éclair, lettres mélangées, dictée du mot, et, avec une phrase,
dictée de la phrase et texte à trous. Rien n'est inventé : sans IA, pas de définition ni de
phrase que la famille n'a pas écrite.

Pur : pas de base, pas de réseau.
"""

import re
from dataclasses import dataclass, field

from app.domain.knowledge import (
    Grade,
    KnowledgeItem,
    KnowledgeType,
    LessonAnalysis,
    LessonInfo,
    Skill,
    SkillVerb,
    Subject,
)
from app.domain.validation import MaterialValidation, validate_material
from app.domain.word_list import _WORD, MIN_WORDS

MAX_WORDS = 30  # une dictée de la semaine, pas un dictionnaire
MAX_SENTENCE_CHARS = 200
DEFAULT_TITLE = "Dictée"
MAX_TITLE_CHARS = 80
OBJECTIVE = "Savoir écrire sans erreur les mots de la liste."
SKILL_LABEL = "Écrire sans erreur les mots de la liste"

_BULLET = re.compile(r"^\s*(?:[-•*·–—]|\d{1,2}[.)])\s*")
_SEPARATOR = re.compile(r"\s*[:=]\s*")


@dataclass(frozen=True)
class WordEntry:
    word: str
    sentence: str | None = None


@dataclass
class WordList:
    entries: list[WordEntry] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # pour la famille, ligne par ligne


def _apostrophe(text: str) -> str:
    return text.replace("’", "'")


def _find(word: str, sentence: str) -> re.Match[str] | None:
    """Le mot dans la phrase, en entier, sans compter les majuscules ni l'apostrophe."""
    return re.search(rf"(?<!\w){re.escape(_apostrophe(word))}(?!\w)", _apostrophe(sentence), re.IGNORECASE)


def _lines(text: str) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) == 1 and ":" not in lines[0] and "=" not in lines[0]:
        lines = re.split(r"[,;]", lines[0])  # « chaton, maison, école » sur une ligne
    return [_BULLET.sub("", line).strip() for line in lines if _BULLET.sub("", line).strip()]


def parse_word_list(text: str) -> WordList:
    """Un mot par ligne (1 à 3 mots, sans chiffre), suivi s'il le faut de « : » et d'une phrase
    qui l'emploie ; ou des mots séparés par des virgules sur une seule ligne. Les doublons sont
    ignorés ; chaque ligne refusée l'est avec sa raison."""
    result = WordList()
    seen: set[str] = set()
    for number, line in enumerate(_lines(text), 1):
        word, sentence_part = _split(line)
        if not _WORD.match(word):
            result.problems.append(f"Ligne {number} : « {word} » n'est pas un mot (pas de chiffre).")
            continue
        sentence = sentence_part or None
        if sentence is not None:
            if len(sentence) > MAX_SENTENCE_CHARS:
                result.problems.append(f"Ligne {number} : la phrase est trop longue.")
                continue
            if _find(word, sentence) is None:
                result.problems.append(f"Ligne {number} : la phrase ne contient pas le mot « {word} ».")
                continue
        key = _apostrophe(word).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.entries.append(WordEntry(word, sentence))
    if len(result.entries) > MAX_WORDS:
        result.problems.append(f"{MAX_WORDS} mots au plus pour une dictée.")
    elif len(result.entries) < MIN_WORDS and not result.problems:
        result.problems.append(f"Au moins {MIN_WORDS} mots pour une dictée.")
    return result


def _split(line: str) -> tuple[str, str]:
    """« chaton : Le chaton dort. » → le mot, puis la phrase (vide s'il n'y en a pas)."""
    parts = _SEPARATOR.split(line, maxsplit=1)
    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""


@dataclass(frozen=True)
class DictationLesson:
    text: str  # le texte de la leçon, tel que la famille l'a écrit (mis en forme)
    analysis: LessonAnalysis
    materials: dict[str, MaterialValidation]


def _line(entry: WordEntry) -> str:
    return f"{entry.word} : {entry.sentence}" if entry.sentence else entry.word


def _blank(entry: WordEntry) -> str | None:
    """La phrase avec « ___ » à la place du mot (texte à trous), si elle a un sens sans lui."""
    if entry.sentence is None:
        return None
    found = _find(entry.word, entry.sentence)
    if found is None:
        return None
    return entry.sentence[: found.start()] + "___" + entry.sentence[found.end() :]


def dictation_lesson(entries: list[WordEntry], title: str | None, grade: Grade | None) -> DictationLesson:
    """La leçon complète : texte, analyse (une notion par mot, une compétence d'écriture) et
    matériel contrôlé. `grade` : la classe de l'enfant (inconnue : CE2, confiance nulle)."""
    name = (title or "").strip()[:MAX_TITLE_CHARS] or DEFAULT_TITLE
    if not re.search(r"dict[ée]e", name, re.IGNORECASE):
        name = f"{DEFAULT_TITLE} : {name}"  # le titre dit la liste de mots (§5.68)
    text = "\n".join([name, *(_line(e) for e in entries)])
    items: list[KnowledgeItem] = []
    for number, entry in enumerate(entries, 1):
        statement = entry.sentence or f"Savoir écrire le mot « {entry.word} »."
        items.append(
            KnowledgeItem(
                id=f"k{number}",
                type=KnowledgeType.TERM,
                label=entry.word,
                statement=statement,
                importance=3,
                attributes={"definition": entry.sentence or f"Mot de la dictée : {entry.word}"},
                source_excerpt=_line(entry),
            )
        )
    words = ", ".join(e.word for e in entries[:5]) + ("…" if len(entries) > 5 else "")
    analysis = LessonAnalysis(
        is_lesson=True,
        lesson=LessonInfo(
            subject=Subject.FRENCH,
            grade=grade or Grade.CE2,
            grade_confidence=1.0 if grade is not None else 0.0,
            title=name,
            objective=OBJECTIVE,
            summary=f"Dictée de {len(entries)} mots : {words}",
        ),
        knowledge=items,
        skills=[
            Skill(
                id="s1",
                label=SKILL_LABEL,
                verb=SkillVerb.RECALL,
                importance=4,
                knowledge_ids=[i.id for i in items],
                source_excerpt=name,
            )
        ],
    )
    materials = {
        item.id: validate_material(
            item,
            {
                "explanation": item.statement,
                "spelling": {"word": entry.word, "sentence": _blank(entry)},
            },
            text,
            Subject.FRENCH,
        )
        for item, entry in zip(items, entries, strict=True)
    }
    return DictationLesson(text, analysis, materials)
