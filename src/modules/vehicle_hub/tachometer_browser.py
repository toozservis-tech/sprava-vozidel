from __future__ import annotations

import base64
import logging
import os
import queue
import re
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - import availability differs by env
    PlaywrightError = Exception
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None


TACHOMETER_PORTAL_URL = "https://www.kontrolatachometru.cz/"
TACHOMETER_SESSION_TTL_SECONDS = 10 * 60
_DEFAULT_WAIT_SECONDS = 20
_DEFAULT_WAIT_MS = _DEFAULT_WAIT_SECONDS * 1000
logger = logging.getLogger(__name__)


class TachometerBrowserError(Exception):
    pass


class TachometerBrowserInvalidCaptcha(TachometerBrowserError):
    def __init__(self, captcha_image_data_url: str):
        super().__init__("Špatně opsaný kód z obrázku")
        self.captcha_image_data_url = captcha_image_data_url


class TachometerBrowserSessionExpired(TachometerBrowserError):
    pass


@dataclass
class TachometerBrowserStartResult:
    session_id: str
    captcha_image_data_url: str
    expires_in_seconds: int


@dataclass
class _StoredBrowserSession:
    session_id: str
    vehicle_id: int
    vin: str
    scraper: "TachometerScraper"
    captcha_image_data_url: str
    created_at: float
    expires_at: float


_SESSION_STORE: dict[str, _StoredBrowserSession] = {}
_SESSION_LOCK = threading.Lock()


