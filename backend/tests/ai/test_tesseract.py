"""Lecture des photos par Tesseract et mode « auto » (§5.65).

- le code décide de la qualité de la page et des passages douteux, à partir de la confiance de
  Tesseract ; un passage douteux est vérifiable (il est dans son contexte, le contexte dans la page) ;
- la photo passe par l'entrée standard : aucun fichier ; Tesseract absent : une erreur claire ;
- « auto » : seules les pages mal lues vont au modèle de vision, et seulement s'il lit les images ;
- avec le vrai programme (s'il est installé) : une fiche imprimée photographiée est bien lue.
"""

import io
import json
import shutil
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.ai.check import check
from app.ai.factory import AiChoice, build_providers, ocr_for
from app.ai.fallback import FallbackLLM
from app.ai.ocr.tesseract import AutoOcr, TesseractOcr, Word, page_of, parse_tsv, prepare
from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.ports import AIError, LLMResult, PageImage, Usage
from app.ai.pricing import run_cost
from app.ai.providers.fake import FakeProvider
from app.ai.providers.ollama import OllamaProvider, reads_images
from app.ai.schemas import OcrPage, OcrResult
from app.config import Settings
from app.domain.ocr_review import select_uncertain

FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
needs_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None or not FONT.exists(), reason="tesseract ou police absents"
)


def words(text: str, confidence: float = 95, line: tuple[int, int, int] = (1, 1, 1)) -> list[Word]:
    return [Word(w, confidence, line) for w in text.split()]


def png(width: int = 200, height: int = 100) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(out, format="PNG")
    return out.getvalue()


def test_tsv_words_in_reading_order() -> None:
    tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "1\t1\t0\t0\t0\t0\t0\t0\t100\t100\t-1\t\n"
        "5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t96.5\tLe\n"
        "5\t1\t1\t1\t1\t2\t0\t0\t10\t10\t91\tverbe\n"
        "5\t1\t1\t1\t1\t3\t0\t0\t10\t10\t-1\t \n"
        "5\t1\t2\t1\t1\t1\t0\t0\t10\t10\t40\taller\n"
        "5\tcassé\n"
    )
    assert parse_tsv(tsv) == [
        Word("Le", 96.5, (1, 1, 1)),
        Word("verbe", 91.0, (1, 1, 1)),
        Word("aller", 40.0, (2, 1, 1)),
    ]


def test_quality_is_decided_by_the_code() -> None:
    good = page_of(0, words("Le verbe aller au présent") + words("je vais", line=(1, 1, 2)))
    assert good.quality == "good" and good.text == "Le verbe aller au présent\nje vais"
    assert good.uncertain == []
    partial = page_of(1, words("Le verbe aller", 70))
    assert partial.quality == "partial" and partial.text == "Le verbe aller"
    assert page_of(2, words("des gribouillis illisibles", 30)).quality == "unreadable"
    assert page_of(3, words("deux mots")) == OcrPage(index=3, quality="unreadable", text="")
    # Un nouveau paragraphe est séparé par une ligne vide.
    two = page_of(0, words("Exercice un") + words("Exercice deux", line=(2, 1, 1)))
    assert two.text == "Exercice un\n\nExercice deux"


def test_doubtful_words_are_checkable_by_the_child() -> None:
    line = [
        Word("Le", 95, (1, 1, 1)),
        Word("docteur", 95, (1, 1, 1)),
        Word("travaille", 95, (1, 1, 1)),
        Word("à", 30, (1, 1, 1)),  # trop court pour être montré
        Word("l'hôpita1", 41, (1, 1, 1)),
        Word("de", 95, (1, 1, 1)),
        Word("Lyon.", 52, (1, 1, 1)),
    ]
    page = page_of(0, line)
    assert [u.text for u in page.uncertain] == ["l'hôpita1", "Lyon."]  # le moins sûr d'abord
    assert page.uncertain[0].context == "Le docteur travaille à l'hôpita1 de Lyon."
    review = select_uncertain([(0, page.text, [(u.text, u.context) for u in page.uncertain])])
    assert [r.text for r in review] == ["l'hôpita1", "Lyon."]


