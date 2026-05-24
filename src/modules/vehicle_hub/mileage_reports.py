from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time
from io import BytesIO
from typing import Any, Iterable

from sqlalchemy.orm import Session

from .models import (
    ServiceIntake,
    ServiceRecord as ServiceRecordModel,
    VehicleMileage as VehicleMileageModel,
    VehicleTachometerHistoryEntry as VehicleTachometerHistoryEntryModel,
)

try:
    from PIL import Image, ImageDraw, ImageFont

    PILLOW_AVAILABLE = True
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None
    PILLOW_AVAILABLE = False


MANUAL_MILEAGE_DESCRIPTION = "Zápis aktuálního stavu tachometru"
TACHOMETER_IMPORT_DESCRIPTION = "Načteno z kontroly tachometru (MDČR)"
# Stejný den + téměř stejné km = duplicitní evidence (auditní sladění s vehicle_report_mileage_timeline).
DUPLICATE_MILEAGE_TOLERANCE_KM = 100
# Krátké okno: velký absolutní skok; nebo vysoká denní intenzita nájezdu (bez vyhlazování dat).
SUSPICIOUS_JUMP_SHORT_WINDOW_DAYS = 30
SUSPICIOUS_JUMP_MIN_DELTA_KM = 20_000
SUSPICIOUS_JUMP_MIN_DAILY_RATE = 1_000
SUSPICIOUS_JUMP_HIGH_KM_FOR_RATE = 5_000


def _is_expected_same_day_stk_pair(previous: "MileageTimelinePoint", current: "MileageTimelinePoint") -> bool:
    if previous.source_type not in ("stk", "import") or current.source_type not in ("stk", "import"):
        return False
    previous_label = str(previous.source_label or "").upper()
    current_label = str(current.source_label or "").upper()
    labels = {previous_label, current_label}
    return any("SME" in label for label in labels) and any("STK" in label for label in labels)


@dataclass
class MileageTimelinePoint:
    date: datetime
    mileage_km: int
    source_type: str
    source_label: str
    record_id: str
    is_verified: bool
    anomaly: str | None = None
    anomaly_flags: list[str] = field(default_factory=list)


