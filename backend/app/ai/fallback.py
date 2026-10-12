"""Repli sur une autre IA (cahier des charges §147) : si l'IA choisie ne répond pas (injoignable,
trop lente, quota épuisé, clé refusée), la suivante de la liste fait le travail.

Une réponse hors format n'est pas une panne : elle n'entraîne pas de repli (le pipeline relance
la même IA). Le résultat dit quelle IA a répondu et pourquoi la précédente a été écartée.
"""

from dataclasses import replace

from pydantic import BaseModel

from app.ai.ports import AIError, AIInvalidOutput, LLMProvider, LLMResult, PageImage, Prompt, Stage


class FallbackLLM:
    def __init__(self, chain: list[LLMProvider]) -> None:
        if not chain:
            raise ValueError("au moins une IA")
        self.chain = chain
        self.name = chain[0].name

    def model_for(self, stage: Stage) -> str:
        return self.chain[0].model_for(stage)

    async def structured[T: BaseModel](
        self, *, prompt: Prompt, input: str, schema: type[T], images: tuple[PageImage, ...] = ()
    ) -> LLMResult[T]:
        failures: list[str] = []
        last: AIError | None = None
        for llm in self.chain:
            try:
                result = await llm.structured(prompt=prompt, input=input, schema=schema, images=images)
            except AIInvalidOutput:
                raise
            except AIError as exc:
                failures.append(f"{llm.name} : {exc}")
                last = exc
                continue
            if failures:
                return LLMResult(result.output, replace(result.usage, fallback_from=" ; ".join(failures)))
            return result
        assert last is not None
        raise type(last)(" ; ".join(failures)) from last
