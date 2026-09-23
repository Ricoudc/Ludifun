import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from app.domain.activities.registry import ActivityRegistry, default_registry
from app.domain.knowledge import KnowledgeUnit, LessonAnalysis
from app.domain.validation import validate_analysis, validate_material

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "lessons"
LESSON_FILES = sorted(p.name for p in FIXTURES.glob("*.json"))


@dataclass(frozen=True)
class ReferenceLesson:
    name: str
    raw: dict[str, Any]
    analysis: LessonAnalysis
    units: dict[str, KnowledgeUnit]

    def unit(self, knowledge_id: str) -> KnowledgeUnit:
        return self.units[knowledge_id]


def load_lesson(name: str) -> ReferenceLesson:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    analysis = validate_analysis(raw["analysis"], raw["ocr_text"]).analysis
    units = {
        item.id: KnowledgeUnit(item=item, material=validate_material(item, raw["material"][item.id]).material)
        for item in analysis.knowledge
    }
    return ReferenceLesson(name, raw, analysis, units)


@pytest.fixture(params=LESSON_FILES)
def lesson(request: pytest.FixtureRequest) -> ReferenceLesson:
    return load_lesson(request.param)


@pytest.fixture
def history() -> ReferenceLesson:
    return load_lesson("history_cm1_revolution.json")


@pytest.fixture
def math() -> ReferenceLesson:
    return load_lesson("math_cm2_fractions.json")


@pytest.fixture
def science() -> ReferenceLesson:
    return load_lesson("science_ce2_water_states.json")


@pytest.fixture
def registry() -> ActivityRegistry:
    return default_registry()
