"""État de l'installation dit au parent (§5.89) : règles pures."""

from app.domain.installation import Check, Level, OllamaModel, gpu_check, lessons_check, overall

GB = 1_000_000_000
INSTALLED = [
    OllamaModel("qwen3-vl:8b", 6 * GB + 200_000_000),
    OllamaModel("qwen2.5vl:7b", 6 * GB),
    OllamaModel("llama3.1:8b", 4 * GB + 900_000_000),
    OllamaModel("qwen3.5:4b", 3 * GB + 300_000_000),
]


def test_a_model_that_overflows_the_graphics_card_gets_smaller_installed_ones() -> None:
    # PC d'essai : 6,4 Go dont 10 % sur le processeur.
    loaded = [OllamaModel("qwen3-vl:8b", 6_400_000_000, 5_760_000_000)]
    check = gpu_check("qwen3-vl:8b", loaded, INSTALLED)
    assert check.level is Level.WARNING
    assert "10 % tourne sur le processeur" in check.message and "6,4 Go" in check.message
    assert check.action is not None
    # 5,76 Go de carte, avec une marge pour le contexte et l'image : moins de 4,9 Go.
    assert "qwen3.5:4b (3,3 Go)" in check.action
    assert "qwen2.5vl:7b" not in check.action and "llama3.1:8b" not in check.action


def test_a_model_inside_the_graphics_card_is_fine() -> None:
    loaded = [OllamaModel("qwen3.5:4b", 3_300_000_000, 3_300_000_000)]
    assert gpu_check("qwen3.5:4b", loaded, INSTALLED).level is Level.OK
    assert "pas chargé" in gpu_check("qwen3.5:4b", [], INSTALLED).message


def test_no_smaller_model_installed_says_so() -> None:
    loaded = [OllamaModel("qwen3.5:4b", 3_300_000_000, 2_000_000_000)]
    check = gpu_check("qwen3.5:4b", loaded, INSTALLED)
    assert check.action is not None and "installez-en un plus léger" in check.action


def test_recent_lessons() -> None:
    assert lessons_check([]).level is Level.OK
    assert lessons_check(["ready"] * 6).message == "Les 5 dernières leçons ont été préparées."
    one = lessons_check(["ready", "failed", "ready"])
    assert one.level is Level.WARNING and "1 des 3" in one.message
    assert lessons_check(["failed", "failed", "ready"]).level is Level.ERROR


def test_the_worst_point_gives_the_overall_state() -> None:
    def check(level: Level) -> Check:
        return Check("x", level, "t", "m")

    assert overall([check(Level.OK)]) is Level.OK
    assert overall([check(Level.OK), check(Level.WARNING)]) is Level.WARNING
    assert overall([check(Level.WARNING), check(Level.ERROR)]) is Level.ERROR
