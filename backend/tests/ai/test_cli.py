import io
import json
from pathlib import Path

import pytest

from app.ai.providers.fake import DEMO_LESSON, LessonScript
from app.tools.analyze import main


def test_cli_with_a_photo(tmp_path: Path) -> None:
    photo = tmp_path / "page1.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xe0 fausse photo")
    out, report = io.StringIO(), tmp_path / "resultat.json"

    code = main([str(photo), "--provider", "fake", "--seed", "4", "--json", str(report)], out=out)

    text = out.getvalue()
    assert code == 0
    for expected in (
        "══ Leçon ══",
        "LA RÉVOLUTION FRANÇAISE",
        "✓ k1 [date, ★★★★★] 1789",
        "🧩 Association",
        "══ Appels IA ══",
    ):
        assert expected in text
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert saved["failure_reason"] is None
    assert set(saved["material"]) == {f"k{i}" for i in range(1, 9)}
    assert [r["stage"] for r in saved["runs"]][:2] == ["ocr", "analysis"]


def test_cli_with_text(tmp_path: Path) -> None:
    lesson = tmp_path / "lecon.txt"
    lesson.write_text(LessonScript.from_file(DEMO_LESSON).ocr_text, encoding="utf-8")
    out = io.StringIO()
    assert main(["--text", str(lesson), "--provider", "fake"], out=out) == 0
    assert "ocr " not in out.getvalue()  # pas d'appel OCR


def test_cli_reports_failures(tmp_path: Path) -> None:
    lesson = tmp_path / "chat.txt"
    lesson.write_text("Mon chat s'appelle Caramel.", encoding="utf-8")
    out = io.StringIO()
    assert main(["--text", str(lesson), "--provider", "fake"], out=out) == 1
    assert "✗ Échec : not_a_lesson" in out.getvalue()


def test_cli_rejects_unknown_formats(tmp_path: Path) -> None:
    heic = tmp_path / "page.heic"
    heic.write_bytes(b"\x00\x00\x00\x18ftypheic")
    with pytest.raises(SystemExit, match="format non pris en charge"):
        main([str(heic), "--provider", "fake"], out=io.StringIO())
