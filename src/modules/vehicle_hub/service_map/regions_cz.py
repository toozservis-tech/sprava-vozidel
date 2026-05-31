"""Bbox kraje ČR pro dávkový OSM import (approximativní)."""
from __future__ import annotations

# south, west, north, east (WGS84)
CZ_REGION_BBOXES: dict[str, dict[str, float | str]] = {
    "praha": {"label": "Hlavní město Praha", "south": 49.94, "west": 14.22, "north": 50.18, "east": 14.71},
    "stredocesky": {"label": "Středočeský kraj", "south": 49.52, "west": 13.40, "north": 50.48, "east": 15.38},
    "jihocesky": {"label": "Jihočeský kraj", "south": 48.52, "west": 13.55, "north": 49.65, "east": 15.58},
    "plzensky": {"label": "Plzeňský kraj", "south": 48.94, "west": 12.72, "north": 50.08, "east": 13.95},
    "karlovarsky": {"label": "Karlovarský kraj", "south": 49.92, "west": 12.10, "north": 50.35, "east": 13.15},
    "ustecky": {"label": "Ústecký kraj", "south": 50.05, "west": 12.75, "north": 50.85, "east": 14.35},
    "liberecky": {"label": "Liberecký kraj", "south": 50.45, "west": 14.45, "north": 51.05, "east": 15.58},
    "kralovehradecky": {"label": "Královéhradecký kraj", "south": 50.05, "west": 15.05, "north": 50.78, "east": 16.35},
    "pardubicky": {"label": "Pardubický kraj", "south": 49.55, "west": 15.05, "north": 50.18, "east": 16.85},
    "svitavy_test": {"label": "Test Svitavy", "south": 49.72, "west": 16.35, "north": 49.82, "east": 16.55},
    "vysocina": {"label": "Kraj Vysočina", "south": 48.93, "west": 14.85, "north": 49.88, "east": 16.42},
    "jihomoravsky": {"label": "Jihomoravský kraj", "south": 48.75, "west": 15.58, "north": 49.65, "east": 17.18},
    "olomoucky": {"label": "Olomoucký kraj", "south": 49.38, "west": 16.55, "north": 50.45, "east": 18.05},
    "moravskoslezsky": {"label": "Moravskoslezský kraj", "south": 49.38, "west": 17.15, "north": 50.35, "east": 18.85},
    "zlinsky": {"label": "Zlínský kraj", "south": 48.85, "west": 17.05, "north": 49.58, "east": 18.35},
}

CZ_FULL_BBOX = {"south": 48.55, "west": 12.08, "north": 51.08, "east": 18.88}

OVERPASS_TAG_LINES = [
    'nwr["shop"="car_repair"]',
    'nwr["shop"="tyres"]',
    'nwr["craft"="mechanic"]',
    'nwr["amenity"="vehicle_inspection"]',
    'nwr["service:vehicle:inspection"="yes"]',
    'nwr["service:vehicle:tyres"="yes"]',
    'nwr["service:vehicle:car_repair"="yes"]',
    'nwr["service:vehicle:hgv"="yes"]',
    'nwr["service:vehicle:body_repair"="yes"]',
    'nwr["car:repair"="yes"]',
    'nwr["car:tyres"="yes"]',
]

# Doporučené pořadí importu (ne abecední)
IMPORT_ORDER = [
    "svitavy_test",
    "pardubicky",
    "kralovehradecky",
    "vysocina",
    "stredocesky",
    "praha",
    "jihocesky",
    "plzensky",
    "karlovarsky",
    "ustecky",
    "liberecky",
    "olomoucky",
    "zlinsky",
    "jihomoravsky",
    "moravskoslezsky",
]


def build_overpass_query(*, south: float, west: float, north: float, east: float, timeout: int = 180) -> str:
    """Overpass QL s bbox filtrem (south,west,north,east)."""
    bbox = f"{south},{west},{north},{east}"
    t = max(1, int(timeout))
    lines = "\n".join(f"  {tag}({bbox});" for tag in OVERPASS_TAG_LINES)
    return f"""[out:json][timeout:{t}];
(
{lines}
);
out center tags;"""


def build_overpass_test_query(*, timeout: int = 25) -> str:
    return f"""[out:json][timeout:{timeout}];
node(49.75,16.45,49.77,16.50);
out 1;"""


def split_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    *,
    tiles: int = 2,
) -> list[tuple[float, float, float, float]]:
    """Rozdělí bbox na menší dlaždice (tiles x tiles)."""
    tiles = max(1, int(tiles))
    lat_step = (north - south) / tiles
    lng_step = (east - west) / tiles
    result: list[tuple[float, float, float, float]] = []
    for row in range(tiles):
        for col in range(tiles):
            s = south + row * lat_step
            n = south + (row + 1) * lat_step if row < tiles - 1 else north
            w = west + col * lng_step
            e = west + (col + 1) * lng_step if col < tiles - 1 else east
            result.append((s, w, n, e))
    return result


def region_keys() -> list[str]:
    return sorted(CZ_REGION_BBOXES.keys())


def import_region_keys() -> list[str]:
    return [k for k in IMPORT_ORDER if k in CZ_REGION_BBOXES]
