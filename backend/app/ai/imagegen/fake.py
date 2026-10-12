"""Moteur factice (tests, démonstration) : une image unie, sans carte graphique."""

import hashlib
import io

from PIL import Image

from app.ai.imagegen.ports import GeneratedImage, ImageRequest


class FakeImageEngine:
    name = "fake"
    model = "fake-image"
    base_url: str | None = None

    def __init__(self) -> None:
        self.requests: list[ImageRequest] = []
        self.released = 0

    async def generate(self, request: ImageRequest) -> GeneratedImage:
        self.requests.append(request)
        colour = hashlib.sha256(request.prompt.encode()).digest()[:3]
        buffer = io.BytesIO()
        Image.new("RGB", (64, 64), (colour[0], colour[1], colour[2])).save(buffer, format="PNG")
        return GeneratedImage(buffer.getvalue(), "image/png", self.name, self.model, 1)

    async def release(self) -> None:
        self.released += 1
