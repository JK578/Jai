"""Bound request memory and authenticated request rates for the local API."""

import time
from collections import defaultdict, deque
from threading import Lock

from starlette.responses import JSONResponse


class RequestRate:
    def __init__(self, limit=120):
        self.limit = limit
        self.entries = defaultdict(deque)
        self.lock = Lock()

    def allowed(self, user_id):
        now = time.monotonic()
        with self.lock:
            queue = self.entries[user_id]
            while queue and queue[0] < now - 60:
                queue.popleft()
            if len(queue) >= self.limit:
                return False
            queue.append(now)
            return True


class BodyLimit:
    def __init__(self, app, limit=65536):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        body = bytearray()
        chunks = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunks += 1
            body.extend(message.get("body", b""))
            if len(body) > self.limit or chunks > 128:
                return await JSONResponse({"detail": "Request too large"}, status_code=413)(
                    scope, receive, send
                )
            if not message.get("more_body"):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)
