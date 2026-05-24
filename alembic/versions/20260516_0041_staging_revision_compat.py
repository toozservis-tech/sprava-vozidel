"""staging revision compatibility marker

Revision ID: 20260516_0041
Revises: 20260516_0040
"""
from __future__ import annotations


revision = "20260516_0041"
down_revision = "20260516_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The production database was already stamped with this revision during the
    # earlier UI/service audit work. Keep the revision chain resolvable without
    # introducing runtime schema changes.
    return None


def downgrade() -> None:
    return None
