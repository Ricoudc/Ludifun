"""Évaluation du pipeline sur un corpus de vraies leçons (cahier des charges §17.2).

    uv run python -m app.tools.evaluate ../eval/lessons
    uv run python -m app.tools.evaluate ../eval/example --provider fake
    uv run python -m app.tools.evaluate ../eval/lessons --prompt analysis=v7   # ancienne version

Pour comparer deux évaluations (deux prompts, deux modèles) : `app.tools.compare` (§5.81).

Chaque leçon est un dossier contenant ses photos (page1.jpg, page2.jpg…), un PDF, un Word
(.docx) ou un LibreOffice (.odt), ou un `lesson.txt`, et si possible un `expected.json` annoté
par un adulte (voir eval/README.md) ; sans lui, la leçon est analysée sans mesure de justesse.
Le résultat est écrit dans un dossier horodaté : un rapport `report.md`, et pour
chaque leçon le résultat complet (`<leçon>.json`) et la séance à relire (`<leçon>.txt`).
"""

import argparse
import asyncio
import hashlib
import io
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.ai.factory import build_providers
from app.ai.ports import PROMPT_VERSIONS, PROMPTS_DIR, PageImage, Stage
from app.ai.presets import PRESETS
from app.ai.pricing import run_cost
from app.config import get_settings
from app.domain.activities.registry import default_registry
from app.domain.knowledge import Grade, KnowledgeItem, Subject
from app.domain.text import contains_words, normalize
from app.services.documents import DocumentError, read_document
from app.services.lesson_pipeline import LessonPipeline, PipelineResult
from app.tools.analyze import media_type, report, to_json

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
DOCUMENT_SUFFIXES = {".pdf", ".docx", ".odt"}
GRADES = [g.value for g in Grade]

# Prix publics en dollars par million de jetons (entrée, sortie). Les jetons de
# réflexion sont comptés en sortie ; les lectures de cache, moins chères, sont
# comptées au plein tarif : l'estimation est donc prudente.


class ExpectedNotion(BaseModel):
    label: str
    aliases: list[str] = Field(default_factory=list)


class Expected(BaseModel):
    """Annotation d'une leçon par un adulte (`expected.json`). Facultative : sans elle, la leçon
    est seulement analysée (ce que l'application en fait), sans mesure de justesse."""

    subject: Subject | None = None
    grade: Grade | None = None
    support: str = "inconnu"  # manuscrit, manuel, photocopie…
    essential: list[ExpectedNotion] = Field(default_factory=list)  # notions indispensables
    is_lesson: bool = True  # false pour un cas piège (photo qui n'est pas une leçon)
    # Noms écrits sur les pages (élève, école, enseignant) qui ne doivent pas se retrouver dans le
    # texte lu (AIPD, §4). Ils restent dans expected.json, hors du dépôt, et jamais dans le rapport.
    personal: list[str] = Field(default_factory=list)
    notes: str = ""


@dataclass
class LessonScore:
    name: str
    pages: int
    support: str
    expected: Expected
    failure: str | None
    duration_s: float
    subject_ok: bool | None = None
    grade_ok: bool | None = None
    found: dict[str, str | None] = field(default_factory=dict)  # notion attendue → notion produite
    invented: int = 0  # notions rejetées car introuvables dans le texte
    material_kept: int = 0
    material_rejected: int = 0
    cost_usd: float | None = 0.0
    tokens: tuple[int, int] = (0, 0)
    from_text: bool = False  # lesson.txt : pas de lecture de photo
    review: int = 0  # passages douteux soumis à l'enfant (« Peux-tu vérifier ? »)
    notions: int = 0  # notions retenues, avec leur matériel
    in_skill: int = 0  # notions reliées à au moins une compétence
    skills: int = 0
    with_help: int = 0  # notions avec au moins un indice et un rappel
    open_questions: int = 0
    important_notions: int = 0
    important_with_open_question: int = 0
    personal_leaks: int = 0  # noms personnels retrouvés dans le texte lu

    @property
    def recall(self) -> float | None:
        return sum(v is not None for v in self.found.values()) / len(self.found) if self.found else None

    @property
    def correct_outcome(self) -> bool:
        """Une leçon doit aboutir ; un cas piège doit être refusé."""
        if self.expected.is_lesson:
            return self.failure is None
        return self.failure in ("not_a_lesson", "unreadable")


