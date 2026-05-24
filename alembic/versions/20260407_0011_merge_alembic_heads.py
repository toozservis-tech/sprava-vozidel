"""Merge parallel Alembic heads (20260405_0003 + 20260407_0010).

Revision ID: 20260407_0011
Revises: 20260405_0003, 20260407_0010
Create Date: 2026-04-07 20:00:00.000000
"""
from __future__ import annotations

revision = "20260407_0011"
down_revision = ("20260405_0003", "20260407_0010")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
