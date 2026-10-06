"""Loads environment config, volumes and secrets."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

SECRET_KEYS = [
    "SUNBIRD_API_KEY",
    "ADMIN_USERNAME",
    "ADMIN_PASSWORD",
    "ADMIN_USER_ID",
    "CONTENT_CREATOR_ID",
    "CONTENT_CREATOR_USERNAME",
    "CONTENT_CREATOR_PASSWORD",
    "CONTENT_REVIEWER_ID",
    "CONTENT_REVIEWER_USERNAME",
    "CONTENT_REVIEWER_PASSWORD",
    "KEYCLOAK_CLIENT_SECRET",
    "TEST_USER_PASSWORD",
]


@dataclass
class Settings:
    env: dict
    volumes: dict
    secrets: dict = field(default_factory=dict)

    @property
    def run_id(self) -> str:
        return self.volumes["run_id"]

    @property
    def output_dir(self) -> Path:
        path = Path(self.env.get("output_root", "output")) / self.run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _role_prefix(self, role: str) -> str | None:
        """.env prefix for a role with its own account, or None to act as the admin."""
        prefix = {"creator": "CONTENT_CREATOR", "reviewer": "CONTENT_REVIEWER"}.get(role)
        return prefix if prefix and self.secrets.get(f"{prefix}_USERNAME") else None

    def role_login(self, role: str) -> tuple[str, str]:
        prefix = self._role_prefix(role)
        if prefix is None:
            return self.secrets["ADMIN_USERNAME"], self.secrets["ADMIN_PASSWORD"]
        return self.secrets[f"{prefix}_USERNAME"], self.secrets[f"{prefix}_PASSWORD"]

    def role_user_id(self, role: str) -> str:
        prefix = self._role_prefix(role)
        if prefix is None:
            return self.secrets["ADMIN_USER_ID"]
        if not self.secrets.get(f"{prefix}_ID"):
            raise ValueError(f"{prefix}_USERNAME is set, so {prefix}_ID is required")
        return self.secrets[f"{prefix}_ID"]

    @property
    def creator_id(self) -> str:
        """createdBy on content, courses and batches."""
        return self.role_user_id("creator")

    @property
    def reviewer_id(self) -> str:
        """lastPublishedBy on content and course publish."""
        return self.role_user_id("reviewer")

    @property
    def mode(self) -> str:
        mode = self.env.get("mode", "public")
        if mode not in ("public", "local"):
            raise ValueError(f"mode must be 'public' or 'local', got {mode!r}")
        return mode

    def endpoint(self, name: str) -> tuple[str, str]:
        """(method, path or URL) for the active mode."""
        if self.mode == "local":
            local = self.env["local"]
            if name not in local["endpoints"]:
                raise KeyError(f"endpoint {name!r} missing from local.endpoints")
            route = local["endpoints"][name]["route"]
            for service, host in local["hosts"].items():
                route = route.replace("{" + service + "}", host.rstrip("/"))
        else:
            route = self.env["endpoints"][name]
        method, path = route.split(None, 1)
        return method.upper(), path.strip()

    def public_endpoint(self, name: str) -> tuple[str, str]:
        method, path = self.env["endpoints"][name].split(None, 1)
        return method.upper(), path.strip()

    def needs_user_token(self, name: str) -> bool:
        """Public calls always send it; local calls only where configured."""
        if self.mode == "public":
            return True
        return bool(self.env["local"]["endpoints"][name].get("user_token", False))


def load_settings(env_path: str = "config/bench.yaml",
                  volumes_path: str = "config/volumes.yaml") -> Settings:
    load_dotenv()
    with open(env_path) as f:
        env = yaml.safe_load(f)
    with open(volumes_path) as f:
        volumes = yaml.safe_load(f)
    secrets = {k: os.environ.get(k, "") for k in SECRET_KEYS}
    return Settings(env=env, volumes=volumes, secrets=secrets)
