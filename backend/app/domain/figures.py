"""Bibliothèque de figures (étape 22) : cartes et schémas dont les zones ont un nom.

Les figures sont des fichiers JSON (`app/figures/`) produits par `tools/figures/build_figures.py`
à partir de Natural Earth, des contours de l'IGN et de dessins faits pour Ludifun. Le moteur ne
lit que les noms des zones : une notion (« la Bretagne », « le fémur », « Jupiter ») dont le nom
est celui d'une zone peut être travaillée sur la figure. L'application reçoit la figure entière
par `GET /v1/figures/{id}`.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from app.domain.text import normalize

FIGURES_DIR = Path(__file__).resolve().parents[1] / "figures"
# Ordre de préférence quand plusieurs figures conviennent (« Loire » : fleuve ou département).
ORDER = (
    "france-regions",
    "france-relief",
    "europe",
    "monde",
    "france-departements",
    "systeme-solaire",
    "squelette",
    "appareil-digestif",
    "plante",
    "cycle-de-l-eau",
    "volcan",
    "periodes-histoire",
)
ARTICLES = frozenset({"le", "la", "les", "l", "un", "une", "des", "du"})


def zone_key(text: str) -> str:
    """Clé de comparaison d'un nom : « La Bretagne » → « bretagne », « l'Asie » → « asie »."""
    words = normalize(text).split()
    if len(words) > 1 and words[0] in ARTICLES:
        words = words[1:]
    return " ".join(words)


@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    keys: frozenset[str]


@dataclass(frozen=True)
class Figure:
    id: str
    version: int
    title: str
    subject: str
    zones: tuple[Zone, ...]

    @property
    def ref(self) -> dict[str, Any]:
        """Ce que la charge utile d'une activité dit de la figure."""
        return {"id": self.id, "version": self.version}

    def zone(self, zone_id: str) -> Zone | None:
        return next((z for z in self.zones if z.id == zone_id), None)

    def find(self, text: str) -> Zone | None:
        key = zone_key(text)
        return next((z for z in self.zones if key in z.keys), None)


def parse(data: dict[str, Any]) -> Figure:
    zones = tuple(
        Zone(
            id=z["id"],
            name=z["name"],
            keys=frozenset(zone_key(n) for n in (z["name"], *z.get("aliases", []))),
        )
        for z in data["zones"]
    )
    return Figure(data["id"], data["version"], data["title"], data["subject"], zones)


class FigureLibrary:
    def __init__(self, figures: list[Figure]) -> None:
        self.figures = figures
        self._by_id = {f.id: f for f in figures}

    def get(self, figure_id: str) -> Figure | None:
        return self._by_id.get(figure_id)

    def matches(self, text: str) -> bool:
        return any(f.find(text) is not None for f in self.figures)

    def placement(self, texts: list[str]) -> tuple[Figure, list[Zone]] | None:
        """La première figure où chaque texte désigne une zone différente."""
        for figure in self.figures:
            zones = [figure.find(t) for t in texts]
            found = [z for z in zones if z is not None]
            if len(found) == len(texts) and len({z.id for z in found}) == len(found):
                return figure, found
        return None


def figure_path(figure_id: str) -> Path | None:
    return FIGURES_DIR / f"{figure_id}.json" if figure_id in ORDER else None


@cache
def default_library() -> FigureLibrary:
    figures = []
    for figure_id in ORDER:
        path = figure_path(figure_id)
        assert path is not None
        figures.append(parse(json.loads(path.read_text(encoding="utf-8"))))
    return FigureLibrary(figures)
