#!/usr/bin/env python3
"""Interactive CLI lookup for latest mileage from kontrolatachometru.cz.

No third-party dependencies.

Usage:
    python3 scripts/kontrolatachometru_cli.py --vin TMBJF73T2B9044629
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE_URL = "https://www.kontrolatachometru.cz"
SEARCH_PATH = "/Home/Search"


@dataclass
class Inspection:
    check_date: Optional[dt.date]
    mileage_km: int
    protocol_number: Optional[str]
    inspection_type: Optional[str]


def normalize_vin(raw: str) -> str:
    vin = (raw or "").strip().upper().replace(" ", "")
    if len(vin) != 17:
        raise ValueError("VIN musí mít přesně 17 znaků.")
    if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin):
        raise ValueError("VIN obsahuje nepovolené znaky.")
    return vin


def extract_hidden_token(page_html: str) -> Optional[str]:
    match = re.search(
        r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"',
        page_html,
        flags=re.I,
    )
    return html.unescape(match.group(1)) if match else None


def extract_captcha_src(page_html: str) -> Optional[str]:
    match = re.search(r'<img[^>]+id="captcha_IMG"[^>]+src="([^"]+)"', page_html, flags=re.I)
    return html.unescape(match.group(1)) if match else None


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]*>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_km(text: str) -> Optional[int]:
    digits = re.sub(r"[^0-9]", "", text or "")
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def parse_cz_date(text: str) -> Optional[dt.date]:
    text = (text or "").strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def extract_td_value(row_html: str, attr: str) -> str:
    pattern = rf'<td[^>]*{attr}[^>]*>(.*?)</td>'
    match = re.search(pattern, row_html, flags=re.I | re.S)
    if not match:
        return ""
    return strip_html(match.group(1))


def parse_inspections(search_html: str) -> List[Inspection]:
    rows = re.findall(r"<tr[^>]*data-row-id[^>]*>(.*?)</tr>", search_html, flags=re.I | re.S)
    results: List[Inspection] = []
    for row in rows:
        km_text = extract_td_value(row, "data-km-staff")
        km = parse_km(km_text)
        if km is None:
            continue
        date_text = extract_td_value(row, "data-finish-date")
        protocol = extract_td_value(row, "data-protocol-number") or None
        typ = extract_td_value(row, "data-inspection-type-name") or None
        results.append(
            Inspection(
                check_date=parse_cz_date(date_text),
                mileage_km=km,
                protocol_number=protocol,
                inspection_type=typ,
            )
        )

    results.sort(key=lambda i: (i.check_date or dt.date.min, i.mileage_km), reverse=True)
    return results


def open_file(path: str) -> None:
    if sys.platform == "darwin":
        os.system(f'open "{path}" >/dev/null 2>&1')


def http_get(opener, url: str, timeout: int, headers: dict[str, str]) -> tuple[bytes, dict[str, str]]:
    req = Request(url, headers=headers, method="GET")
    with opener.open(req, timeout=timeout) as resp:
        body = resp.read()
        resp_headers = {k: v for k, v in resp.headers.items()}
    return body, resp_headers


def http_post_form(opener, url: str, timeout: int, headers: dict[str, str], form: dict[str, str]) -> tuple[bytes, dict[str, str]]:
    data = urlencode(form).encode("utf-8")
    post_headers = dict(headers)
    post_headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = Request(url, data=data, headers=post_headers, method="POST")
    with opener.open(req, timeout=timeout) as resp:
        body = resp.read()
        resp_headers = {k: v for k, v in resp.headers.items()}
    return body, resp_headers


def main() -> int:
    parser = argparse.ArgumentParser(description="Načte poslední km z kontrolatachometru.cz")
    parser.add_argument("--vin", required=True, help="VIN vozidla (17 znaků)")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout v sekundách")
    args = parser.parse_args()

    try:
        vin = normalize_vin(args.vin)
    except ValueError as exc:
        print(f"Chyba: {exc}")
        return 2

    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    common_headers = {
        "User-Agent": "SpravaVozidel-CLI/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        page_bytes, _ = http_get(opener, BASE_URL, args.timeout, common_headers)
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"Chyba připojení na {BASE_URL}: {exc}")
        return 3

    page_html = page_bytes.decode("utf-8", errors="replace")
    token = extract_hidden_token(page_html)
    captcha_src = extract_captcha_src(page_html)
    if not token or not captcha_src:
        print("Nepodařilo se načíst token/captcha ze stránky.")
        return 4

    captcha_url = urljoin(BASE_URL, captcha_src)
    try:
        captcha_bytes, captcha_headers = http_get(opener, captcha_url, args.timeout, common_headers)
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"Nepodařilo se stáhnout captcha obrázek: {exc}")
        return 5

    suffix = ".png"
    content_type = (captcha_headers.get("Content-Type") or "").lower()
    if "jpeg" in content_type:
        suffix = ".jpg"
    elif "gif" in content_type:
        suffix = ".gif"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="tachometer_captcha_") as fh:
        fh.write(captcha_bytes)
        captcha_path = fh.name

    print(f"Captcha uložena: {captcha_path}")
    open_file(captcha_path)
    captcha_code = input("Opište kód z obrázku: ").strip()
    if len(captcha_code) < 2:
        print("Neplatný captcha kód.")
        return 6

    form_data = {
        "__RequestVerificationToken": token,
        "VIN": vin,
        "captcha$TB": captcha_code,
    }

    post_headers = dict(common_headers)
    post_headers["Referer"] = BASE_URL

    try:
        result_bytes, _ = http_post_form(opener, urljoin(BASE_URL, SEARCH_PATH), args.timeout, post_headers, form_data)
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"Chyba při odesílání formuláře: {exc}")
        return 7

    html_text = result_bytes.decode("utf-8", errors="replace")
    if "Špatně opsaný kód z obrázku" in html_text:
        print("Captcha je špatně. Spusť skript znovu.")
        return 8

    inspections = parse_inspections(html_text)
    if not inspections:
        print("Pro zadané VIN nebyly nalezeny žádné údaje STK/emisí.")
        return 9

    latest = inspections[0]
    date_text = latest.check_date.isoformat() if latest.check_date else "neznámé datum"
    print("\n=== POSLEDNÍ STAV TACHOMETRU ===")
    print(f"VIN: {vin}")
    print(f"Datum: {date_text}")
    print(f"Kilometry: {latest.mileage_km} km")
    if latest.inspection_type:
        print(f"Typ: {latest.inspection_type}")
    if latest.protocol_number:
        print(f"Protokol: {latest.protocol_number}")

    print("\nPosledních záznamů:")
    for idx, row in enumerate(inspections[:5], start=1):
        row_date = row.check_date.isoformat() if row.check_date else "?"
        row_type = row.inspection_type or "-"
        print(f"{idx}. {row_date} | {row.mileage_km} km | {row_type}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
