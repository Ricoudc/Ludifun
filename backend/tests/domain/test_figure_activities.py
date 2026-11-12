"""Activités sur une figure (étape 22) : la bibliothèque, la carte et le coloriage."""

import json
import random
from datetime import UTC, datetime

import pytest

from app.domain.activities.base import ActivityCode, InvalidResponse
from app.domain.activities.registry import ActivityRegistry
from app.domain.composer import SessionComposer
from app.domain.figures import ORDER, default_library, figure_path, zone_key
from app.domain.knowledge import KnowledgeType, KnowledgeUnit
from app.domain.simulated_pupil import respond
from app.domain.understanding import CognitiveLevel, cognitive_level
from tests.domain.conftest import ReferenceLesson

NOW = datetime(2026, 9, 24, 17, 0, tzinfo=UTC)
PLANETS = {
    "planètes telluriques": ["Mercure", "Vénus", "la Terre", "Mars"],
    "planètes gazeuses": ["Jupiter", "Saturne", "Uranus", "Neptune"],
}


def place(history: ReferenceLesson, knowledge_id: str, label: str) -> KnowledgeUnit:
    """Une notion « lieu » (« la Bretagne »), sur la base d'une notion existante."""
    base = history.unit(knowledge_id)
    item = base.item.model_copy(
        update={"type": KnowledgeType.PLACE, "label": label, "attributes": {"description": label}}
    )
    return KnowledgeUnit(item=item, material=base.material)


def classification(history: ReferenceLesson, categories: dict[str, list[str]]) -> KnowledgeUnit:
    base = history.unit("k1")
    attributes = {"categories": [{"name": n, "members": m} for n, m in categories.items()]}
    item = base.item.model_copy(
        update={"type": KnowledgeType.CLASSIFICATION, "label": "Les planètes", "attributes": attributes}
    )
    return KnowledgeUnit(item=item, material=base.material)


@pytest.mark.parametrize(
    ("text", "key"),
    [("La Bretagne", "bretagne"), ("l'Asie", "asie"), ("Les Alpes", "alpes"), ("Le Moyen Âge", "moyen age")],
)
def test_zone_key(text: str, key: str) -> None:
    assert zone_key(text) == key


def test_every_figure_is_well_formed() -> None:
    library = default_library()
    assert [f.id for f in library.figures] == list(ORDER)
    for figure in library.figures:
        path = figure_path(figure.id)
        assert path is not None
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["width"] > 0 and data["height"] > 0 and data["credits"]
        ids = [z.id for z in figure.zones]
        assert len(ids) == len(set(ids)), figure.id
        keys = [k for z in figure.zones for k in z.keys]
        assert len(keys) == len(set(keys)), f"{figure.id} : deux zones portent le même nom"
        for zone in data["zones"]:
            assert zone["kind"] in ("area", "line", "point") and zone["shapes"], (figure.id, zone["id"])
            for polygon in zone["shapes"]:
                assert all(len(ring) >= 4 and len(ring) % 2 == 0 for ring in polygon)
    assert figure_path("../secrets") is None


def test_library_finds_the_figure_holding_every_notion() -> None:
    library = default_library()
    found = library.placement(["La Bretagne", "Normandie", "la Corse"])
    assert found is not None and found[0].id == "france-regions"
    rivers = library.placement(["La Loire", "La Seine", "Le Rhône"])
    assert rivers is not None and rivers[0].id == "france-relief"  # la Loire, fleuve plutôt que département
    assert library.placement(["Bretagne", "Jupiter"]) is None
    assert library.placement(["Bretagne", "la Bretagne"]) is None  # deux fois la même zone


def test_map(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    game = registry.get(ActivityCode.MAP)
    units = [
        place(history, f"k{i}", name)
        for i, name in enumerate(["Bretagne", "Occitanie", "Grand Est"], start=1)
    ]
    assert game.can_build(units, 2) and not game.can_build(units[:1], 2)
    assert cognitive_level(ActivityCode.MAP, 2) is CognitiveLevel.RECOGNIZE
    activity = game.build(units, 2, random.Random(1))
    assert activity.payload["figure"] == {"id": "france-regions", "version": 1}
    assert sorted(i["text"] for i in activity.payload["items"]) == ["Bretagne", "Grand Est", "Occitanie"]

    perfect = game.grade(activity, respond(activity, lambda _: True))
    assert perfect.score == 1 and set(perfect.evidence.values()) == {1.0}
    missed = units[0].id
    wrong = game.grade(activity, respond(activity, lambda k: k != missed))
    assert wrong.evidence[missed] == 0 and wrong.errors == {missed: "confusion"}
    detail = next(d for d in wrong.details if not d["correct"])
    assert detail["zone"] == "bretagne" and detail["touched_name"] in ("Occitanie", "Grand Est")

    first = activity.payload["items"][0]["id"]
    with pytest.raises(InvalidResponse):
        game.grade(activity, {"answers": [[first, "bretagne"]]})  # pas tout répondu
    unknown = [[i["id"], "atlantide"] for i in activity.payload["items"]]
    assert game.grade(activity, {"answers": unknown}).score == 0  # zone inconnue : faux


def test_coloring(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    game = registry.get(ActivityCode.COLORING)
    unit = classification(history, PLANETS)
    assert game.can_build([unit], 2) and cognitive_level(ActivityCode.COLORING, 2) is CognitiveLevel.RECALL
    activity = game.build([unit], 2, random.Random(2))
    assert activity.payload["figure"]["id"] == "systeme-solaire" and activity.payload["count"] == 8
    assert [p["name"] for p in activity.payload["palette"]] == list(PLANETS)
    assert "Mercure" not in json.dumps(activity.payload)  # les zones à colorier ne sont pas montrées

    assert game.grade(activity, respond(activity, lambda _: True)).score == 1
    bad = game.grade(activity, respond(activity, lambda _: False))
    assert bad.score == 0 and bad.errors == {unit.id: "confusion"}
    assert {d["text"] for d in bad.details} >= {"Mercure", "la Terre"}
    partial = game.grade(activity, {"colors": [["terre", "p1"], ["jupiter", "p2"], ["soleil", "p1"]]})
    assert partial.score == 2 / 8  # le Soleil n'était pas à colorier : sans effet
    with pytest.raises(InvalidResponse):
        game.grade(activity, {"colors": [["terre", "p9"]]})
    with pytest.raises(InvalidResponse):
        game.grade(activity, {"colors": [["terre", "p1"], ["terre", "p2"]]})


def test_coloring_needs_every_element_on_one_figure(
    history: ReferenceLesson, registry: ActivityRegistry
) -> None:
    game = registry.get(ActivityCode.COLORING)
    assert not game.accepts(
        classification(history, {"a": ["Mercure", "Vénus"], "b": ["Jupiter", "Bretagne"]})
    )
    assert not game.accepts(classification(history, {"a": ["Mercure"], "b": ["Jupiter"]}))  # trop peu


def test_first_session_prefers_the_map(history: ReferenceLesson, registry: ActivityRegistry) -> None:
    units = [
        place(history, "k1", "Bretagne"),
        place(history, "k2", "Normandie"),
        place(history, "k3", "Corse"),
        *list(history.units.values())[3:],
    ]
    session = SessionComposer(registry).compose(units, {}, NOW, seed=5)
    assert [i.activity.type for i in session.items if i.block == "match"] == [ActivityCode.MAP]
