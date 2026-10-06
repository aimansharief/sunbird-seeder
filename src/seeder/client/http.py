"""Shared HTTP client: auth headers, retries with backoff, error reporting."""
from __future__ import annotations

import asyncio
import logging
import random

import httpx

from seeder.client.auth import Auth
from seeder.config import Settings

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ApiError(Exception):
    def __init__(self, endpoint: str, status: int | None, body: str):
        self.endpoint, self.status, self.body = endpoint, status, body
        super().__init__(f"{endpoint} -> {status}: {body[:500]}")


class SunbirdClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.s = settings
        self.http = httpx.AsyncClient(
            base_url=settings.env["base_url"].rstrip("/"),
            timeout=settings.env.get("request_timeout_s", 30),
            transport=transport,
        )
        self.auth = Auth(settings, self.http)
        self.retries = int(settings.env.get("retries", 4))

    async def close(self) -> None:
        await self.http.aclose()

    async def _headers(self, name: str, as_admin: bool, user_token: str | None) -> dict:
        # Local calls go straight to the service, so there is no Kong API key.
        headers = {}
        if self.s.mode == "public":
            headers["Authorization"] = f"Bearer {self.s.secrets['SUNBIRD_API_KEY']}"
        headers.update(self.s.env.get("extra_headers") or {})
        if user_token:
            headers["x-authenticated-user-token"] = user_token
        elif as_admin and self.s.needs_user_token(name):
            headers["x-authenticated-user-token"] = await self.auth.admin_token()
        return headers

    async def call(self, name: str, *, id: str | None = None, json: dict | None = None,
                   files: dict | None = None, params: dict | None = None,
                   as_admin: bool = True, user_token: str | None = None) -> dict:
        method, path = self.s.endpoint(name)
        if "{id}" in path:
            path = path.replace("{id}", str(id))
        last_status, last_body = None, ""
        for attempt in range(self.retries + 1):
            headers = await self._headers(name, as_admin, user_token)
            try:
                resp = await self.http.request(method, path, json=json, files=files,
                                               params=params, headers=headers)
            except httpx.TransportError as exc:
                last_status, last_body = None, f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code < 400:
                    return resp.json() if resp.content else {}
                last_status, last_body = resp.status_code, resp.text
                if resp.status_code == 401 and as_admin and not user_token:
                    self.auth.invalidate_admin()
                elif resp.status_code not in RETRYABLE_STATUS:
                    raise ApiError(name, last_status, last_body)
            if attempt < self.retries:
                delay = min(2 ** attempt, 30) + random.random()
                log.debug("retry %s in %.1fs (%s)", name, delay, last_status)
                await asyncio.sleep(delay)
        raise ApiError(name, last_status, last_body)
