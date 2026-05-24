from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class VehicleImageProviderCandidate:
    title: str = ""
    image_url: str = ""
    thumbnail_url: str | None = None
    source_url: str | None = None
    source_domain: str | None = None
    width: int | None = None
    height: int | None = None
    snippet: str | None = None
    provider: str = "unknown"
    raw_payload: dict[str, Any] = field(default_factory=dict)


class VehicleImageProviderAdapter(Protocol):
    name: str

    def search(self, query: str, *, limit: int) -> list[VehicleImageProviderCandidate]:
        ...