def _notion_matches(expected: ExpectedNotion, item: KnowledgeItem) -> bool:
    text = f"{item.label} {item.statement}"
    return any(
        contains_words(text, name)
        or SequenceMatcher(None, normalize(item.label), normalize(name)).ratio() >= 0.85
        for name in [expected.label, *expected.aliases]
    )


def match_notions(expected: list[ExpectedNotion], knowledge: list[KnowledgeItem]) -> list[str | None]:
    """Associe les notions attendues aux notions produites sans compter deux fois la même.

    Un appariement biparti (avec réaffectation) évite qu'une seule notion produite valide
    plusieurs notions attendues simplement parce que son énoncé contient plusieurs libellés.
    Le résultat conserve l'ordre des annotations.
    """
    candidates = [
        [index for index, item in enumerate(knowledge) if _notion_matches(notion, item)]
        for notion in expected
    ]
    assigned: dict[int, int] = {}

    def assign(expected_index: int, visited: set[int]) -> bool:
        for item_index in candidates[expected_index]:
            if item_index in visited:
                continue
            visited.add(item_index)
            previous = assigned.get(item_index)
            if previous is None or assign(previous, visited):
                assigned[item_index] = expected_index
                return True
        return False

    for expected_index in range(len(expected)):
        assign(expected_index, set())

    result: list[str | None] = [None] * len(expected)
    for item_index, expected_index in assigned.items():
        result[expected_index] = knowledge[item_index].id
    return result


def match_notion(expected: ExpectedNotion, knowledge: list[KnowledgeItem]) -> str | None:
    """Compatibilité unitaire ; les scores de corpus utilisent match_notions."""
    return match_notions([expected], knowledge)[0]


QUESTION_REVIEW_LABELS = {"pertinent", "à corriger", "hors sujet"}


def _question_review_signature(review: dict[str, Any]) -> str:
    """Empreinte des contenus pédagogiques qui rendent une annotation valable."""
    snapshot = {
        key: review.get(key)
        for key in (
            "knowledge_id",
            "notion",
            "notion_statement",
            "importance",
            "review_dimensions",
            "level",
            "prompt",
            "key_points",
            "model_answer",
            "passage",
        )
    }
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def open_question_review(result: PipelineResult, lesson_name: str) -> list[dict[str, Any]]:
    """Exporte les questions ouvertes dans un format de revue humaine, sans score sémantique fictif."""
    reviews = [
        {
            "review_id": f"{lesson_name}:{unit.id}:{index + 1}",
            "lesson": lesson_name,
            "knowledge_id": unit.id,
            "notion": unit.item.label,
            "notion_statement": unit.item.statement,
            "importance": unit.item.importance,
            "level": question.level,
            "prompt": question.prompt,
            "key_points": question.key_points,
            "model_answer": question.model_answer,
            "passage": question.passage,
            "review_status": "à annoter",
            "review_dimensions": [
                "pertinence_par_rapport_a_la_notion",
                "niveau_cognitif_annonce",
                "absence_de_reponse_dans_la_question",
                "points_cles_et_reponse_modele",
                "adaptation_a_l_age",
            ],
        }
        for unit in result.units
        for index, question in enumerate(unit.material.open_questions)
    ]
    return [review | {"review_signature": _question_review_signature(review)} for review in reviews]