def _normalize_datetime(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    return None


def _normalize_int(value: object | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _point_sort_key(point: MileageTimelinePoint) -> tuple[datetime, int, int, str]:
    source_rank = {"service": 0, "manual": 1, "stk": 2, "import": 2}.get(point.source_type, 9)
    return (point.date, point.mileage_km, source_rank, point.record_id)


def collect_vehicle_mileage_timeline_points(db: Session, vehicle_id: int) -> list[MileageTimelinePoint]:
    points: list[MileageTimelinePoint] = []

    mileage_rows = (
        db.query(VehicleMileageModel)
        .filter(VehicleMileageModel.vehicle_id == vehicle_id)
        .order_by(VehicleMileageModel.created_at.asc(), VehicleMileageModel.id.asc())
        .all()
    )
    _vm_labels = {
        "manual": "Ruční zápis km",
        "stk": "STK / portál tachometru",
        "service": "Servisní zápis km",
        "import": "Import / synchronizace",
    }
    for vm in mileage_rows:
        normalized_date = _normalize_datetime(getattr(vm, "created_at", None))
        normalized_mileage = _normalize_int(getattr(vm, "mileage_km", None))
        if normalized_date is None or normalized_mileage is None:
            continue
        src = str(getattr(vm, "source", "") or "manual").strip().lower()
        if src not in ("manual", "stk", "service", "import"):
            src = "manual"
        points.append(
            MileageTimelinePoint(
                date=normalized_date,
                mileage_km=normalized_mileage,
                source_type=src,
                source_label=_vm_labels.get(src, src),
                record_id=f"vehicle_mileage:{vm.id}",
                is_verified=(src == "stk"),
            )
        )

    service_records = (
        db.query(ServiceRecordModel)
        .filter(
            ServiceRecordModel.vehicle_id == vehicle_id,
            ServiceRecordModel.is_deleted.is_(False),
        )
        .all()
    )
    for record in service_records:
        normalized_date = _normalize_datetime(getattr(record, "performed_at", None))
        normalized_mileage = _normalize_int(getattr(record, "mileage", None))
        if normalized_date is None or normalized_mileage is None:
            continue

        description = str(getattr(record, "description", "") or "").strip()
        if description == TACHOMETER_IMPORT_DESCRIPTION:
            continue

        source_type = "manual" if description == MANUAL_MILEAGE_DESCRIPTION else "service"
        source_label = "Ruční zápis km" if source_type == "manual" else (description or "Servisní záznam")
        points.append(
            MileageTimelinePoint(
                date=normalized_date,
                mileage_km=normalized_mileage,
                source_type=source_type,
                source_label=source_label,
                record_id=f"service:{record.id}",
                is_verified=False,
            )
        )

    intake_rows = (
        db.query(ServiceIntake)
        .filter(ServiceIntake.vehicle_id == vehicle_id)
        .all()
    )
    for intake in intake_rows:
        normalized_date = _normalize_datetime(getattr(intake, "created_at", None))
        normalized_mileage = _normalize_int(getattr(intake, "odometer_km", None))
        if normalized_date is None or normalized_mileage is None:
            continue
        points.append(
            MileageTimelinePoint(
                date=normalized_date,
                mileage_km=normalized_mileage,
                source_type="service",
                source_label="Servisní příjem",
                record_id=f"intake:{intake.id}",
                is_verified=False,
            )
        )

    stk_rows = (
        db.query(VehicleTachometerHistoryEntryModel)
        .filter(VehicleTachometerHistoryEntryModel.vehicle_id == vehicle_id)
        .all()
    )
    for entry in stk_rows:
        normalized_date = _normalize_datetime(
            getattr(entry, "inspection_date", None) or getattr(entry, "check_date", None)
        )
        normalized_mileage = _normalize_int(
            getattr(entry, "odometer_km", None) or getattr(entry, "mileage_km", None)
        )
        if normalized_date is None or normalized_mileage is None:
            continue
        source_label = str(getattr(entry, "inspection_type", "") or "").strip() or "STK / tachometr"
        points.append(
            MileageTimelinePoint(
                date=normalized_date,
                mileage_km=normalized_mileage,
                source_type="stk",
                source_label=source_label,
                record_id=f"stk:{entry.id}",
                is_verified=True,
            )
        )

    points.sort(key=_point_sort_key)
    _apply_mileage_timeline_anomalies(points)
    return points


def _apply_mileage_timeline_anomalies(points: list[MileageTimelinePoint]) -> None:
    """Označí duplicity (stejný den + malý rozdíl km), rollback a podezřelé skoky — bez úpravy hodnot bodů."""
    by_day: dict[date, list[MileageTimelinePoint]] = defaultdict(list)
    for point in points:
        by_day[point.date.date()].append(point)

    for day_points in by_day.values():
        if len(day_points) < 2:
            continue
        ordered = sorted(day_points, key=lambda p: (p.mileage_km, p.record_id))
        for idx in range(1, len(ordered)):
            prev_p = ordered[idx - 1]
            cur_p = ordered[idx]
            if abs(cur_p.mileage_km - prev_p.mileage_km) > DUPLICATE_MILEAGE_TOLERANCE_KM:
                continue
            if _is_expected_same_day_stk_pair(prev_p, cur_p):
                continue
            for p in (prev_p, cur_p):
                if "duplicate" not in p.anomaly_flags:
                    p.anomaly_flags.append("duplicate")

    previous: MileageTimelinePoint | None = None
    for point in points:
        if previous is not None:
            if point.mileage_km < previous.mileage_km:
                if "rollback" not in point.anomaly_flags:
                    point.anomaly_flags.append("rollback")
            else:
                delta_km = point.mileage_km - previous.mileage_km
                delta_days = max((point.date - previous.date).total_seconds() / 86400, 0.0)
                daily_rate = delta_km / delta_days if delta_days > 0 else float("inf")
                is_short_window_jump = (
                    delta_km >= SUSPICIOUS_JUMP_MIN_DELTA_KM
                    and delta_days <= SUSPICIOUS_JUMP_SHORT_WINDOW_DAYS
                )
                is_high_daily_rate = (
                    delta_km >= SUSPICIOUS_JUMP_HIGH_KM_FOR_RATE
                    and daily_rate >= SUSPICIOUS_JUMP_MIN_DAILY_RATE
                )
                if is_short_window_jump or is_high_daily_rate:
                    if "suspicious_jump" not in point.anomaly_flags:
                        point.anomaly_flags.append("suspicious_jump")
        previous = point

    for point in points:
        if not point.anomaly_flags:
            point.anomaly = None
            continue
        unique_flags = []
        for flag in point.anomaly_flags:
            if flag not in unique_flags:
                unique_flags.append(flag)
        point.anomaly_flags = unique_flags
        for preferred in ("rollback", "suspicious_jump", "duplicate"):
            if preferred in unique_flags:
                point.anomaly = preferred
                break


def summarize_mileage_timeline(points: Iterable[MileageTimelinePoint]) -> dict[str, object]:
    items = list(points)
    if not items:
        return {
            "first_point": None,
            "last_point": None,
            "point_count": 0,
            "anomaly_point_count": 0,
            "anomaly_counts": {},
            "first_mileage_km": None,
            "last_mileage_km": None,
            "first_date": None,
            "last_date": None,
        }

    anomaly_counts = Counter()
    anomaly_point_count = 0
    for point in items:
        if point.anomaly_flags:
            anomaly_point_count += 1
            anomaly_counts.update(point.anomaly_flags)

    return {
        "first_point": items[0],
        "last_point": items[-1],
        "point_count": len(items),
        "anomaly_point_count": anomaly_point_count,
        "anomaly_counts": dict(anomaly_counts),
        "first_mileage_km": items[0].mileage_km,
        "last_mileage_km": items[-1].mileage_km,
        "first_date": items[0].date,
        "last_date": items[-1].date,
    }


def mileage_timeline_point_to_dict(point: MileageTimelinePoint) -> dict[str, Any]:
    return {
        "date": point.date.isoformat(),
        "mileage_km": point.mileage_km,
        "source_type": point.source_type,
        "source_label": point.source_label,
        "record_id": point.record_id,
        "is_verified": point.is_verified,
        "anomaly": point.anomaly,
        "anomaly_flags": list(point.anomaly_flags),
    }


def build_mileage_timeline_payload(db: Session, vehicle_id: int) -> dict[str, Any]:
    """
    Auditní JSON: sloučená časová osa (servisní záznamy, příjmy, STK/tachometr), vzestupně podle data.
    """
    points = collect_vehicle_mileage_timeline_points(db, vehicle_id)
    summary = summarize_mileage_timeline(points)
    first_dt = summary.get("first_date")
    last_dt = summary.get("last_date")
    return {
        "mileage_timeline": {
            "points": [mileage_timeline_point_to_dict(p) for p in points],
            "summary": {
                "first_mileage_km": summary.get("first_mileage_km"),
                "last_mileage_km": summary.get("last_mileage_km"),
                "first_date": first_dt.isoformat() if isinstance(first_dt, datetime) else None,
                "last_date": last_dt.isoformat() if isinstance(last_dt, datetime) else None,
                "point_count": summary.get("point_count", 0),
                "anomaly_point_count": summary.get("anomaly_point_count", 0),
                "anomaly_counts": summary.get("anomaly_counts") or {},
            },
        }
    }


def render_mileage_timeline_chart_png(
    points: Iterable[MileageTimelinePoint],
    *,
    width: int = 1200,
    height: int = 680,
) -> bytes:
    if not PILLOW_AVAILABLE:
        raise RuntimeError("Pillow není dostupný pro vykreslení grafu vývoje km.")

    items = list(points)
    if not items:
        raise ValueError("Graf nelze vykreslit bez bodů.")

    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    plot_left = 90
    plot_top = 36
    plot_right = width - 36
    plot_bottom = height - 150
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    draw.rounded_rectangle((plot_left, plot_top, plot_right, plot_bottom), radius=12, outline="#cbd5e1", width=1)

    draw.text((plot_left, plot_top - 22), "Stav km (osa Y)", fill="#0f172a", font=font)
    label_x = plot_left + (plot_width // 2) - 28
    draw.text((label_x, plot_bottom + 36), "Datum (osa X)", fill="#0f172a", font=font)

    timestamps = [point.date.timestamp() for point in items]
    min_ts = min(timestamps)
    max_ts = max(timestamps)
    if min_ts == max_ts:
        max_ts += 86400

    mileages = [point.mileage_km for point in items]
    min_mileage = min(mileages)
    max_mileage = max(mileages)
    if min_mileage == max_mileage:
        padding = max(1000, int(max_mileage * 0.05) or 1000)
        min_mileage -= padding
        max_mileage += padding
    else:
        padding = max(1000, int((max_mileage - min_mileage) * 0.08))
        min_mileage = max(0, min_mileage - padding)
        max_mileage += padding

    def map_x(value: float) -> float:
        return plot_left + ((value - min_ts) / (max_ts - min_ts)) * plot_width

    def map_y(value: int) -> float:
        return plot_bottom - ((value - min_mileage) / (max_mileage - min_mileage)) * plot_height

    for grid_index in range(6):
        y_value = min_mileage + ((max_mileage - min_mileage) / 5) * grid_index
        y = map_y(int(y_value))
        draw.line((plot_left, y, plot_right, y), fill="#e2e8f0", width=1)
        label = f"{int(y_value):,}".replace(",", " ") + " km"
        draw.text((18, y - 7), label, fill="#475569", font=font)

    tick_count = min(max(len(items), 2), 6)
    tick_indices = sorted({round(index * (len(items) - 1) / (tick_count - 1)) for index in range(tick_count)})
    for index in tick_indices:
        point = items[index]
        x = map_x(point.date.timestamp())
        draw.line((x, plot_bottom, x, plot_bottom + 6), fill="#94a3b8", width=1)
        draw.text((x - 22, plot_bottom + 12), point.date.strftime("%d.%m.%y"), fill="#475569", font=font)

    point_positions = [(map_x(point.date.timestamp()), map_y(point.mileage_km)) for point in items]
    for index in range(1, len(point_positions)):
        draw.line((*point_positions[index - 1], *point_positions[index]), fill="#334155", width=3)

    duplicate_offsets: dict[tuple[date, int], list[float]] = {}
    for point in items:
        key = (point.date.date(), point.mileage_km)
        duplicate_offsets.setdefault(key, [])
    for key, group in duplicate_offsets.items():
        size = len([point for point in items if (point.date.date(), point.mileage_km) == key])
        if size == 1:
            duplicate_offsets[key] = [0.0]
        else:
            sequence = [-8.0, 0.0, 8.0, -14.0, 14.0]
            duplicate_offsets[key] = sequence[:size]

    duplicate_cursors: dict[tuple[date, int], int] = defaultdict(int)
    source_colors = {
        "service": "#2563eb",
        "manual": "#d97706",
        "stk": "#059669",
    }

    for point, (base_x, base_y) in zip(items, point_positions):
        key = (point.date.date(), point.mileage_km)
        offset_index = duplicate_cursors[key]
        duplicate_cursors[key] += 1
        offset = duplicate_offsets[key][offset_index]
        x = base_x + offset
        y = base_y
        fill = source_colors.get(point.source_type, "#475569")
        if point.anomaly_flags:
            draw.ellipse((x - 9, y - 9, x + 9, y + 9), outline="#dc2626", width=3)
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=fill, outline="#ffffff", width=1)

    draw.text((plot_left, height - 118), "Legenda", fill="#0f172a", font=font)
    legend_items = [
        ("Servisní záznam", source_colors["service"], False),
        ("Ruční zápis", source_colors["manual"], False),
        ("STK / tachometr", source_colors["stk"], False),
        ("Podezřelý pokles / anomálie", "#dc2626", True),
    ]
    legend_x = plot_left
    legend_y = height - 92
    for label, color, anomaly in legend_items:
        if anomaly:
            draw.ellipse((legend_x, legend_y, legend_x + 16, legend_y + 16), outline=color, width=3)
            draw.ellipse((legend_x + 4, legend_y + 4, legend_x + 12, legend_y + 12), fill="#ffffff", outline="#ffffff", width=1)
        else:
            draw.ellipse((legend_x, legend_y, legend_x + 16, legend_y + 16), fill=color, outline="#ffffff", width=1)
        draw.text((legend_x + 24, legend_y + 2), label, fill="#334155", font=font)
        legend_x += 220

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
