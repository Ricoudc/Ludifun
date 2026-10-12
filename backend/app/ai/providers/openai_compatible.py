"""Adaptateur des API « compatibles OpenAI » (chat completions) : ChatGPT, Gemini, Mistral, Groq,
Grok (xAI), et tout service qui parle de la même façon (Azure OpenAI, OpenRouter, Ollama…).

Sortie structurée : le schéma JSON attendu est demandé (`response_format` de type
`json_schema`) et rappelé dans les consignes ; si le service refuse ce format, un seul nouvel
essai en simple objet JSON. La réponse est toujours validée par le schéma Pydantic : une sortie
hors schéma est une erreur, comme avec Claude.
"""

import base64
import json
import re
import time
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.ports import AIError, AIInvalidOutput, AIRefused, LLMResult, PageImage, Prompt, Stage, Usage

TIMEOUT_S = 180.0
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


class SchemaFormatRefused(Exception):
    """Le service ne connaît pas `response_format: json_schema`."""


def schema_instructions(schema: type[BaseModel]) -> str:
    return (
        "\n\n# Format de la réponse\n"
        "Réponds uniquement par un objet JSON valide, sans texte autour, conforme à ce schéma JSON :\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )


def parse_json(content: str) -> Any:
    return json.loads(_FENCE.sub("", content.strip()))


class OpenAICompatibleProvider:
    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        models: Mapping[Stage, str],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.models = dict(models)
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_S)

    def model_for(self, stage: Stage) -> str:
        return self.models[stage]

    def _messages(
        self, prompt: Prompt, input: str, schema: type[BaseModel], images: tuple[PageImage, ...]
    ) -> Any:
        user: str | list[dict[str, Any]] = input
        if images:
            user = [
                *(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image.media_type};base64,"
                            + base64.standard_b64encode(image.data).decode("ascii")
                        },
                    }
                    for image in images
                ),
                {"type": "text", "text": input},
            ]
        return [
            {"role": "system", "content": prompt.text + schema_instructions(schema)},
            {"role": "user", "content": user},
        ]

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(
                f"{self.base_url}/chat/completions", json=body, headers=self._headers
            )
        except httpx.TimeoutException as exc:
            raise AIError(f"{self.name} n'a pas répondu à temps ({type(exc).__name__})") from exc
        except httpx.HTTPError as exc:
            raise AIError(f"connexion impossible à {self.name} : {type(exc).__name__}") from exc
        if response.status_code >= 400:
            detail = response.text[:300]
            asked_schema = body.get("response_format", {}).get("type") == "json_schema"
            about_format = re.search(r"response_format|json_schema|schema", detail, re.IGNORECASE)
            if response.status_code == 400 and asked_schema and about_format:
                raise SchemaFormatRefused(detail)
            raise AIError(f"API {self.name} {response.status_code} : {detail}")
        data: dict[str, Any] = response.json()
        return data

    async def structured[T: BaseModel](
        self, *, prompt: Prompt, input: str, schema: type[T], images: tuple[PageImage, ...] = ()
    ) -> LLMResult[T]:
        model = self.models[prompt.stage]
        body: dict[str, Any] = {
            "model": model,
            "messages": self._messages(prompt, input, schema, images),
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
            },
        }
        started = time.perf_counter()
        try:
            data = await self._post(body)
        except SchemaFormatRefused:
            data = await self._post(body | {"response_format": {"type": "json_object"}})
        latency_ms = round((time.perf_counter() - started) * 1000)

        try:
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIInvalidOutput("réponse sans message") from exc
        if message.get("refusal"):
            raise AIRefused("le modèle a refusé la demande")
        if choice.get("finish_reason") == "length":
            raise AIInvalidOutput("réponse tronquée (longueur maximale)")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise AIInvalidOutput("réponse vide")
        try:
            output = schema.model_validate(parse_json(content))
        except (ValidationError, json.JSONDecodeError) as exc:
            raise AIInvalidOutput(f"réponse hors schéma : {exc}") from exc
        usage = data.get("usage") or {}
        return LLMResult(
            output,
            Usage(
                provider=self.name,
                model=str(data.get("model") or model),
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                latency_ms=latency_ms,
            ),
        )
