"""§5.81 : comparer deux évaluations (deux prompts, deux modèles) et revenir à la meilleure."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.tools.compare import better, main, render, verdict
from app.tools.evaluate import main as evaluate_main

EXAMPLE = Path(__file__).resolve().parents[3] / "eval" / "example"


def result(
    folder: Path, *, recall: float, invented: int, duration: float, analysis: str = "v8", model: str = "m1"
) -> Path:
    folder.mkdir(parents=True)
    data: dict[str, Any] = {
        "started": "2026-11-09T17:00:00+00:00",
        "configuration": {
            "provider": "claude",
            "models": {"analysis": model, "material": "m1"},
            "prompts": {"analysis": analysis, "material": "v9"},
        },
        "metrics": [
            {
                "name": "Leçons traitées correctement",
                "value": 100.0,
                "display": "100 %",
                "target": "",
                "ok": True,
            },
            {"name": "Rappel des notions indispensables", "value": recall, "display": f"{recall:.0f} %"},
            {"name": "Notions inventées (rejetées)", "value": invented, "display": str(invented)},
            {"name": "Durée photo → prête (médiane)", "value": duration, "display": f"{duration:.0f} s"},
            {"name": "Photos à faire vérifier (passages douteux)", "value": 50.0, "display": "50 %"},
        ],
        "lessons": {
            "fractions": {
                "ready": True,
                "recall": recall / 100,
                "invented": invented,
                "rejected": 1,
                "kept": 9,
                "duration_s": duration,
                "cost_usd": 0.01,
            },
        },
    }
    (folder / "metrics.json").write_text(json.dumps(data), encoding="utf-8")
    return folder


def test_direction_of_each_measure() -> None:
    assert better("Rappel des notions indispensables", 90, 80) == "A"
    assert better("Notions inventées (rejetées)", 2, 0) == "B"  # moins vaut mieux
    assert better("Durée photo → prête (médiane)", 30, 30.2) is None  # écart négligeable
    assert better("Photos à faire vérifier (passages douteux)", 10, 90) is None  # neutre


def test_accuracy_beats_speed_and_says_how_to_go_back(tmp_path: Path) -> None:
    old = result(tmp_path / "ancien", recall=95, invented=0, duration=60, analysis="v7")
    new = result(tmp_path / "nouveau", recall=80, invented=1, duration=20)
    v = verdict(
        json.loads((old / "metrics.json").read_text()), json.loads((new / "metrics.json").read_text())
    )
    assert v.winner == "A" and "justesse" in v.reason
    text = render(old, new)
    assert "- prompt analysis : v7 → v8" in text
    assert "**À garder : A (`ancien`)**" in text
    assert '`"analysis": "v7"` dans `PROMPT_VERSIONS`' in text
    assert "| fractions | 95 % → 80 % | 0 → 1 |" in text


def test_equal_accuracy_then_speed(tmp_path: Path) -> None:
    slow = result(tmp_path / "lent", recall=90, invented=0, duration=60, model="gros")
    fast = result(tmp_path / "rapide", recall=90, invented=0, duration=25, model="petit")
    text = render(slow, fast)
    assert "**À garder : B (`rapide`)**" in text and "durée photo → prête meilleure" in text
    assert "- modèle (analysis) : gros → petit" in text
    same = render(slow, slow)
    assert "**Égalité**" in same and "rien (même configuration" in same


def test_missing_metrics_says_what_to_do(tmp_path: Path) -> None:
    (tmp_path / "vide").mkdir()
    with pytest.raises(SystemExit, match="relancez l'évaluation"):
        render(tmp_path / "vide", tmp_path / "vide")


def test_end_to_end_with_an_older_prompt(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        evaluate_main(
            [str(EXAMPLE), "--provider", "fake", "--out", str(tmp_path / "a"), "--prompt", "analysis=v7"]
        )
        == 0
    )
    assert evaluate_main([str(EXAMPLE), "--provider", "fake", "--out", str(tmp_path / "b")]) == 0
    (a,), (b,) = list((tmp_path / "a").iterdir()), list((tmp_path / "b").iterdir())
    saved = json.loads((a / "metrics.json").read_text(encoding="utf-8"))
    assert saved["configuration"]["prompts"]["analysis"] == "v7" and saved["lessons"]
    assert main([str(a), str(b), "--out", str(tmp_path / "comparaison.md")]) == 0
    assert "prompt analysis : v7 → v8" in (tmp_path / "comparaison.md").read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        evaluate_main([str(EXAMPLE), "--provider", "fake", "--prompt", "analysis=v99"])
