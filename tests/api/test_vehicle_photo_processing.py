from __future__ import annotations

import io

import pytest

from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router


PIL = pytest.importorskip("PIL")
Image = PIL.Image


def test_normalize_vehicle_photo_resizes_and_converts_to_jpeg():
    source = io.BytesIO()
    Image.new("RGBA", (2400, 1800), (120, 130, 140, 255)).save(source, format="PNG")

    normalized_bytes = vehicles_router._normalize_vehicle_photo(source.getvalue())

    assert normalized_bytes

    with Image.open(io.BytesIO(normalized_bytes)) as normalized:
        assert normalized.size == vehicles_router.VEHICLE_PHOTO_TARGET_SIZE
        assert normalized.format == "JPEG"
