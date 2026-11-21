from starlette.datastructures import Headers
from starlette.responses import JSONResponse


class RequestLimits:
    def __init__(self, app, origin):
        self.app = app
        self.origin = origin

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PATCH"}:
            await self.app(scope, receive, send)
            return
        origin = Headers(scope=scope).get("origin")
        if origin not in (None, self.origin):
            await JSONResponse({"detail": "Origin is not authorized for workspace changes"}, status_code=403)(
                scope, receive, send,
            )
            return
        if scope["path"].endswith("/upload"):
            await self.app(scope, receive, send)
            return
        body = bytearray()
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > 8192:
                await JSONResponse({"detail": "JSON body limit is 8 KiB"}, status_code=413)(scope, receive, send)
                return
            body.extend(chunk)
            more = message.get("more_body", False)
        delivered = False

        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)