def test_photo_is_prepared_in_memory() -> None:
    with Image.open(io.BytesIO(prepare(png(600, 300)))) as image:
        assert image.mode == "L" and max(image.size) == 1800  # petite photo agrandie
    with pytest.raises(AIError, match="photo illisible"):
        prepare(b"pas une image")


async def test_missing_program_is_a_clear_error() -> None:
    reader = TesseractOcr(command="/nulle/part/tesseract")
    with pytest.raises(AIError, match="Tesseract n'est pas installé"):
        await reader.extract((PageImage(png(), "image/png"),))
    assert run_cost(reader.model, None, None) == 0.0  # gratuit, compté comme tel


@needs_tesseract
async def test_a_printed_worksheet_photographed() -> None:
    font = ImageFont.truetype(str(FONT), 34)
    sheet = Image.new("L", (1400, 700), 235)
    draw = ImageDraw.Draw(sheet)
    lines = [
        "Le verbe aller au présent",
        "je vais, tu vas, il va, nous allons",
        "Mots à savoir écrire : hôpital, chevaux, aujourd'hui.",
    ]
    for i, text in enumerate(lines):
        draw.text((70, 60 + 80 * i), text, fill=30, font=font)
    photo = sheet.rotate(2, expand=True, fillcolor=200).filter(ImageFilter.GaussianBlur(1))
    out = io.BytesIO()
    photo.save(out, format="JPEG", quality=70)
    blank = io.BytesIO()
    Image.new("L", (800, 600), 240).save(blank, format="JPEG")
    result = await TesseractOcr().extract(
        (PageImage(out.getvalue(), "image/jpeg"), PageImage(blank.getvalue(), "image/jpeg"))
    )
    first, second = result.output.pages
    assert first.quality == "good"
    for expected in ("verbe aller au présent", "nous allons", "hôpital", "aujourd'hui"):
        assert expected in first.text
    assert second.quality == "unreadable" and second.index == 1
    assert result.usage.provider == "tesseract" and result.usage.input_tokens is None


class FakeReader:
    """Un lecteur dont on choisit la réponse, et qui note les pages reçues."""

    def __init__(self, name: str, pages: list[OcrPage] | None = None, error: bool = False) -> None:
        self.name, self.model, self.prompt_version = name, f"{name}-model", f"{name}.v1"
        self.pages, self.error = pages or [], error
        self.received: list[tuple[PageImage, ...]] = []

    async def extract(self, pages: tuple[PageImage, ...]) -> LLMResult[OcrResult]:
        self.received.append(pages)
        if self.error:
            raise AIError(f"{self.name} en panne")
        output = OcrResult(pages=self.pages, language="fr", warnings=[])
        return LLMResult(output, Usage(self.name, self.model, 100, 50, 30))


def auto(primary: FakeReader, vision: FakeReader, reads: bool | None = None) -> AutoOcr:
    async def probe() -> bool:
        assert reads is not None
        return reads

    return AutoOcr(primary, vision, None if reads is None else probe)  # type: ignore[arg-type]


PAGES = (PageImage(b"p0", "image/png"), PageImage(b"p1", "image/png"), PageImage(b"p2", "image/png"))
TESS = [
    OcrPage(index=0, quality="good", text="imprimé"),
    OcrPage(index=1, quality="unreadable", text=""),
    OcrPage(index=2, quality="partial", text="à moitié"),
]


async def test_auto_sends_only_the_weak_pages_to_the_vision_model() -> None:
    vision = FakeReader(
        "vision",
        [OcrPage(index=0, quality="good", text="cursive"), OcrPage(index=1, quality="unreadable", text="")],
    )
    result = await auto(FakeReader("tesseract", TESS), vision).extract(PAGES)
    assert vision.received == [(PAGES[1], PAGES[2])]
    assert [(p.index, p.quality, p.text) for p in result.output.pages] == [
        (0, "good", "imprimé"),
        (1, "good", "cursive"),
        (2, "partial", "à moitié"),  # la relecture était pire : celle de Tesseract est gardée
    ]
    assert result.usage.provider == "vision" and result.usage.latency_ms == 60  # tokens de l'IA
    assert "2 page(s) relue(s)" in result.output.warnings[0]


