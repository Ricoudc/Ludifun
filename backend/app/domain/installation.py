"""État de l'installation, dit au parent (§5.89) : ce qui marche, ce qui bloque, quoi faire.

Domaine pur : les faits sont relevés ailleurs (`app.services.installation`), ici on en tire des
lignes lisibles par un parent. Aucune donnée d'enfant : ni prénom, ni texte de leçon.
"""

from dataclasses import dataclass
from enum import StrEnum

# En dessous de cette part du modèle sur la carte graphique, une étape d'une minute en prend dix.
GPU_SHARE_OK = 0.99
# Marge gardée pour le contexte et l'image : un modèle de 6 Go ne tient pas dans 6 Go de carte.
FIT_MARGIN = 0.85
RECENT_LESSONS = 5  # leçons récentes regardées pour « les dernières analyses »


class Level(StrEnum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Check:
    code: str
    level: Level
    title: str
    message: str
    action: str | None = None  # ce que le parent peut faire, s'il y a quelque chose à faire


@dataclass(frozen=True)
class OllamaModel:
    name: str
    size: int  # octets
    size_vram: int | None = None  # part sur la carte graphique, si le modèle est chargé


def _gb(size: int) -> str:
    return f"{size / 1e9:.1f} Go".replace(".", ",")


def gpu_check(model: str, loaded: list[OllamaModel], installed: list[OllamaModel]) -> Check:
    """Le modèle tient-il dans la carte graphique ? Sinon, lesquels des modèles installés y
    tiendraient (plus petits que ce que la carte a pu prendre, avec une marge)."""
    current = next((m for m in loaded if m.name == model), None)
    if current is None or not current.size or current.size_vram is None:
        return Check(
            "gpu",
            Level.OK,
            "Carte graphique",
            f"Le modèle {model} n'est pas chargé en ce moment : il le sera à la prochaine leçon.",
        )
    share = current.size_vram / current.size
    if share >= GPU_SHARE_OK:
        return Check(
            "gpu",
            Level.OK,
            "Carte graphique",
            f"Le modèle {model} tient entièrement dans la carte graphique.",
        )
    fits = sorted(
        (m for m in installed if m.name != model and 0 < m.size <= current.size_vram * FIT_MARGIN),
        key=lambda m: -m.size,
    )
    advice = (
        "Modèles installés qui tiendraient : "
        + ", ".join(f"{m.name} ({_gb(m.size)})" for m in fits[:3])
        + "."
        if fits
        else "Aucun des modèles installés n'est assez petit : installez-en un plus léger."
    )
    return Check(
        "gpu",
        Level.WARNING,
        "Carte graphique",
        f"Le modèle {model} ({_gb(current.size)}) déborde de la carte graphique : "
        f"{round(100 * (1 - share))} % tourne sur le processeur, les leçons sont beaucoup plus lentes.",
        f"Fermez les jeux et vidéos, ou choisissez un modèle plus petit. {advice}",
    )


def lessons_check(statuses: list[str]) -> Check:
    """`statuses` : état des dernières leçons de la famille, la plus récente d'abord."""
    recent = statuses[:RECENT_LESSONS]
    failed = sum(1 for s in recent if s == "failed")
    if not recent:
        return Check("lessons", Level.OK, "Dernières leçons", "Aucune leçon envoyée pour l'instant.")
    if failed == 0:
        return Check(
            "lessons", Level.OK, "Dernières leçons", f"Les {len(recent)} dernières leçons ont été préparées."
        )
    level = Level.ERROR if recent[0] == "failed" and failed >= 2 else Level.WARNING
    return Check(
        "lessons",
        level,
        "Dernières leçons",
        f"{failed} des {len(recent)} dernières leçons n'ont pas pu être préparées.",
        "Ouvrez la leçon en échec pour voir pourquoi, puis relancez-la ou vérifiez l'IA ci-dessus.",
    )


def overall(checks: list[Check]) -> Level:
    if any(c.level is Level.ERROR for c in checks):
        return Level.ERROR
    return Level.WARNING if any(c.level is Level.WARNING for c in checks) else Level.OK