def _find_playwright_chromium_binary() -> Optional[str]:
    cache_root = Path.home() / ".cache" / "ms-playwright"
    if not cache_root.exists():
        return None
    chromium = sorted(cache_root.glob("chromium-*/chrome-linux64/chrome"))
    if chromium:
        return str(chromium[-1])
    headless_shell = sorted(cache_root.glob("chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))
    if headless_shell:
        return str(headless_shell[-1])
    return None


def _resolve_browser_binary() -> Optional[str]:
    return (
        os.getenv("TACHOMETER_BROWSER_BINARY")
        or os.getenv("CHROME_BINARY")
        or _find_playwright_chromium_binary()
    )


class TachometerScraper:
    def __init__(self) -> None:
        self._playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.vin = ""
        self._commands: "queue.Queue[tuple[str, tuple, dict, queue.Queue]]" = queue.Queue()
        self._worker_ready = threading.Event()
        self._worker_error: Exception | None = None
        self._closed = False
        self._worker = threading.Thread(target=self._worker_main, name="tachometer-browser", daemon=True)
        self._worker.start()
        self._worker_ready.wait(timeout=30)
        if self._worker_error is not None:
            raise self._worker_error
        if not self._worker_ready.is_set():
            raise TachometerBrowserError("Nepodařilo se připravit headless prohlížeč pro čtení STK/SME.")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._call("_shutdown")
        except Exception:
            pass
        if self._worker.is_alive():
            self._worker.join(timeout=5)

    def _worker_main(self) -> None:
        try:
            self._init_browser()
        except Exception as exc:
            self._worker_error = exc
            self._worker_ready.set()
            return
        self._worker_ready.set()
        while True:
            name, args, kwargs, result_queue = self._commands.get()
            if name == "_shutdown":
                try:
                    self._close_browser_resources()
                finally:
                    result_queue.put((True, None))
                    break
            try:
                result = getattr(self, name)(*args, **kwargs)
                result_queue.put((True, result))
            except Exception as exc:
                result_queue.put((False, exc))

    def _call(self, name: str, *args, **kwargs):
        if self._worker_error is not None:
            raise self._worker_error
        if not self._worker.is_alive() and name != "_shutdown":
            raise TachometerBrowserError("Headless relace STK/SME už není aktivní.")
        result_queue: "queue.Queue[tuple[bool, object]]" = queue.Queue(maxsize=1)
        self._commands.put((name, args, kwargs, result_queue))
        ok, payload = result_queue.get(timeout=90)
        if ok:
            return payload
        raise payload

    def _close_browser_resources(self) -> None:
        try:
            if self.page is not None:
                self.page.close()
        except Exception:
            pass
        try:
            if self.context is not None:
                self.context.close()
        except Exception:
            pass
        try:
            if self.browser is not None:
                self.browser.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass

    def _init_browser(self) -> None:
        binary_location = _resolve_browser_binary()
        if sync_playwright is None:
            raise TachometerBrowserError(
                "V prostředí serveru chybí knihovna Playwright pro čtení STK/SME."
            )
        try:
            self._playwright = sync_playwright().start()
            launch_kwargs = {
                "headless": True,
                "args": [
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            }
            if binary_location:
                launch_kwargs["executable_path"] = binary_location
            self.browser = self._playwright.chromium.launch(**launch_kwargs)
            self.context = self.browser.new_context(
                locale="cs-CZ",
                viewport={"width": 1440, "height": 1200},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            self.page = self.context.new_page()
            self.page.set_default_timeout(_DEFAULT_WAIT_MS)
        except Exception as exc:
            self.close()
            raise TachometerBrowserError(
                f"Nepodařilo se spustit headless prohlížeč pro čtení STK/SME: {exc}"
            ) from exc

    def _find_first(self, selectors: list[str]):
        last_exc: Exception | None = None
        if self.page is None:
            raise TachometerBrowserError("Headless stránka není připravená.")
        for selector in selectors:
            try:
                locator = self.page.locator(selector).first
                locator.wait_for(state="visible", timeout=_DEFAULT_WAIT_MS)
                return locator
            except Exception as exc:
                last_exc = exc
        raise TachometerBrowserError(f"Nepodařilo se najít element na portálu: {selectors!r} ({last_exc})")

    def _captcha_image_data_url(self) -> str:
        img = self._find_first(
            [
                "#captcha_IMG",
                ".captchaImg img",
                "img[id*='captcha']",
            ]
        )
        assert self.page is not None
        assert self.context is not None
        try:
            src = (img.get_attribute("src") or "").strip()
            if src.startswith("data:"):
                return src
            data_url = img.evaluate(
                """(node) => {
                    const image = node;
                    const canvas = document.createElement('canvas');
                    const width = image.naturalWidth || image.width || 200;
                    const height = image.naturalHeight || image.height || 80;
                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(image, 0, 0, width, height);
                    return canvas.toDataURL('image/png');
                }"""
            )
            if isinstance(data_url, str) and data_url.startswith("data:image/"):
                return data_url
            if src:
                image_url = urljoin(self.page.url, src)
                response = self.context.request.get(image_url, fail_on_status_code=True)
                body = response.body()
                content_type = response.headers.get("content-type", "image/png").split(";", 1)[0].strip() or "image/png"
                return f"data:{content_type};base64," + base64.b64encode(body).decode("ascii")
        except Exception:
            logger.exception("[TACHOMETER_BROWSER] direct captcha fetch failed, falling back to screenshot")
        png = img.screenshot(type="png")
        return "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    def open_portal(self, vin: str) -> str:
        return self._call("_open_portal", vin)

    def _open_portal(self, vin: str) -> str:
        try:
            assert self.page is not None
            self.page.goto(TACHOMETER_PORTAL_URL, wait_until="domcontentloaded", timeout=_DEFAULT_WAIT_MS)
            self.vin = str(vin or "").strip().upper()
            vin_input = self._find_first(
                [
                    "input[name='VIN']",
                    "#VIN",
                ],
            )
            vin_input.fill(vin)
            return self._captcha_image_data_url()
        except PlaywrightTimeoutError as exc:
            raise TachometerBrowserError("Portál kontrolatachometru.cz neodpověděl včas.") from exc
        except PlaywrightError as exc:
            raise TachometerBrowserError(f"Headless prohlížeč selhal při otevření portálu: {exc}") from exc

    def submit_captcha(self, captcha_code: str) -> str:
        return self._call("_submit_captcha", captcha_code)

    def _submit_captcha(self, captcha_code: str) -> str:
        try:
            assert self.page is not None
            from .tachometer_parser import parse_tachometer_inspections

            captcha_input = self._find_first(
                [
                    "input[name='captcha$TB']",
                    "input[name='captcha']",
                    "input[id*='captcha'][type='text']",
                ],
            )
            captcha_input.fill(captcha_code)

            submit_button = self._find_first(
                [
                    "form[action*='Search'] input[type='submit']",
                    "form[action*='Search'] button[type='submit']",
                    "input[type='submit']",
                    "button[type='submit']",
                ],
            )
            submit_button.click()
            self.page.wait_for_load_state("domcontentloaded", timeout=_DEFAULT_WAIT_MS)
            deadline = time.time() + 60
            last_html = ""
            while time.time() < deadline:
                try:
                    self.page.wait_for_load_state("networkidle", timeout=1500)
                except Exception:
                    pass
                page_html = self.page.content()
                last_html = page_html
                if "Špatně opsaný kód z obrázku" in page_html or "Nesprávný kód" in page_html:
                    raise TachometerBrowserInvalidCaptcha(self._captcha_image_data_url())
                if self.vin:
                    try:
                        parsed = parse_tachometer_inspections(page_html, self.vin)
                    except Exception:
                        parsed = []
                    if parsed:
                        return page_html
                if re.search(r"nebyly\s+nalezeny\s+žádné\s+údaje|nebyly\s+nalezeny\s+zadne\s+udaje", page_html, flags=re.I):
                    return page_html
                time.sleep(1)
            logger.error(
                "[TACHOMETER_BROWSER] submit timeout vin=%s url=%s title=%s snippet=%s",
                self.vin,
                self.page.url,
                self.page.title(),
                " ".join((last_html or "")[:1200].split()),
            )
            raise TachometerBrowserError("Výsledná stránka STK/SME se nenačetla včas.")
        except PlaywrightTimeoutError as exc:
            raise TachometerBrowserError("Výsledná stránka STK/SME se nenačetla včas.") from exc
        except PlaywrightError as exc:
            logger.exception("[TACHOMETER_BROWSER] playwright failure during submit vin=%s", self.vin)
            raise TachometerBrowserError(f"Headless prohlížeč selhal při odeslání CAPTCHA: {exc}") from exc


def _cleanup_expired_sessions() -> None:
    now = time.time()
    expired: list[_StoredBrowserSession] = []
    with _SESSION_LOCK:
        for session_id, item in list(_SESSION_STORE.items()):
            if item.expires_at <= now:
                expired.append(_SESSION_STORE.pop(session_id))
    for item in expired:
        item.scraper.close()


def _parse_data_url(data_url: str) -> tuple[str, bytes]:
    raw = str(data_url or "").strip()
    if not raw.startswith("data:") or "," not in raw:
        raise TachometerBrowserError("Neplatný formát CAPTCHA obrázku.")
    header, payload = raw.split(",", 1)
    mime = header[5:].split(";", 1)[0].strip() or "image/png"
    try:
        blob = base64.b64decode(payload, validate=False)
    except Exception as exc:
        raise TachometerBrowserError("Nepodařilo se dekódovat CAPTCHA obrázek.") from exc
    return mime, blob


def create_browser_session(*, vehicle_id: int, vin: str) -> TachometerBrowserStartResult:
    _cleanup_expired_sessions()
    scraper = TachometerScraper()
    try:
        captcha_data_url = scraper.open_portal(vin)
    except Exception:
        scraper.close()
        raise

    session_id = secrets.token_urlsafe(24)
    now = time.time()
    record = _StoredBrowserSession(
        session_id=session_id,
        vehicle_id=int(vehicle_id),
        vin=str(vin),
        scraper=scraper,
        captcha_image_data_url=captcha_data_url,
        created_at=now,
        expires_at=now + TACHOMETER_SESSION_TTL_SECONDS,
    )
    with _SESSION_LOCK:
        _SESSION_STORE[session_id] = record
    return TachometerBrowserStartResult(
        session_id=session_id,
        captcha_image_data_url=captcha_data_url,
        expires_in_seconds=TACHOMETER_SESSION_TTL_SECONDS,
    )


def _pop_browser_session(session_id: str) -> _StoredBrowserSession | None:
    with _SESSION_LOCK:
        return _SESSION_STORE.pop(session_id, None)


def get_browser_session(session_id: str) -> _StoredBrowserSession:
    _cleanup_expired_sessions()
    with _SESSION_LOCK:
        item = _SESSION_STORE.get(session_id)
    if item is None or item.expires_at <= time.time():
        if item is not None:
            remove_browser_session(session_id)
        raise TachometerBrowserSessionExpired("Relace CAPTCHA vypršela. Načtěte nový obrázek.")
    return item


def remove_browser_session(session_id: str) -> None:
    item = _pop_browser_session(session_id)
    if item is not None:
        item.scraper.close()


def get_browser_session_captcha(*, session_id: str, vehicle_id: int, vin: str | None = None) -> tuple[str, bytes]:
    item = get_browser_session(session_id)
    if int(item.vehicle_id) != int(vehicle_id):
        raise TachometerBrowserError("Relace CAPTCHA patří k jinému vozidlu.")
    if vin is not None and str(item.vin).strip().upper() != str(vin).strip().upper():
        raise TachometerBrowserError("Relace CAPTCHA patří k jinému VIN.")
    return _parse_data_url(item.captcha_image_data_url)


def submit_browser_session(*, session_id: str, vehicle_id: int, vin: str, captcha_code: str) -> str:
    item = get_browser_session(session_id)
    if int(item.vehicle_id) != int(vehicle_id):
        raise TachometerBrowserError("Relace CAPTCHA patří k jinému vozidlu.")
    if str(item.vin).strip().upper() != str(vin).strip().upper():
        raise TachometerBrowserError("Relace CAPTCHA patří k jinému VIN.")
    try:
        html = item.scraper.submit_captcha(captcha_code)
    except TachometerBrowserInvalidCaptcha as exc:
        item.captcha_image_data_url = exc.captcha_image_data_url
        item.expires_at = time.time() + TACHOMETER_SESSION_TTL_SECONDS
        raise
    except Exception:
        remove_browser_session(session_id)
        raise
    remove_browser_session(session_id)
    return html