async def test_auto_reports_an_incomplete_vision_reread() -> None:
    vision = FakeReader("vision", [OcrPage(index=0, quality="good", text="cursive")])
    result = await auto(FakeReader("tesseract", TESS), vision).extract(PAGES)

    assert result.output.pages[1].quality == "good"
    assert result.output.pages[2] == TESS[2]  # page non renvoyée : texte Tesseract conservé
    assert "1/2 page(s) relue(s)" in result.output.warnings[0]
    assert "1 page(s) sans réponse" in result.output.warnings[1]


async def test_auto_keeps_tesseract_when_the_ai_cannot_help() -> None:
    good = [OcrPage(index=i, quality="good", text="ok") for i in range(3)]
    vision = FakeReader("vision")
    assert (await auto(FakeReader("tesseract", good), vision).extract(PAGES)).usage.provider == "tesseract"
    assert vision.received == []  # tout est bien lu : l'IA ne voit pas les photos
    blind = await auto(FakeReader("tesseract", TESS), vision, reads=False).extract(PAGES)
    assert vision.received == [] and "ne lit pas les images" in blind.output.warnings[-1]
    broken = await auto(FakeReader("tesseract", TESS), FakeReader("vision", error=True)).extract(PAGES)
    assert broken.output.pages == TESS and "impossible" in broken.output.warnings[-1]
    # Tesseract absent : le modèle de vision lit tout.
    rescue = FakeReader("vision", good)
    await auto(FakeReader("tesseract", error=True), rescue).extract(PAGES)
    assert rescue.received == [PAGES]


async def test_ollama_vision_capability() -> None:
    def server(capabilities: list[str] | None, status: int = 200) -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/show" and json.loads(request.content) == {"model": "m"}
            return httpx.Response(status, json={} if capabilities is None else {"capabilities": capabilities})

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    assert not await reads_images("http://pc:11434", "m", server(["completion"]))
    assert await reads_images("http://pc:11434", "m", server(["completion", "vision"]))
    assert await reads_images("http://pc:11434", "m", server(None))  # ancienne version : on suppose oui
    assert await reads_images("http://pc:11434", "m", server(None, 404))


def test_the_reader_follows_the_setting() -> None:
    fake = FakeProvider()
    assert isinstance(ocr_for(Settings(), fake), VisionLLMOcr)  # par défaut : rien ne change
    assert isinstance(ocr_for(Settings(ocr_engine="tesseract"), fake), TesseractOcr)
    plain = ocr_for(Settings(ocr_engine="auto"), fake)
    assert isinstance(plain, AutoOcr) and plain._reads_images is None
    ollama = OllamaProvider("http://pc:11434", {"ocr": "mistral:7b"})
    for llm in (ollama, FallbackLLM([ollama, fake])):
        reader = ocr_for(Settings(ocr_engine="auto"), llm)
        assert isinstance(reader, AutoOcr) and reader._reads_images is not None
    ocr, _ = build_providers(Settings(ai_provider="fake", ocr_engine="tesseract"))
    assert ocr.name == "tesseract" and ocr.prompt_version == "tesseract.v1"


async def test_a_text_model_is_enough_when_tesseract_reads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "mistral:7b"}]})
        return httpx.Response(200, json={"capabilities": ["completion"]})

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    choice = AiChoice("ollama", "mistral:7b")
    assert not (await check(choice, Settings(), client())).ok
    tesseract = await check(choice, Settings(ocr_engine="tesseract"), client())
    assert tesseract.ok and "Tesseract" in tesseract.message
    mixed = await check(choice, Settings(ocr_engine="auto"), client())
    assert mixed.ok and "Tesseract seul" in mixed.message


def test_tesseract_reads_then_groq_analyses_and_creates(monkeypatch: pytest.MonkeyPatch) -> None:
    """La combinaison voulue par la famille : Tesseract lit la photo sur le PC, Groq analyse la
    leçon et crée les questions ; seule la transcription part chez Groq, jamais la photo."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_essai")
    ocr, llm = build_providers(Settings(ai_provider="groq", ocr_engine="tesseract"))
    assert isinstance(ocr, TesseractOcr)  # aucune image n'est donnée à l'IA
    assert llm.name == "groq" and llm.model_for("analysis") and llm.model_for("material")
