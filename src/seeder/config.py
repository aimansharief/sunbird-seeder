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

    def endpoint(self, name: str) -> tuple[str, str]:
        method, path = self.env["endpoints"][name].split(None, 1)
        return method.upper(), path.strip()


def load_settings(env_path: str = "config/bench.yaml",
                  volumes_path: str = "config/volumes.yaml") -> Settings:
    load_dotenv()
    with open(env_path) as f:
        env = yaml.safe_load(f)
    with open(volumes_path) as f:
        volumes = yaml.safe_load(f)
    secrets = {k: os.environ.get(k, "") for k in SECRET_KEYS}
    return Settings(env=env, volumes=volumes, secrets=secrets)
