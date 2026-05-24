"""Vehicle technical overview JSON (structured VIN/MDČR snapshot).

Revision ID: 20260428_0026
Revises: 20260428_0025
Create Date: 2026-04-28 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260428_0026"
down_revision = "20260428_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vehicles",
        sa.Column("vehicle_technical_overview", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vehicles", "vehicle_technical_overview")
