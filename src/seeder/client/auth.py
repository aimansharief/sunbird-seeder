"""Tokens for the admin and for learners.

Login is two steps: a Keycloak grant returns a refresh_token, which Sunbird's
refresh endpoint exchanges for the access token the APIs accept.
"""
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

    @property
    def _api_key_header(self) -> dict:
        return {"Authorization": f"Bearer {self.s.secrets['SUNBIRD_API_KEY']}"}

    async def keycloak_grant(self, form: dict) -> dict:
        resp = await self.http.post(self._token_url, data=form, headers=self._api_key_header)
        if resp.status_code != 200:
            raise TokenError(f"token grant failed for {form.get('username')}: "
                             f"{resp.status_code} {resp.text[:300]}")
        return resp.json()

    async def refresh(self, refresh_token: str, fallback_ttl: int) -> tuple[str, int]:
        # Login always goes through the public route, in either mode.
        method, path = self.s.public_endpoint("refresh_token")
        resp = await self.http.request(method, path, data={"refresh_token": refresh_token},
                                       headers=self._api_key_header)
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

    async def admin_token(self) -> str:
        async with self._lock:
            if self._admin_token and time.time() < self._admin_expiry - 60:
                return self._admin_token
            kc = self.s.env["keycloak"]
            form = {"client_id": kc["admin_client_id"],
                    "grant_type": kc.get("admin_grant_type", "password"),
                    "username": self.s.secrets["ADMIN_USERNAME"],
                    "password": self.s.secrets["ADMIN_PASSWORD"]}
            token, ttl = await self.login(form)
            self._admin_token, self._admin_expiry = token, time.time() + ttl
            return token

    def invalidate_admin(self) -> None:
        self._admin_token = None

    async def user_token(self, username: str) -> tuple[str, int]:
        return await self.login({"client_id": self.s.env["keycloak"]["user_client_id"],
                                 "grant_type": "password", "username": username,
                                 "password": self.s.secrets["TEST_USER_PASSWORD"]})
