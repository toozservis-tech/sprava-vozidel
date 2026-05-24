from __future__ import annotations

from .base import VehicleImageProviderAdapter, VehicleImageProviderCandidate


class MockVehicleImageProvider:
    name = "mock"

    def search(self, query: str, *, limit: int) -> list[VehicleImageProviderCandidate]:
        normalized = " ".join(str(query or "").split()).strip() or "vehicle"
        items = [
            VehicleImageProviderCandidate(
                title=f"{normalized} official exterior",
                image_url="https://mock.vehicle-images.local/peugeot-boxer-2019-main.jpg",
                thumbnail_url="https://mock.vehicle-images.local/peugeot-boxer-2019-main-thumb.jpg",
                source_url="https://media.peugeot.example/catalog/boxer",
                source_domain="media.peugeot.example",
                width=1280,
                height=720,
                snippet="official exterior white van front three quarter",
                provider=self.name,
                raw_payload={"fixture": "main"},
            ),
            VehicleImageProviderCandidate(
                title=f"{normalized} brochure side view",
                image_url="https://mock.vehicle-images.local/peugeot-boxer-2019-alt-1.jpg",
                thumbnail_url="https://mock.vehicle-images.local/peugeot-boxer-2019-alt-1-thumb.jpg",
                source_url="https://catalog.example/vehicles/boxer",
                source_domain="catalog.example",
                width=1024,
                height=640,
                snippet="grey exterior catalog van",
                provider=self.name,
                raw_payload={"fixture": "alt-1"},
            ),
            VehicleImageProviderCandidate(
                title=f"{normalized} lifestyle interior",
                image_url="https://mock.vehicle-images.local/peugeot-boxer-2019-interior.jpg",
                thumbnail_url="https://mock.vehicle-images.local/peugeot-boxer-2019-interior-thumb.jpg",
                source_url="https://blog.example/vehicle/inside",
                source_domain="blog.example",
                width=900,
                height=600,
                snippet="interior dashboard",
                provider=self.name,
                raw_payload={"fixture": "alt-2"},
            ),
        ]
        return items[: max(int(limit or 0), 0)]


def build_provider() -> VehicleImageProviderAdapter:
    return MockVehicleImageProvider()
