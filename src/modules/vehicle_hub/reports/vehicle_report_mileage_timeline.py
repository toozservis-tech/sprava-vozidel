from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from typing import Iterable

from .vehicle_report_models import (
    VehicleReportMileagePoint,
    VehicleReportMileageTimeline,
    VehicleReportServiceRecord,
)

DUPLICATE_MILEAGE_TOLERANCE_KM = 100
SUSPICIOUS_JUMP_SHORT_WINDOW_DAYS = 30
SUSPICIOUS_JUMP_MIN_DELTA_KM = 20000
SUSPICIOUS_JUMP_MIN_DAILY_RATE = 1000


def _is_expected_same_day_inspection_pair(
    previous: VehicleReportMileagePoint,
    current: VehicleReportMileagePoint,
) -> bool:
    if previous.source_type != "stk_history" or current.source_type != "stk_history":
        return False
    previous_label = str(previous.source_label or "").upper()
    current_label = str(current.source_label or "").upper()
    labels = {previous_label, current_label}
    return any("SME" in label for label in labels) and any("STK" in label for label in labels)


def _parse_datetime(raw_value: object) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return raw_value
    text = str(raw_value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _build_service_record_points(
    service_records: Iterable[VehicleReportServiceRecord],
) -> list[tuple[datetime, VehicleReportMileagePoint]]:
    points: list[tuple[datetime, VehicleReportMileagePoint]] = []
    for record in service_records:
        recorded_at = _parse_datetime(record.date)
        mileage_km = record.odometer_km
        if recorded_at is None or mileage_km is None:
            continue
        label = str(record.title or record.category or "Servisni zaznam").strip() or "Servisni zaznam"
        points.append(
            (
                recorded_at,
                VehicleReportMileagePoint(
                    date=recorded_at.isoformat(),
                    mileage_km=int(mileage_km),
                    source_type="service_record",
                    source_label=label,
                    reference=f"service_record:{record.id}",
                ),
            )
        )
    return points


def _build_inspection_points(inspections: Iterable[object]) -> list[tuple[datetime, VehicleReportMileagePoint]]:
    points: list[tuple[datetime, VehicleReportMileagePoint]] = []
    for inspection in inspections:
        recorded_at = _parse_datetime(
            getattr(inspection, "inspection_date", None)
            or getattr(inspection, "check_date", None)
        )
        mileage_km = getattr(inspection, "odometer_km", None) or getattr(inspection, "mileage_km", None)
        if recorded_at is None or mileage_km is None:
            continue
        inspection_type = str(getattr(inspection, "inspection_type", "") or "STK").strip() or "STK"
        inspection_kind = str(getattr(inspection, "inspection_kind", "") or "").strip()
        source = str(getattr(inspection, "source", "") or "kontrolatachometru.cz").strip()
        label = inspection_type if not inspection_kind else f"{inspection_type} / {inspection_kind}"
        points.append(
            (
                recorded_at,
                VehicleReportMileagePoint(
                    date=recorded_at.isoformat(),
                    mileage_km=int(mileage_km),
                    source_type="stk_history",
                    source_label=f"{label} ({source})",
                    reference=f"vehicle_inspection_history:{getattr(inspection, 'id', 'unknown')}",
                ),
            )
        )
    return points


def _mark_duplicate_anomalies(sorted_points: list[tuple[datetime, VehicleReportMileagePoint]]) -> None:
    points_by_day: dict[str, list[tuple[datetime, VehicleReportMileagePoint]]] = defaultdict(list)
    for recorded_at, point in sorted_points:
        points_by_day[recorded_at.date().isoformat()].append((recorded_at, point))

    for day_items in points_by_day.values():
        if len(day_items) < 2:
            continue
        ordered = sorted(day_items, key=lambda item: (item[1].mileage_km, item[1].reference))
        for idx in range(1, len(ordered)):
            previous = ordered[idx - 1][1]
            current = ordered[idx][1]
            if abs(current.mileage_km - previous.mileage_km) > DUPLICATE_MILEAGE_TOLERANCE_KM:
                continue
            if _is_expected_same_day_inspection_pair(previous, current):
                continue
            duplicate_note = (
                f"Temer shodna hodnota km ve stejny den ({current.mileage_km} km vs {previous.mileage_km} km)."
            )
            for point in (previous, current):
                if "duplicate" not in point.anomaly_flags:
                    point.anomaly_flags.append("duplicate")
                if not point.anomaly_note:
                    point.anomaly_note = duplicate_note


def _mark_sequence_anomalies(sorted_points: list[tuple[datetime, VehicleReportMileagePoint]]) -> None:
    for idx in range(1, len(sorted_points)):
        previous_at, previous_point = sorted_points[idx - 1]
        current_at, current_point = sorted_points[idx]
        delta_km = current_point.mileage_km - previous_point.mileage_km
        if delta_km < 0:
            if "rollback" not in current_point.anomaly_flags:
                current_point.anomaly_flags.append("rollback")
            current_point.anomaly_note = (
                f"Novejsi bod ma nizsi stav km nez predchozi zaznam ({current_point.mileage_km} km po {previous_point.mileage_km} km)."
            )
            continue

        delta_days = max((current_at - previous_at).total_seconds() / 86400, 0)
        if delta_days <= 0:
            continue
        daily_rate = delta_km / delta_days
        is_short_window_jump = (
            delta_days <= SUSPICIOUS_JUMP_SHORT_WINDOW_DAYS
            and delta_km >= SUSPICIOUS_JUMP_MIN_DELTA_KM
        )
        is_high_daily_rate = (
            delta_km >= 5000
            and daily_rate >= SUSPICIOUS_JUMP_MIN_DAILY_RATE
        )
        if not (is_short_window_jump or is_high_daily_rate):
            continue
        if "suspicious_jump" not in current_point.anomaly_flags:
            current_point.anomaly_flags.append("suspicious_jump")
        current_point.anomaly_note = (
            f"Podezrely skok o {delta_km:,} km za {delta_days:.1f} dne."
        ).replace(",", " ")


def build_vehicle_report_mileage_timeline(
    *,
    service_records: Iterable[VehicleReportServiceRecord],
    inspections: Iterable[object],
) -> VehicleReportMileageTimeline:
    raw_points = [
        *_build_service_record_points(service_records),
        *_build_inspection_points(inspections),
    ]
    raw_points.sort(
        key=lambda item: (
            item[0],
            item[1].mileage_km,
            item[1].source_type,
            item[1].reference,
        )
    )
    _mark_duplicate_anomalies(raw_points)
    _mark_sequence_anomalies(raw_points)

    serialized_points = [replace(point) for _, point in raw_points]
    first_point = serialized_points[0] if serialized_points else None
    last_point = serialized_points[-1] if serialized_points else None
    anomalies_count = sum(len(point.anomaly_flags) for point in serialized_points)
    return VehicleReportMileageTimeline(
        points=serialized_points,
        first_known_date=first_point.date if first_point else None,
        first_known_mileage_km=first_point.mileage_km if first_point else None,
        last_known_date=last_point.date if last_point else None,
        last_known_mileage_km=last_point.mileage_km if last_point else None,
        anomalies_count=anomalies_count,
    )
