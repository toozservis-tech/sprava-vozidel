"""fakturyweb_custom_header

Revision ID: 20260507_0035
Revises: 20260506_0034
Create Date: 2026-05-07 13:40:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260507_0035'
down_revision = '20260506_0034'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('service_fakturyweb_settings', sa.Column('custom_d_name', sa.String(length=255), nullable=True))
    op.add_column('service_fakturyweb_settings', sa.Column('custom_d_street', sa.String(length=255), nullable=True))
    op.add_column('service_fakturyweb_settings', sa.Column('custom_d_city', sa.String(length=255), nullable=True))
    op.add_column('service_fakturyweb_settings', sa.Column('custom_d_zip', sa.String(length=32), nullable=True))
    op.add_column('service_fakturyweb_settings', sa.Column('custom_d_state', sa.String(length=64), nullable=True))
    op.add_column('service_fakturyweb_settings', sa.Column('custom_d_ico', sa.String(length=32), nullable=True))
    op.add_column('service_fakturyweb_settings', sa.Column('custom_d_dic', sa.String(length=32), nullable=True))
    op.add_column('service_fakturyweb_settings', sa.Column('custom_d_email', sa.String(length=320), nullable=True))
    op.add_column('service_fakturyweb_settings', sa.Column('custom_d_phone', sa.String(length=64), nullable=True))
    op.add_column('service_fakturyweb_settings', sa.Column('custom_d_web', sa.String(length=255), nullable=True))
    op.add_column('service_fakturyweb_settings', sa.Column('custom_d_bankaccount', sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column('service_fakturyweb_settings', 'custom_d_bankaccount')
    op.drop_column('service_fakturyweb_settings', 'custom_d_web')
    op.drop_column('service_fakturyweb_settings', 'custom_d_phone')
    op.drop_column('service_fakturyweb_settings', 'custom_d_email')
    op.drop_column('service_fakturyweb_settings', 'custom_d_dic')
    op.drop_column('service_fakturyweb_settings', 'custom_d_ico')
    op.drop_column('service_fakturyweb_settings', 'custom_d_state')
    op.drop_column('service_fakturyweb_settings', 'custom_d_zip')
    op.drop_column('service_fakturyweb_settings', 'custom_d_city')
    op.drop_column('service_fakturyweb_settings', 'custom_d_street')
    op.drop_column('service_fakturyweb_settings', 'custom_d_name')
