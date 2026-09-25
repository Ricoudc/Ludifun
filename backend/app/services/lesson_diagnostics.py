"""« Voir ce qui se passe » sur l'écran d'analyse : l'IA utilisée, chaque étape et sa durée, et
en cas d'échec la raison, en clair puis telle que l'IA l'a donnée.

Pendant l'analyse, les étapes viennent de la mémoire du serveur (`LIVE`) ; ensuite, du journal
`ai_runs` (dernière tentative). Pas de texte de leçon : les messages sont nettoyés.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AiRun, Lesson
from app.services.lesson_pipeline import STAGE_LABELS
from app.services.lesson_processing import IN_PROGRESS
from app.services.live_calls import LiveCalls
from app.services.monitoring import clean_message


@dataclass(frozen=True)
class Step:
    stage: str
    model: str
    seconds: int
    status: str  # ok, running, error, invalid_output, refused
    message: str | None = None


@dataclass(frozen=True)
class Diagnostics:
    steps: list[Step]
    explanation: str | None  # la raison de l'échec, en clair (pour le parent)


# Motifs des messages d'erreur des IA → explication simple, dans cet ordre.
EXPLANATIONS = (
    ("n'a pas répondu", "L'IA a mis trop de temps à répondre. Avec Ollama : modèle trop lourd pour ce "
     "PC, ou carte graphique non utilisée (voir « ollama ps »). Essayez un modèle plus léger "
     "ou une IA en ligne."),
    ("s'est arrêté", "Ollama s'est arrêté pendant la lecture, même avec une photo réduite : le modèle "
     "ne tient sans doute pas dans la mémoire de la carte graphique (« ollama ps » : une part en CPU). "
     "Essayez LUDIFUN_OLLAMA_NUM_CTX=8192 dans .env, ou un modèle plus léger (qwen2.5vl:3b)."),
    ("injoignable", "Le serveur n'arrive pas à joindre Ollama : est-il lancé ? Sur un autre ordinateur, "
     "il faut OLLAMA_HOST=0.0.0.0 et le port 11434 ouvert."),
    ("connexion impossible", "Le serveur n'arrive pas à joindre l'IA en ligne : connexion Internet du PC ?"),
    ("absent", "Le modèle choisi n'est pas installé dans Ollama (« ollama pull … » sur le PC)."),
    ("model_not_found", "Ce modèle n'existe plus chez ce fournisseur (retiré) : choisissez-en un autre "
     "(Changer-IA-Ludifun.bat, ou « Intelligence artificielle » dans l'espace parent)."),
    ("401", "La clé d'API a été refusée : vérifiez-la dans l'espace parent."),
    ("403", "La clé d'API a été refusée ou n'a pas accès à ce modèle."),
    ("429", "L'IA en ligne limite le nombre de demandes (quota ou offre gratuite épuisée) : "
     "réessayez plus tard."),
    ("402", "Le compte de l'IA en ligne n'a plus de crédit."),
    ("tronquée", "La réponse de l'IA a été coupée (contexte trop court)."),
    ("hors schéma", "L'IA a répondu, mais pas dans le format attendu : le modèle suit mal les consignes "
     "(fréquent avec les petits modèles). Réessayez, ou choisissez un modèle plus grand."),
    ("réponse vide", "L'IA a renvoyé une réponse vide."),
    ("erreur interne", "Erreur dans le serveur Ludifun lui-même : envoyez le rapport (Rapport-Ludifun.bat)."),
)  # fmt: skip
STAGE_ORDER = ("ocr", "analysis", "material", "evaluation")
FAILURE_EXPLANATIONS = {
    "unreadable": "L'IA n'a pas réussi à lire le texte de la photo (floue, sombre, écriture trop petite ?).",
    "not_a_lesson": "L'IA a lu la photo mais n'y a pas trouvé de leçon à apprendre.",
    "too_long": "Le texte lu est trop long pour une seule leçon.",
}


def explain(message: str) -> str:
    return next((text for motif, text in EXPLANATIONS if motif in message), "Erreur de l'IA.")


LABELS: dict[str, str] = {str(stage): label for stage, label in STAGE_LABELS.items()}


def _label(stage: str) -> str:
    return LABELS.get(stage, stage)


async def diagnostics(db: AsyncSession, lesson: Lesson, live: LiveCalls, now: datetime) -> Diagnostics:
    if lesson.status in IN_PROGRESS:
        steps = [
            Step(
                _label(c.stage), c.model, c.seconds, c.status, clean_message(c.message) if c.message else None
            )
            for c in live.done(lesson.id)
        ]
        steps += [
            Step(_label(c.stage), c.model, max(0, round((now - c.started_at).total_seconds())), "running")
            for c in live.current(lesson.id)
        ]
        return Diagnostics(steps, None)

    runs = await _last_attempt(db, lesson.id)
    steps = [
        Step(
            _label(r.stage),
            r.model,
            round(r.latency_ms / 1000),
            r.status,
            _message(r),
        )
        for r in runs
    ]
    explanation = None
    if lesson.status == "failed":
        failed = next((s for s in reversed(steps) if s.status != "ok"), None)
        if lesson.failure_reason in FAILURE_EXPLANATIONS:
            explanation = FAILURE_EXPLANATIONS[lesson.failure_reason]
        elif failed is not None:
            explanation = explain(failed.message or "")
        else:
            explanation = (
                "L'analyse s'est arrêtée sans message de l'IA (serveur redémarré pendant l'analyse ?)."
            )
    return Diagnostics(steps, explanation)


def _message(run: AiRun) -> str | None:
    """Erreur de l'appel, ou repli sur une autre IA (appel réussi par une IA de secours)."""
    if not run.warnings:
        return None
    first = str(run.warnings[0])
    if run.status != "ok" or first.startswith("repli"):
        return clean_message(first)
    return None


async def _last_attempt(db: AsyncSession, lesson_id: uuid.UUID) -> list[AiRun]:
    """Les appels de la dernière tentative : enregistrés ensemble, à la même heure."""
    last = await db.scalar(select(func.max(AiRun.created_at)).where(AiRun.lesson_id == lesson_id))
    if last is None:
        return []
    runs = await db.scalars(select(AiRun).where(AiRun.lesson_id == lesson_id, AiRun.created_at == last))
    return sorted(
        runs, key=lambda r: STAGE_ORDER.index(r.stage) if r.stage in STAGE_ORDER else len(STAGE_ORDER)
    )
