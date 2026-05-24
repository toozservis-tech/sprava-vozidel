"""Static parity checks for user-settings save/toggle slice."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USER_SETTINGS = (ROOT / "web" / "user-settings.js").read_text(encoding="utf-8")


def test_user_settings_faq_items_defined():
    assert "const FAQ_ITEMS" in USER_SETTINGS
    assert "faq:getting-started" in USER_SETTINGS
    assert "faq:account-security" in USER_SETTINGS


def test_user_settings_toggle_keys_present():
    assert "data-uapp-settings-toggle" in USER_SETTINGS
    for key in (
        "notify.master",
        "notify.email",
        "garage.mdcr_auto_update",
        "documents.auto_sort",
        "services.allow_vehicle_access",
        "privacy.third_party",
    ):
        assert key in USER_SETTINGS


def test_user_settings_save_handlers_read_toggle_state():
    assert "function collectToggleState" in USER_SETTINGS
    assert "async function savePrivacyPrefs" in USER_SETTINGS
    assert "async function saveGaragePrefs" in USER_SETTINGS
    assert "marketing: false, third_party: false" not in USER_SETTINGS
    assert "mdcr_auto_update: true }); showMsg('Uloženo.'" not in USER_SETTINGS


def test_user_settings_faq_actions_wired():
    assert "if (action.startsWith('faq:'))" in USER_SETTINGS
    assert "function openFaqItem" in USER_SETTINGS
