"""OCR par un modèle multimodal utilisé en transcription pure (§5.1)."""

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
        # Exactement une page par image, dans l'ordre : une page oubliée est illisible.
        by_index = {p.index: p for p in result.output.pages if 0 <= p.index < len(pages)}
        ordered = [
            by_index.get(i, OcrPage(index=i, quality="unreadable", text="")) for i in range(len(pages))
        ]
        output = result.output.model_copy(update={"pages": ordered})
        return LLMResult(output, result.usage)
