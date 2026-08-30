"""Keep CORS headers on *unhandled* 500s.

Starlette builds its middleware stack with ``ServerErrorMiddleware`` as the very
outermost layer (see ``Starlette.build_middleware_stack``), which sits *outside*
any user middleware — including :class:`~starlette.middleware.cors.CORSMiddleware`.
So when a route raises an exception that nothing catches, the 500 response is
produced above the CORS layer and never gets an ``Access-Control-Allow-Origin``
header. The browser then reports a misleading *"No 'Access-Control-Allow-Origin'
header is present"* / ``net::ERR_FAILED`` CORS error that completely hides the
real server-side failure (this is what surfaced on ``POST /diagnosis/submit``).

This middleware runs as the outermost *user* middleware: it catches anything the
inner app lets escape, forwards it to Sentry (the SDK's own outer layer would
otherwise miss a swallowed exception), and returns a plain ``500`` JSON body
*with* the same CORS headers ``CORSMiddleware`` would have added for an allowed
Origin. HTTPExceptions and normal responses are untouched — those already flow
back through ``CORSMiddleware`` correctly.
"""

from __future__ import annotations

import logging

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.core.sentry import capture_to_sentry

logger = logging.getLogger(__name__)


class CorsErrorSafetyMiddleware:
    """Ensure a 500 raised above ``CORSMiddleware`` still carries CORS headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._allowed = set(settings.cors_origins_list)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:  # noqa: BLE001 - deliberately broad safety net
            capture_to_sentry(exc)
            logger.exception("unhandled_exception path=%s", scope.get("path"))
            if response_started:
                # Headers are already on the wire; nothing we can safely do.
                raise
            origin = Headers(scope=scope).get("origin")
            cors_headers: dict[str, str] = {}
            if origin and origin in self._allowed:
                cors_headers = {
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                    "Vary": "Origin",
                }
            response = JSONResponse(
                {"detail": "Internal Server Error"},
                status_code=500,
                headers=cors_headers,
            )
            await response(scope, receive, send)
