"""Taille maximale d'une requête (§16.1 : des tailles maximales partout).

Avec un en-tête Content-Length (cas de l'application), le refus est immédiat. Sans (envoi par
morceaux), le corps est lu en comptant, dans la limite du plafond, puis rejoué à l'application.
"""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

TOO_LARGE = json.dumps({"error": {"code": "request_too_large", "message": "Envoi trop volumineux."}}).encode()


class BodySizeLimit:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit():
            if int(declared) > self.max_bytes:
                await self._reject(send)
            else:
                await self.app(scope, receive, send)
            return

        # Corps de taille inconnue : lu ici, au plus `max_bytes`.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":  # déconnexion du client
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                await self._reject(send)
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(TOO_LARGE)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": TOO_LARGE})
