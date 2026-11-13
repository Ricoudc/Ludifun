"""Lecture des photos par Tesseract (§5.65) : un programme d'OCR installé avec le serveur, sans
IA ni carte graphique, en un quart de seconde par page. La photo ne quitte jamais le PC : seul le
texte lu passe ensuite à l'IA choisie par la famille (Ollama, ou une IA en ligne).

Le code décide seul de ce que vaut la lecture, à partir de la confiance que Tesseract donne à
chaque mot : qualité de la page (bonne, partielle, illisible) et passages douteux montrés à
l'enfant (« Peux-tu vérifier ? », `app.domain.ocr_review`).

Tesseract lit très bien l'imprimé, mal l'écriture à la main et pas du tout les schémas : le mode
`auto` (`AutoOcr`) confie au modèle de vision les seules pages que Tesseract a mal lues.

La photo passe par l'entrée standard du programme : aucun fichier n'est écrit.
"""

import asyncio
import io
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace

from PIL import Image, ImageOps, UnidentifiedImageError

from app.ai.ports import AIError, LLMResult, OcrProvider, PageImage, Usage
from app.ai.schemas import OcrPage, OcrResult, UncertainOut

PROMPT_VERSION = "tesseract.v1"  # version de cette lecture (préparation, seuils), enregistrée
TIMEOUT_S = 60.0  # une page : moins d'une seconde d'ordinaire
MIN_SIDE = 1800  # une photo plus petite est agrandie : Tesseract lit mal les petites lettres
MAX_SIDE = 4000
MIN_WORDS = 3  # moins de mots lus : la page est illisible (dessin, page blanche, écriture à la main)
GOOD = 80.0  # confiance moyenne (0-100) au-dessus de laquelle la page est bien lue
PARTIAL = 55.0  # en dessous : illisible
DOUBT_BELOW = 60.0  # un mot moins sûr que cela est un passage douteux
MAX_UNCERTAIN = 5
CONTEXT_WORDS = 4  # mots gardés de chaque côté d'un passage douteux
_RANK = {"unreadable": 0, "partial": 1, "good": 2}


@dataclass(frozen=True)
class Word:
    text: str
    confidence: float
    line: tuple[int, int, int]  # bloc, paragraphe, ligne


def prepare(data: bytes) -> bytes:
    """La photo remise droite (EXIF), en gris, contrastée, à une taille que Tesseract lit bien."""
    try:
        with Image.open(io.BytesIO(data)) as opened:
            image = ImageOps.exif_transpose(opened).convert("L")
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        raise AIError("photo illisible par Tesseract") from exc
    side = max(image.size)
    if side < MIN_SIDE or side > MAX_SIDE:
        factor = (MIN_SIDE if side < MIN_SIDE else MAX_SIDE) / side
        size = (round(image.width * factor), round(image.height * factor))
        image = image.resize(size, Image.Resampling.LANCZOS)
    image = ImageOps.autocontrast(image, cutoff=1)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def parse_tsv(tsv: str) -> list[Word]:
    """Les mots de la sortie TSV de Tesseract (niveau 5), dans l'ordre de lecture."""
    words: list[Word] = []
    for row in tsv.splitlines()[1:]:
        cells = row.split("\t")
        if len(cells) < 12 or cells[0] != "5" or not cells[11].strip():
            continue
        try:
            confidence = float(cells[10])
            line = (int(cells[2]), int(cells[3]), int(cells[4]))
        except ValueError:
            continue
        if confidence >= 0:
            words.append(Word(cells[11].strip(), confidence, line))
    return words


def _lines(words: list[Word]) -> list[list[Word]]:
    lines: list[list[Word]] = []
    for word in words:
        if lines and lines[-1][0].line == word.line:
            lines[-1].append(word)
        else:
            lines.append([word])
    return lines


def page_of(index: int, words: list[Word]) -> OcrPage:
    """Texte, qualité et passages douteux d'une page, décidés par le code."""
    letters = sum(len(w.text) for w in words)
    if len(words) < MIN_WORDS or not letters:
        return OcrPage(index=index, quality="unreadable", text="")
    mean = sum(w.confidence * len(w.text) for w in words) / letters  # un long mot compte plus
    if mean < PARTIAL:
        return OcrPage(index=index, quality="unreadable", text="")
    lines = _lines(words)
    parts: list[str] = []
    for i, line in enumerate(lines):
        if i:  # un nouveau paragraphe est séparé par une ligne vide
            parts.append("\n\n" if line[0].line[:2] != lines[i - 1][0].line[:2] else "\n")
        parts.append(" ".join(w.text for w in line))
    doubtful: list[tuple[float, UncertainOut]] = []
    for line in lines:
        for k, word in enumerate(line):
            # Les nombres, fractions et symboles mathématiques sont importants même sans
            # trois lettres : une seule confusion (« 1989 » → « 1980 ») change le sens.
            important = sum(c.isalpha() for c in word.text) >= 3 or any(
                c.isdigit() or c in "=+-×÷/%²³°<>√π∑∫≈≠≤≥" for c in word.text
            )
            if word.confidence >= DOUBT_BELOW or not important:
                continue
            context = " ".join(w.text for w in line[max(0, k - CONTEXT_WORDS) : k + CONTEXT_WORDS + 1])
            doubtful.append((word.confidence, UncertainOut(text=word.text, context=context)))
    doubtful.sort(key=lambda d: d[0])
    return OcrPage(
        index=index,
        quality="good" if mean >= GOOD else "partial",
        text="".join(parts),
        uncertain=[u for _, u in doubtful[:MAX_UNCERTAIN]],
    )


