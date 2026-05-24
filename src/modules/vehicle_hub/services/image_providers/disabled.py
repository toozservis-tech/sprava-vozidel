from __future__ import annotations

from .base import VehicleImageProviderAdapter


class DisabledVehicleImageProvider:
    name = "disabled"

    def search(self, query: str, *, limit: int):
        return []


def build_provider() -> VehicleImageProviderAdapter:
    return DisabledVehicleImageProvider()
