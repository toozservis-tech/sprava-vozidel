"""
Historické beta testy — modely Beta* nejsou součástí aktuálního release schématu.

Soubor zůstává kvůli CI/kolekci; celý modul je přeskočen.
"""
import pytest

pytestmark = pytest.mark.skip(
    reason="Beta program models are not part of current release schema",
    allow_module_level=True,
)


def test_beta_program_archived_placeholder() -> None:
    assert True