def apply_question_review_annotations(
    reviews: list[dict[str, Any]], annotations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Réapplique les labels uniquement si l'identifiant et le contenu pédagogique correspondent."""
    by_id: dict[str, dict[str, Any]] = {}
    for annotation in annotations:
        if not isinstance(annotation, dict):
            raise ValueError("chaque annotation doit être un objet JSON")
        review_id = annotation.get("review_id")
        if not isinstance(review_id, str) or not review_id:
            raise ValueError("une annotation doit avoir un review_id")
        if review_id in by_id:
            raise ValueError(f"annotation en double : {review_id}")
        if annotation.get("review_status") not in QUESTION_REVIEW_LABELS:
            raise ValueError(f"label de revue invalide pour {review_id}")
        by_id[review_id] = annotation

    result = []
    seen: set[str] = set()
    for review in reviews:
        review_id = review["review_id"]
        if review_id in seen:
            raise ValueError(f"question générée en double : {review_id}")
        seen.add(review_id)
        matched_annotation = by_id.pop(review_id) if review_id in by_id else None
        if matched_annotation is not None:
            if matched_annotation.get("review_signature") != _question_review_signature(review):
                raise ValueError(f"contenu pédagogique modifié depuis l'annotation : {review_id}")
            review = review | {"review_status": matched_annotation["review_status"]}
        result.append(review)
    if by_id:
        raise ValueError(f"annotations sans question correspondante : {', '.join(sorted(by_id))}")
    return result


def question_review_summary(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Compte les annotations humaines ; les questions non annotées ne sont pas au dénominateur."""
    counts = {label: 0 for label in sorted(QUESTION_REVIEW_LABELS)}
    pending = 0
    for review in reviews:
        # Une question sans niveau cognitif ne peut pas être évaluée dans les statistiques
        # de pertinence par niveau ; elle reste toutefois comprise dans le total exporté.
        if review.get("level") is None:
            continue
        label = review.get("review_status", "à annoter")
        if label == "à annoter":
            pending += 1
        elif label in counts:
            counts[label] += 1
        else:
            raise ValueError(f"label de revue inconnu : {label}")
    annotated = sum(counts.values())
    by_level: dict[str, dict[str, int]] = {}
    for review in reviews:
        level = review.get("level")
        if level is None:
            continue
        key = str(level)
        bucket = by_level.setdefault(
            key, {"total": 0, "annotated": 0, "pending": 0, **{label: 0 for label in counts}}
        )
        bucket["total"] += 1
        label = review.get("review_status", "à annoter")
        if label == "à annoter":
            bucket["pending"] += 1
        elif label in counts:
            bucket["annotated"] += 1
            bucket[label] += 1

    level_summary = {}
    for level, bucket in sorted(by_level.items(), key=lambda item: int(item[0])):
        level_summary[level] = bucket | {
            "pertinent_rate": (bucket["pertinent"] / bucket["annotated"] if bucket["annotated"] else None),
            "off_topic_rate": (bucket["hors sujet"] / bucket["annotated"] if bucket["annotated"] else None),
        }

    return {
        "total": len(reviews),
        "annotated": annotated,
        "pending": pending,
        "counts": counts,
        "pertinent_rate": counts["pertinent"] / annotated if annotated else None,
        "off_topic_rate": counts["hors sujet"] / annotated if annotated else None,
        "by_level": level_summary,
    }


def material_counts(result: PipelineResult) -> tuple[int, int]:
    kept = 0
    for unit in result.units:
        m = unit.material
        kept += len(m.questions) + len(m.true_statements) + len(m.false_statements)
        kept += len(m.open_questions)
        kept += sum(
            x is not None
            for x in (m.cloze, m.pair, m.flashcard, m.tip, m.help, m.sorting, m.sequence, m.spelling)
        )
    rejected = sum(1 for r in result.rejected if "." in r.element and not r.element.startswith("analysis."))
    return kept, rejected


def score(
    name: str,
    expected: Expected,
    result: PipelineResult,
    pages: int,
    duration_s: float,
    from_text: bool = False,
) -> LessonScore:
    s = LessonScore(name, pages, expected.support, expected, result.failure_reason, duration_s)
    s.from_text = from_text
    costs = [run_cost(r.model, r.input_tokens, r.output_tokens) for r in result.runs]
    s.cost_usd = None if None in costs else sum(c or 0.0 for c in costs)
    s.tokens = (sum(r.input_tokens or 0 for r in result.runs), sum(r.output_tokens or 0 for r in result.runs))
    s.invented = sum(
        1 for r in result.rejected if r.element.startswith("analysis.") and "introuvable" in r.reason
    )
    s.material_kept, s.material_rejected = material_counts(result)
    analysis = result.analysis
    if expected.is_lesson and analysis is not None and analysis.lesson is not None:
        lesson = analysis.lesson
        if expected.subject is not None:
            s.subject_ok = lesson.subject == expected.subject
        if expected.grade is not None:
            s.grade_ok = abs(GRADES.index(lesson.grade) - GRADES.index(expected.grade)) <= 1
    if expected.is_lesson:
        knowledge = analysis.knowledge if analysis else []
        matches = match_notions(expected.essential, knowledge)
        s.found = {notion.label: item_id for notion, item_id in zip(expected.essential, matches, strict=True)}
    s.review = len(result.review)
    s.notions = len(result.units)
    if analysis is not None:
        s.skills = len(analysis.skills)
        linked = {k for skill in analysis.skills for k in skill.knowledge_ids}
        s.in_skill = sum(1 for u in result.units if u.id in linked)
    for unit in result.units:
        ladder = unit.material.help
        s.with_help += ladder is not None and ladder.hint is not None and ladder.reminder is not None
        open_count = len(unit.material.open_questions)
        s.open_questions += open_count
        if unit.item.importance >= 4:
            s.important_notions += 1
            s.important_with_open_question += open_count > 0
    if result.ocr is not None:
        read = result.ocr.text
        s.personal_leaks = sum(1 for name in expected.personal if contains_words(read, name))
    return s


# --------------------------------------------------------------------------- #
# Rapport
# --------------------------------------------------------------------------- #


def _pct(values: list[bool]) -> float | None:
    return 100 * sum(values) / len(values) if values else None


def _fmt(value: float | None, suffix: str = " %") -> str:
    return "—" if value is None else f"{value:.0f}{suffix}"


@dataclass
class Metric:
    name: str
    value: float | None
    display: str
    target: str
    ok: bool | None


def metrics(scores: list[LessonScore]) -> list[Metric]:
    lessons = [s for s in scores if s.expected.is_lesson]
    success = _pct([s.correct_outcome for s in scores])
    subject = _pct([bool(s.subject_ok) for s in scores if s.subject_ok is not None])
    grade = _pct([bool(s.grade_ok) for s in scores if s.grade_ok is not None])
    found = [v is not None for s in lessons for v in s.found.values()]
    recall = _pct(found)
    invented = sum(s.invented for s in scores)
    kept = sum(s.material_kept for s in scores)
    rejected = sum(s.material_rejected for s in scores)
    rejection = 100 * rejected / (kept + rejected) if kept + rejected else None
    two_pages = [s.duration_s for s in scores if s.pages == 2 and s.failure is None]
    any_pages = [s.duration_s for s in scores if s.failure is None]
    durations = two_pages or any_pages
    median = statistics.median(durations) if durations else None
    costs = [s.cost_usd for s in scores if s.cost_usd is not None and s.failure is None]
    mean_cost = statistics.mean(costs) if costs else None
    photos = [s for s in scores if s.expected.is_lesson and not s.from_text]
    to_check = _pct([s.review > 0 for s in photos])
    notions = sum(s.notions for s in scores)
    in_skill = 100 * sum(s.in_skill for s in scores) / notions if notions else None
    helped = 100 * sum(s.with_help for s in scores) / notions if notions else None
    ready = [s for s in scores if s.notions]
    open_per_lesson = statistics.mean(s.open_questions for s in ready) if ready else None
    important_notions = sum(s.important_notions for s in scores)
    important_with_open = sum(s.important_with_open_question for s in scores)
    important_open_coverage = 100 * important_with_open / important_notions if important_notions else None
    annotated = [s for s in scores if s.expected.personal]
    leaks = sum(s.personal_leaks for s in annotated)

    def at_least(value: float | None, target: float) -> bool | None:
        return None if value is None else value >= target

    return [
        Metric("Leçons traitées correctement", success, _fmt(success), "≥ 90 %", at_least(success, 90)),
        Metric("Matière correcte", subject, _fmt(subject), "≥ 95 %", at_least(subject, 95)),
        Metric("Niveau à ± 1 classe", grade, _fmt(grade), "≥ 80 %", at_least(grade, 80)),
        Metric("Rappel des notions indispensables", recall, _fmt(recall), "≥ 85 %", at_least(recall, 85)),
        Metric("Notions inventées (rejetées)", invented, str(invented), "0", invented == 0),
        Metric(
            "Matériel rejeté par les validateurs",
            rejection,
            _fmt(rejection),
            "≤ 15 %",
            None if rejection is None else rejection <= 15,
        ),
        Metric(
            "Durée photo → prête (médiane" + (", 2 pages)" if two_pages else ")"),
            median,
            _fmt(median, " s"),
            "≤ 45 s",
            None if median is None else median <= 45,
        ),
        Metric(
            "Coût IA moyen par leçon",
            mean_cost,
            "—" if mean_cost is None else f"{mean_cost:.3f} $",
            "à fixer",
            None,
        ),
        # Étapes 13 à 15 et AIPD (spécification technique §9)
        Metric("Photos à faire vérifier (passages douteux)", to_check, _fmt(to_check), "à suivre", None),
        Metric(
            "Notions reliées à une compétence", in_skill, _fmt(in_skill), "≥ 90 %", at_least(in_skill, 90)
        ),
        Metric("Notions avec indice et rappel", helped, _fmt(helped), "≥ 90 %", at_least(helped, 90)),
        Metric(
            "Questions ouvertes par leçon (moyenne)",
            open_per_lesson,
            "—" if open_per_lesson is None else f"{open_per_lesson:.1f}",
            "≥ 1",
            None if open_per_lesson is None else open_per_lesson >= 1,
        ),
        Metric(
            "Notions importantes avec question ouverte",
            important_open_coverage,
            _fmt(important_open_coverage),
            "à suivre (selon pertinence pédagogique)",
            None,
        ),
        Metric(
            "Noms personnels dans le texte lu",
            leaks if annotated else None,
            f"{leaks} ({len(annotated)} leçon(s) annotée(s))" if annotated else "— (aucune annotation)",
            "0",
            leaks == 0 if annotated else None,
        ),
    ]


def render_report(scores: list[LessonScore], provider: str, started: datetime) -> str:
    icon = {True: "✅", False: "❌", None: "·"}
    lines = [
        f"# Évaluation du pipeline — {started:%Y-%m-%d %H:%M} UTC",
        "",
        f"Fournisseur : `{provider}` · {len(scores)} leçon(s)",
        "",
        "## Mesures (§17.2)",
        "",
        "| Mesure | Valeur | Seuil V1 | |",
        "|---|---|---|---|",
    ]
    lines += [f"| {m.name} | {m.display} | {m.target} | {icon[m.ok]} |" for m in metrics(scores)]

    def recall_breakdown(attribute: str) -> list[tuple[str, int, int, float]]:
        groups: dict[str, list[bool]] = {}
        for score in scores:
            if not score.expected.is_lesson:
                continue
            value = getattr(score.expected, attribute)
            if value is None:
                continue
            label = value.value
            groups.setdefault(label, []).extend(found is not None for found in score.found.values())
        return [
            (label, sum(values), len(values), 100 * sum(values) / len(values))
            for label, values in sorted(groups.items())
            if values
        ]

    by_subject = recall_breakdown("subject")
    by_grade = recall_breakdown("grade")
    if by_subject or by_grade:
        lines += ["", "## Rappel des notions par matière et niveau", ""]
        if by_subject:
            lines += [
                "### Par matière",
                "",
                "| Matière | Notions retrouvées | Total | Rappel |",
                "|---|---:|---:|---:|",
            ]
            lines += [
                f"| {label} | {found} | {total} | {recall:.0f} % |"
                for label, found, total, recall in by_subject
            ]
            lines.append("")
        if by_grade:
            lines += [
                "### Par niveau",
                "",
                "| Niveau | Notions retrouvées | Total | Rappel |",
                "|---|---:|---:|---:|",
            ]
            lines += [
                f"| {label} | {found} | {total} | {recall:.0f} % |"
                for label, found, total, recall in by_grade
            ]
            lines.append("")

    lines += [
        "",
        "## Par leçon",
        "",
        "| Leçon | Support | Pages | Issue | Matière | Niveau | Rappel | Inventées "
        "| Rejets matériel | À vérifier | Compétences | Aides | Ouvertes "
        "| Ouvertes / notions importantes | Durée | Coût |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in scores:
        outcome = "prête" if s.failure is None else s.failure
        if not s.expected.is_lesson:
            outcome += " (piège)"
        total = s.material_kept + s.material_rejected
        rejects = f"{s.material_rejected}/{total}" if total else "—"
        cost = "—" if s.cost_usd is None else f"{s.cost_usd:.3f} $"
        recall = _fmt(None if s.recall is None else 100 * s.recall)
        lines.append(
            f"| {s.name} | {s.support} | {s.pages} | {icon[s.correct_outcome]} {outcome} "
            f"| {icon[s.subject_ok]} | {icon[s.grade_ok]} | {recall} "
            f"| {s.invented} | {rejects} | {s.review or '—'} | {s.skills} ({s.in_skill}/{s.notions}) "
            f"| {s.with_help}/{s.notions} | {s.open_questions} "
            f"| {s.important_with_open_question}/{s.important_notions} | {s.duration_s:.1f} s | {cost} |"
        )
    missed = [(s.name, label) for s in scores for label, found in s.found.items() if found is None]
    if missed:
        lines += ["", "## Notions indispensables manquées", ""]
        lines += [f"- **{name}** : {label}" for name, label in missed]
    leaked = [s for s in scores if s.personal_leaks]
    if leaked:
        lines += ["", "## ⚠ Noms personnels retrouvés dans le texte lu", ""]
        lines += [
            f"- **{s.name}** : {s.personal_leaks} nom(s) sur {len(s.expected.personal)} "
            "(voir `<leçon>.json` ; renforcer la consigne du prompt de lecture)"
            for s in leaked
        ]
    lines += [
        "",
        "## À faire ensuite",
        "",
        "- Relire les séances (`<leçon>.txt`) avec la grille `eval/grille-evaluation.md`.",
        "- Pour chaque ❌, ouvrir `<leçon>.json` : texte lu, notions, éléments rejetés et raisons.",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Exécution
# --------------------------------------------------------------------------- #


@dataclass
class LessonInput:
    name: str
    expected: Expected
    pages: list[PageImage]
    text: str | None


def load_corpus(root: Path, only: set[str] | None = None) -> list[LessonInput]:
    lessons = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if only and folder.name not in only:
            continue
        expected_file = folder / "expected.json"
        if expected_file.exists():
            expected = Expected.model_validate_json(expected_file.read_text(encoding="utf-8"))
        else:
            print(
                f"ℹ {folder.name} : pas de expected.json, analysée sans mesure de justesse", file=sys.stderr
            )
            expected = Expected()
        text_file = folder / "lesson.txt"
        text = text_file.read_text(encoding="utf-8") if text_file.exists() else None
        images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
        pages = [PageImage(p.read_bytes(), media_type(p.read_bytes(), p)) for p in images]
        documents = sorted(p for p in folder.iterdir() if p.suffix.lower() in DOCUMENT_SUFFIXES)
        if text is None and not pages and documents:
            # Leçon en PDF, Word ou LibreOffice : lue comme dans l'application (§5.49).
            try:
                read = read_document(documents[0].read_bytes(), max_pages=6, max_image_bytes=8 * 2**20)
            except DocumentError as exc:
                print(f"⚠ {folder.name} ignorée : {exc.message}", file=sys.stderr)
                continue
            text, pages = (read.text or None), read.images
        if text is None and not pages:
            print(f"⚠ {folder.name} ignorée : ni photo, ni PDF ou Word, ni lesson.txt", file=sys.stderr)
            continue
        lessons.append(LessonInput(folder.name, expected, pages, text))
    return lessons


async def resume_after_review(pipeline: LessonPipeline, paused: PipelineResult) -> PipelineResult:
    """« Peux-tu vérifier ? » : l'évaluation joue l'enfant qui confirme tout ce qui a été lu, puis
    l'analyse reprend sur ce texte, comme dans l'application. Les passages restent comptés."""
    assert paused.ocr is not None
    resumed = await pipeline.run(text=paused.ocr.text)
    resumed.ocr = paused.ocr
    resumed.review = paused.review
    resumed.runs = paused.runs + resumed.runs
    resumed.prompt_versions = paused.prompt_versions
    return resumed


async def evaluate(
    lessons: list[LessonInput], provider: str | None, concurrency: int
) -> tuple[list[tuple[LessonInput, PipelineResult, float]], dict[str, str]]:
    settings = get_settings()
    if provider:
        settings = settings.model_copy(update={"ai_provider": provider})
    ocr, llm = build_providers(settings)
    pipeline = LessonPipeline(ocr, llm, default_registry(), max_chars=settings.max_lesson_chars)
    semaphore = asyncio.Semaphore(concurrency)

    async def one(lesson: LessonInput) -> tuple[LessonInput, PipelineResult, float]:
        async with semaphore:
            started = time.perf_counter()
            result = await pipeline.run(lesson.pages, lesson.text)
            if result.review and result.failure_reason is None and result.ocr is not None:
                result = await resume_after_review(pipeline, result)
            duration = time.perf_counter() - started
            print(
                f"  {lesson.name} : {result.failure_reason or 'prête'} en {duration:.1f} s", file=sys.stderr
            )
            return lesson, result, duration

    results = list(await asyncio.gather(*(one(lesson) for lesson in lessons)))
    models = {stage: llm.model_for(stage) for stage in ("analysis", "material", "evaluation")}
    return results, models


def configuration(provider: str, models: dict[str, str]) -> dict[str, Any]:
    """Ce qui a produit ces résultats : fournisseur, modèle et version du prompt de chaque étape."""
    return {"provider": provider, "models": models, "prompts": dict(sorted(PROMPT_VERSIONS.items()))}


def metrics_json(scores: list[LessonScore], config: dict[str, Any], started: datetime) -> dict[str, Any]:
    """Les mesures, lisibles par `app.tools.compare` (§5.81)."""
    return {
        "started": started.isoformat(timespec="seconds"),
        "configuration": config,
        "metrics": [
            {"name": m.name, "value": m.value, "display": m.display, "target": m.target, "ok": m.ok}
            for m in metrics(scores)
        ],
        "lessons": {
            s.name: {
                "ready": s.failure is None,
                "recall": s.recall,
                "invented": s.invented,
                "rejected": s.material_rejected,
                "kept": s.material_kept,
                "duration_s": round(s.duration_s, 1),
                "cost_usd": s.cost_usd,
            }
            for s in scores
        },
    }


def _prompt_choice(text: str) -> tuple[Stage, str]:
    """« analysis=v7 » → (étape, version) ; le fichier du prompt doit exister."""
    stage, _, version = text.partition("=")
    if stage not in PROMPT_VERSIONS or not (PROMPTS_DIR / f"{stage}.{version}.md").exists():
        raise argparse.ArgumentTypeError(f"prompt inconnu : {text} (ex. analysis=v7)")
    return stage, version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.tools.evaluate", description=__doc__.split("\n")[0])
    parser.add_argument("corpus", type=Path, help="dossier contenant un sous-dossier par leçon")
    parser.add_argument("--out", type=Path, help="dossier des résultats (défaut : <corpus>/../results)")
    parser.add_argument(
        "--provider", choices=[*sorted(PRESETS), "fake"], help="fournisseur d'IA (défaut : configuration)"
    )
    parser.add_argument("--only", help="noms de leçons séparés par des virgules")
    parser.add_argument(
        "--question-reviews",
        type=Path,
        help="annotations humaines précédentes à réappliquer (open_questions_review.json)",
    )
    parser.add_argument("--concurrency", type=int, default=3, help="leçons traitées en parallèle")
    parser.add_argument(
        "--prompt",
        action="append",
        type=_prompt_choice,
        default=[],
        help="version de prompt à évaluer à la place de l'actuelle, ex. analysis=v7 (répétable)",
    )
    args = parser.parse_args(argv)
    current = dict(PROMPT_VERSIONS)
    try:
        for stage, version in args.prompt:  # le temps de cette évaluation seulement
            PROMPT_VERSIONS[stage] = version
        return _run(parser, args)
    finally:
        PROMPT_VERSIONS.clear()
        PROMPT_VERSIONS.update(current)


def _run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:

    lessons = load_corpus(args.corpus, set(args.only.split(",")) if args.only else None)
    if not lessons:
        parser.error(f"aucune leçon exploitable dans {args.corpus}")

    started = datetime.now(UTC)
    provider = args.provider or get_settings().ai_provider
    print(f"Évaluation de {len(lessons)} leçon(s) avec « {provider} »…", file=sys.stderr)
    runs, models = asyncio.run(evaluate(lessons, args.provider, args.concurrency))

    out = (args.out or args.corpus.resolve().parent / "results") / f"{started:%Y%m%d-%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    scores = []
    question_reviews: list[dict[str, Any]] = []
    for lesson, result, duration in runs:
        question_reviews.extend(open_question_review(result, lesson.name))
        s = score(
            lesson.name, lesson.expected, result, len(lesson.pages) or 1, duration, lesson.text is not None
        )
        scores.append(s)
        details: dict[str, Any] = to_json(result) | {
            "duration_s": round(duration, 2),
            "cost_usd": s.cost_usd,
            "essential_found": s.found,
            "personal_leaks": s.personal_leaks,  # nombre seulement, jamais les noms
        }
        (out / f"{lesson.name}.json").write_text(
            json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        session = io.StringIO()
        report(result, seed=1, out=session)
        (out / f"{lesson.name}.txt").write_text(session.getvalue(), encoding="utf-8")

    if args.question_reviews:
        annotations = json.loads(args.question_reviews.read_text(encoding="utf-8"))
        if not isinstance(annotations, list):
            parser.error("--question-reviews doit contenir une liste JSON")
        try:
            question_reviews = apply_question_review_annotations(question_reviews, annotations)
        except ValueError as exc:
            parser.error(str(exc))
    review_summary = question_review_summary(question_reviews)
    (out / "open_questions_review.json").write_text(
        json.dumps(question_reviews, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    text = render_report(scores, provider, started)
    text += (
        "\n\n## Revue humaine des questions ouvertes\n\n"
        f"- Questions : {review_summary['total']} ; annotées : {review_summary['annotated']} ; "
        f"en attente : {review_summary['pending']}\n"
        f"- Pertinentes : {review_summary['counts']['pertinent']} ; "
        f"à corriger : {review_summary['counts']['à corriger']} ; "
        f"hors sujet : {review_summary['counts']['hors sujet']}\n"
    )
    if review_summary["by_level"]:
        text += (
            "\\n### Résultats par niveau cognitif\\n\\n"
            "| Niveau | Annotées | En attente | Pertinentes | À corriger | Hors sujet | Taux pertinent |\\n"
            "|---:|---:|---:|---:|---:|---:|---:|\\n"
        )
        level_names = {"3": "3 — appliquer", "4": "4 — expliquer", "5": "5 — transférer"}
        for level, bucket in review_summary["by_level"].items():
            pertinent_rate = bucket["pertinent_rate"]
            pertinent_percent = _fmt(100 * pertinent_rate if pertinent_rate is not None else None)
            text += (
                f"| {level_names.get(level, level)} | {bucket['annotated']} | "
                f"{bucket['pending']} | {bucket['pertinent']} | "
                f"{bucket['à corriger']} | {bucket['hors sujet']} | "
                f"{pertinent_percent} |\n"
            )
    (out / "report.md").write_text(text, encoding="utf-8")
    metrics_data = metrics_json(scores, configuration(provider, models), started)
    metrics_data["open_question_review"] = review_summary
    (out / "metrics.json").write_text(
        json.dumps(metrics_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(text)
    print(f"Résultats détaillés : {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
