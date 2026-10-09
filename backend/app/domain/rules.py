"""Règles du moteur pédagogique, lues dans `engine_rules.toml` (cahier des charges §125, §138).

Les seuils de décision ne sont pas dans le code : on les règle dans le fichier, dont la version
est enregistrée avec chaque séance (`ENGINE_VERSION`). Un fichier invalide empêche le serveur de
démarrer (mieux qu'un moteur qui décide avec des valeurs absurdes).
"""

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_FILE = Path(__file__).with_name("engine_rules.toml")


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SessionRules(_Section):
    block_size: int = Field(ge=1)
    strong_notions_needed: int = Field(ge=1)
    speed_notions: int = Field(ge=1)
    replay_max: int = Field(ge=0)
    errors_per_notion: int = Field(ge=1)
    express_below: int = Field(ge=0)
    level_up_score: int = Field(ge=0, le=100)
    deepen_score: int = Field(ge=0, le=100)
    missing_level_score: int = Field(ge=0, le=100)
    # Étape 25 : dans l'approfondissement, les jeux visuels (ranger, remettre dans l'ordre,
    # colorier) passent avant les autres formats quand la notion le permet.
    visual_first: bool = False
    # 1.12.0 : d'une séance à l'autre, à difficulté égale, les formats les moins joués d'abord.
    vary_formats: bool = False
    # Durée estimée d'une séance (1.10.0) : complétée jusqu'à `min_minutes`, sans dépasser
    # `max_minutes` (le temps du jour choisi par le parent peut demander plus : il décide alors).
    min_minutes: int = Field(5, ge=0)
    max_minutes: int = Field(10, ge=1)


class MasteryRules(_Section):
    review_interval_days: dict[int, int]
    mastered_rate: float = Field(ge=0, le=1)
    fragile_rate: float = Field(ge=0, le=1)
    known_score: int = Field(ge=0, le=100)
    important: int = Field(ge=1, le=5)
    half_life_factor: float = Field(3.0, gt=0)
    fading_drop: int = Field(15, ge=1, le=100)


class HelpRules(_Section):
    result_factor: dict[int, float]
    level_proof_max_help: int = Field(ge=0, le=5)


class AdaptationRules(_Section):
    remediation_after_failures: int = Field(ge=1)
    max_remediations: int = Field(ge=0)
    failure_below: float = Field(ge=0, le=1)
    window: int = Field(ge=1)
    fast_wrong: int = Field(ge=1)
    struggling: int = Field(ge=1)
    hint_spacing: int = Field(ge=0)
    random_below_ms: int = Field(ge=0)
    recurring_sessions: int = Field(ge=2)


class BonusRules(_Section):
    min_score: float = Field(ge=0, le=1)
    max_time_share: float = Field(gt=0, le=1)
    activities: int = Field(ge=1)


class RewardRules(_Section):
    daily_xp_cap: int = Field(ge=0)


class MaterialRules(_Section):
    similar_ratio: float = Field(gt=0.5, le=1)
    sourced_notions: int = Field(ge=0, le=10)
    sourced_per_notion: int = Field(ge=0, le=5)


class PictureRules(_Section):
    per_lesson: int = Field(ge=0, le=8)


class HomeworkRules(_Section):
    attempts_before_solution: int = Field(ge=1, le=10)


class DifficultyRules(_Section):
    step_up_after: int = Field(ge=2, le=10)
    step_down_after: int = Field(ge=1, le=10)
    success: float = Field(gt=0, le=1)
    window: int = Field(ge=2, le=20)


class ConfidenceRules(_Section):
    high: float = Field(gt=0, le=1)
    low: float = Field(gt=0, le=1)


class ReminderRules(_Section):
    after_hour: int = Field(ge=0, le=23)


class TeachRules(_Section):
    follow_ups: int = Field(ge=0, le=5)
    explain_ratio: float = Field(gt=0, le=1)


class SubjectRules(_Section):
    # Matière → jeux jamais proposés pour ses leçons (codes d'activité).
    excluded_activities: dict[str, frozenset[str]] = Field(default_factory=dict)


class EngineRules(_Section):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    session: SessionRules
    mastery: MasteryRules
    help: HelpRules
    adaptation: AdaptationRules
    bonus: BonusRules
    rewards: RewardRules
    pictures: PictureRules
    material: MaterialRules
    homework: HomeworkRules
    teach: TeachRules
    difficulty: DifficultyRules
    confidence: ConfidenceRules
    reminders: ReminderRules
    subjects: SubjectRules = Field(default_factory=SubjectRules)


def load_rules(path: Path | None = None) -> EngineRules:
    file = path or Path(os.environ.get("LUDIFUN_ENGINE_RULES") or DEFAULT_FILE)
    with file.open("rb") as handle:
        rules = EngineRules.model_validate(tomllib.load(handle))
    if set(rules.mastery.review_interval_days) != {1, 2, 3, 4, 5}:
        raise ValueError("mastery.review_interval_days : une durée pour chaque boîte de 1 à 5")
    if set(rules.help.result_factor) != set(range(6)):
        raise ValueError("help.result_factor : une part pour chaque niveau d'aide de 0 à 5")
    return rules


RULES = load_rules()
ENGINE_VERSION = RULES.version
