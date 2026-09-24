from app.ai.ocr.vision_llm import VisionLLMOcr
from app.ai.ports import LLMProvider, OcrProvider
from app.ai.providers.claude import ClaudeProvider
from app.ai.providers.fake import FakeProvider
from app.config import Settings


def build_providers(settings: Settings) -> tuple[OcrProvider, LLMProvider]:
    """Fournisseurs configurés : l'OCR V1 utilise le même modèle multimodal (§5.1)."""
    llm: LLMProvider
    if settings.ai_provider == "fake":
        llm = FakeProvider()
    else:
        llm = ClaudeProvider(
            models={
                "ocr": settings.ai_ocr_model,
                "analysis": settings.ai_analysis_model,
                "material": settings.ai_material_model,
                "evaluation": settings.ai_evaluation_model,
            },
            efforts={
                "ocr": settings.ai_ocr_effort,
                "analysis": settings.ai_analysis_effort,
                "material": settings.ai_material_effort,
                "evaluation": settings.ai_evaluation_effort,
            },
        )
    return VisionLLMOcr(llm), llm
