"""Keycloak password-grant tokens for the admin and for learners."""
from __future__ import annotations

import asyncio
import time

import httpx

from seeder.config import Settings


class TokenError(Exception):
    pass


class Auth:
    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        self.s = settings
        self.http = http
        self._admin_token: str | None = None
        self._admin_expiry = 0.0
        self._lock = asyncio.Lock()

    @property
    def _token_url(self) -> str:
        kc = self.s.env["keycloak"]
        return f"{kc['url'].rstrip('/')}/realms/{kc['realm']}/protocol/openid-connect/token"

    async def password_grant(self, client_id: str, username: str,
                             password: str) -> tuple[str, int]:
        form = {"grant_type": "password", "client_id": client_id,
                "username": username, "password": password}
        secret = self.s.secrets.get("KEYCLOAK_CLIENT_SECRET")
        if secret:
            form["client_secret"] = secret
        resp = await self.http.post(self._token_url, data=form)
        if resp.status_code != 200:
            raise TokenError(f"token grant failed for {username}: "
                             f"{resp.status_code} {resp.text[:300]}")
        body = resp.json()
        return body["access_token"], int(body.get("expires_in", 300))

    async def admin_token(self) -> str:
        async with self._lock:
            if self._admin_token and time.time() < self._admin_expiry - 60:
                return self._admin_token
            token, ttl = await self.password_grant(
                self.s.env["keycloak"]["admin_client_id"],
                self.s.secrets["ADMIN_USERNAME"], self.s.secrets["ADMIN_PASSWORD"])
            self._admin_token, self._admin_expiry = token, time.time() + ttl
            return token

    def invalidate_admin(self) -> None:
        self._admin_token = None

    async def user_token(self, username: str) -> tuple[str, int]:
        return await self.password_grant(
            self.s.env["keycloak"]["user_client_id"], username,
            self.s.secrets["TEST_USER_PASSWORD"])
