"""OCR par un modèle multimodal utilisé en transcription pure (§5.1)."""

from collections import Counter

from app.ai.ports import LLMProvider, LLMResult, PageImage, Prompt
from app.ai.schemas import OcrPage, OcrResult


class VisionLLMOcr:
    def __init__(self, llm: LLMProvider, prompt: Prompt | None = None) -> None:
        self.llm = llm
        self.prompt = prompt or Prompt.load("ocr")
        self.name = f"vision-llm:{llm.name}"
        self.model = llm.model_for("ocr")
        self.prompt_version = self.prompt.version

    async def extract(self, pages: tuple[PageImage, ...]) -> LLMResult[OcrResult]:
        result = await self.llm.structured(
            prompt=self.prompt,
            input=f"Transcris les {len(pages)} image(s) ci-dessus, dans l'ordre.",
            schema=OcrResult,
            images=pages,
        )
        # Exactement une page par image. Un index dupliqué est ambigu : ne pas choisir
        # arbitrairement une des transcriptions, qui pourrait être attribuée à la mauvaise page.
        counts = Counter(p.index for p in result.output.pages if 0 <= p.index < len(pages))
        by_index = {
            p.index: p for p in result.output.pages if 0 <= p.index < len(pages) and counts[p.index] == 1
        }
        duplicates = sorted(index for index, count in counts.items() if count > 1)
        invalid = sum(1 for p in result.output.pages if not 0 <= p.index < len(pages))
        ordered = [
            by_index.get(i, OcrPage(index=i, quality="unreadable", text="")) for i in range(len(pages))
        ]
        warnings = list(result.output.warnings)
        if duplicates:
            labels = ", ".join(str(index + 1) for index in duplicates)
            warnings.append(
                f"Transcription ambiguë pour la/les page(s) {labels} : plusieurs réponses ; pages à vérifier."
            )
        if invalid:
            warnings.append(f"{invalid} transcription(s) ignorée(s) : numéro de page hors limites.")
        output = result.output.model_copy(update={"pages": ordered, "warnings": warnings})
        return LLMResult(output, result.usage)