class TesseractOcr:
    """① Lecture des photos par le programme `tesseract` (paquets tesseract-ocr, -fra, -eng)."""

    name = "tesseract"
    prompt_version = PROMPT_VERSION

    def __init__(self, command: str = "tesseract", languages: str = "fra+eng") -> None:
        self.command = command
        self.languages = languages
        self.model = f"tesseract/{languages}"

    async def _read(self, data: bytes) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                self.command,
                "stdin",
                "stdout",
                "-l",
                self.languages,
                "--psm",
                "3",
                "tsv",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise AIError(
                "Tesseract n'est pas installé sur le serveur (paquets tesseract-ocr et tesseract-ocr-fra)"
            ) from exc
        try:
            out, err = await asyncio.wait_for(process.communicate(prepare(data)), TIMEOUT_S)
        except TimeoutError as exc:
            process.kill()
            raise AIError(f"Tesseract n'a pas lu la page en {TIMEOUT_S:.0f} s") from exc
        if process.returncode != 0:
            # Le message de Tesseract nomme seulement une langue ou un fichier manquant.
            detail = err.decode("utf-8", "replace").strip().splitlines()[:1]
            raise AIError("Tesseract a échoué" + (f" : {detail[0][:200]}" if detail else ""))
        return out.decode("utf-8", "replace")

    async def extract(self, pages: tuple[PageImage, ...]) -> LLMResult[OcrResult]:
        started = time.perf_counter()
        read = [page_of(i, parse_tsv(await self._read(page.data))) for i, page in enumerate(pages)]
        warnings = (
            ["Lecture par Tesseract : une partie du texte est peu sûre (écriture à la main, photo floue ?)."]
            if any(p.quality != "good" for p in read)
            else []
        )
        output = OcrResult(pages=read, language="fr", warnings=warnings)
        latency = round((time.perf_counter() - started) * 1000)
        return LLMResult(output, Usage(self.name, self.model, None, None, latency))


class AutoOcr:
    """Mode `auto` : Tesseract d'abord ; les pages qu'il a mal lues sont relues par le modèle de
    vision, si l'IA de la famille sait lire les images. Sans elle, ou si elle échoue, la lecture
    de Tesseract est gardée. Tesseract absent : tout est lu par le modèle de vision."""

    def __init__(
        self,
        primary: TesseractOcr,
        vision: OcrProvider,
        reads_images: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        self.primary = primary
        self.vision = vision
        self.name = f"auto:{primary.name}+{vision.name}"
        self.model = primary.model
        self.prompt_version = f"{primary.prompt_version}+{vision.prompt_version}"
        self._reads_images = reads_images
        self._can_read: bool | None = None

    async def _vision_ok(self) -> bool:
        if self._reads_images is None:
            return True
        if self._can_read is None:
            self._can_read = await self._reads_images()
        return self._can_read

    async def extract(self, pages: tuple[PageImage, ...]) -> LLMResult[OcrResult]:
        try:
            first = await self.primary.extract(pages)
        except AIError:
            return await self.vision.extract(pages)
        # Une page peut avoir une confiance moyenne élevée tout en contenant un nombre,
        # une date ou un mot important très incertain. Ces passages doivent aussi déclencher
        # la relecture vision, avant de demander à l’enfant de vérifier manuellement.
        weak = [p.index for p in first.output.pages if p.quality != "good" or p.uncertain]
        if not weak:
            return first
        if not await self._vision_ok():
            return _noted(first, "L'IA choisie ne lit pas les images : la lecture de Tesseract est gardée.")
        try:
            second = await self.vision.extract(tuple(pages[i] for i in weak))
        except AIError:
            return _noted(first, "Relecture par l'IA impossible : la lecture de Tesseract est gardée.")
        merged = list(first.output.pages)
        reread = min(len(second.output.pages), len(weak))
        for k, index in enumerate(weak[:reread]):
            again = second.output.pages[k].model_copy(update={"index": index})
            if _page_quality_key(again) > _page_quality_key(merged[index]):
                merged[index] = again
        warnings = [
            *first.output.warnings,
            f"{reread}/{len(weak)} page(s) relue(s) par l'IA après Tesseract.",
        ]
        if reread < len(weak):
            warnings.append(
                f"Relecture incomplète : {len(weak) - reread} page(s) sans réponse de l'IA ; "
                "la lecture Tesseract est conservée."
            )
        warnings.extend(second.output.warnings)
        output = OcrResult(
            pages=merged,
            language=first.output.language,
            warnings=warnings,
        )
        usage = replace(second.usage, latency_ms=first.usage.latency_ms + second.usage.latency_ms)
        return LLMResult(output, usage)


def _page_quality_key(page: OcrPage) -> tuple[int, int, int]:
    """Compare les relectures sans remplacer une page par une transcription moins sûre.

    À qualité égale, moins de passages douteux est préférable ; le texte non vide départage
    enfin une page vide. La longueur seule n’est jamais considérée comme une preuve de qualité.
    """
    return (_RANK[page.quality], -len(page.uncertain), int(bool(page.text.strip())))


def _noted(result: LLMResult[OcrResult], warning: str) -> LLMResult[OcrResult]:
    output = result.output.model_copy(update={"warnings": [*result.output.warnings, warning]})
    return LLMResult(output, result.usage)
