"""Tokens for the staff roles (admin, creator, reviewer) and for learners.

Login is two steps: a Keycloak grant returns a refresh_token, which Sunbird's
refresh endpoint exchanges for the access token the APIs accept.
"""
from __future__ import annotations

import asyncio
import random
import time

import httpx

from seeder.config import Settings


RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class TokenError(Exception):
    pass


class Auth:
    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self.s = settings
        self.http = http
        self._tokens: dict[str, tuple[str, float]] = {}  # role -> (token, expiry)
        self._lock = asyncio.Lock()

    @property
    def _token_url(self) -> str:
        kc = self.s.env["keycloak"]
        return f"{kc['url'].rstrip('/')}/realms/{kc['realm']}/protocol/openid-connect/token"

    @property
    def _api_key_header(self) -> dict:
        return {"Authorization": f"Bearer {self.s.secrets['SUNBIRD_API_KEY']}"}

    async def _send(self, method: str, url: str, form: dict) -> httpx.Response:
        """Login request, retried on 429/5xx and transport errors like other API calls."""
        retries = int(self.s.env.get("retries", 4))
        for attempt in range(retries + 1):
            try:
                resp = await self.http.request(method, url, data=form,
                                               headers=self._api_key_header)
                if resp.status_code not in RETRYABLE_STATUS or attempt == retries:
                    return resp
            except httpx.TransportError:
                if attempt == retries:
                    raise
            await asyncio.sleep(min(2 ** attempt, 30) + random.random())
        raise AssertionError("unreachable")

    async def keycloak_grant(self, form: dict) -> dict:
        resp = await self._send("POST", self._token_url, form)
        if resp.status_code != 200:
            raise TokenError(f"token grant failed for {form.get('username')}: "
                             f"{resp.status_code} {resp.text[:300]}")
        return resp.json()

    async def refresh(self, refresh_token: str, fallback_ttl: int) -> tuple[str, int]:
        # Login always goes through the public route, in either mode.
        method, path = self.s.public_endpoint("refresh_token")
        resp = await self._send(method, path, {"refresh_token": refresh_token})
        if resp.status_code != 200:
            raise TokenError(f"refresh token failed: {resp.status_code} {resp.text[:300]}")
        body = resp.json()
        body = body.get("result", body)  # VERIFY: response may or may not wrap in "result"
        return body["access_token"], int(body.get("expires_in", fallback_ttl))

    async def login(self, form: dict) -> tuple[str, int]:
        secret = self.s.secrets.get("KEYCLOAK_CLIENT_SECRET")
        if secret:
            form["client_secret"] = secret
        grant = await self.keycloak_grant(form)
        return await self.refresh(grant["refresh_token"], int(grant.get("expires_in", 300)))

    async def role_token(self, role: str = "admin") -> str:
        async with self._lock:
            cached = self._tokens.get(role)
            if cached and time.time() < cached[1] - 60:
                return cached[0]
            username, password = self.s.role_login(role)
            token, ttl = await self.login({"client_id": self.s.env["keycloak"]["client_id"],
                                           "grant_type": "password",
                                           "username": username, "password": password})
            self._tokens[role] = (token, time.time() + ttl)
            return token

    async def admin_token(self) -> str:
        return await self.role_token("admin")

    def invalidate(self, role: str = "admin") -> None:
        self._tokens.pop(role, None)

    async def user_token(self, username: str) -> tuple[str, int]:
        return await self.login({"client_id": self.s.env["keycloak"]["client_id"],
                                 "grant_type": "password", "username": username,
                                 "password": self.s.secrets["TEST_USER_PASSWORD"]})
