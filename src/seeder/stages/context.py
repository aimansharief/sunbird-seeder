from __future__ import annotations

from dataclasses import dataclass

from seeder.client.http import SunbirdClient
from seeder.config import Settings
from seeder.state.store import Store


@dataclass
class Ctx:
    settings: Settings
    store: Store
    client: SunbirdClient

    @property
    def run_id(self) -> str:
        return self.settings.run_id

    @property
    def vol(self) -> dict:
        return self.settings.volumes

    @property
    def env(self) -> dict:
        return self.settings.env
