"""fakturyweb_test_integration

Revision ID: 20260506_0034
Revises: 20260505_0033
Create Date: 2026-05-06 10:40:48.912092
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260506_0034'
down_revision = '20260505_0033'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # service_fakturyweb_settings
    op.create_table('service_fakturyweb_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('service_workspace_id', sa.Integer(), nullable=True),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('encrypted_api_key', sa.Text(), nullable=False),
    sa.Column('api_key_mask', sa.String(length=64), nullable=True),
    sa.Column('supplier_mode', sa.String(length=32), nullable=False),
    sa.Column('d_id', sa.String(length=64), nullable=True),
    sa.Column('default_due_days', sa.Integer(), nullable=False),
    sa.Column('default_payment', sa.String(length=32), nullable=False),
    sa.Column('default_currency', sa.String(length=16), nullable=False),
    sa.Column('default_style', sa.String(length=32), nullable=False),
    sa.Column('default_qr', sa.Integer(), nullable=False),
    sa.Column('test_mode_default', sa.Boolean(), nullable=False),
    sa.Column('last_test_at', sa.DateTime(), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['service_workspace_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'service_workspace_id', name='uq_service_fakturyweb_settings_tenant_workspace')
    )
    op.create_index(op.f('ix_service_fakturyweb_settings_id'), 'service_fakturyweb_settings', ['id'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_settings_service_workspace_id'), 'service_fakturyweb_settings', ['service_workspace_id'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_settings_tenant_id'), 'service_fakturyweb_settings', ['tenant_id'], unique=False)

    # service_fakturyweb_invoices
    op.create_table('service_fakturyweb_invoices',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('service_workspace_id', sa.Integer(), nullable=True),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('fakturyweb_code', sa.String(length=128), nullable=False),
    sa.Column('fakturyweb_number', sa.String(length=64), nullable=True),
    sa.Column('test_mode', sa.Boolean(), nullable=False),
    sa.Column('customer_name', sa.String(length=512), nullable=True),
    sa.Column('customer_email', sa.String(length=320), nullable=True),
    sa.Column('issue_date', sa.Date(), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('amount_estimated', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('local_status', sa.String(length=32), nullable=False),
    sa.Column('remote_status_raw', sa.Text(), nullable=True),
    sa.Column('pdf_url', sa.Text(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['service_workspace_id'], ['customers.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_service_fakturyweb_invoices_created_at'), 'service_fakturyweb_invoices', ['created_at'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_invoices_created_by_user_id'), 'service_fakturyweb_invoices', ['created_by_user_id'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_invoices_fakturyweb_code'), 'service_fakturyweb_invoices', ['fakturyweb_code'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_invoices_fakturyweb_number'), 'service_fakturyweb_invoices', ['fakturyweb_number'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_invoices_id'), 'service_fakturyweb_invoices', ['id'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_invoices_local_status'), 'service_fakturyweb_invoices', ['local_status'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_invoices_service_workspace_id'), 'service_fakturyweb_invoices', ['service_workspace_id'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_invoices_tenant_id'), 'service_fakturyweb_invoices', ['tenant_id'], unique=False)

    # service_fakturyweb_audit_log
    op.create_table('service_fakturyweb_audit_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('local_invoice_id', sa.Integer(), nullable=True),
    sa.Column('endpoint', sa.String(length=255), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('response_status', sa.String(length=32), nullable=True),
    sa.Column('response_status_id', sa.Integer(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['local_invoice_id'], ['service_fakturyweb_invoices.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['customers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_service_fakturyweb_audit_log_action'), 'service_fakturyweb_audit_log', ['action'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_audit_log_created_at'), 'service_fakturyweb_audit_log', ['created_at'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_audit_log_id'), 'service_fakturyweb_audit_log', ['id'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_audit_log_local_invoice_id'), 'service_fakturyweb_audit_log', ['local_invoice_id'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_audit_log_request_hash'), 'service_fakturyweb_audit_log', ['request_hash'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_audit_log_tenant_id'), 'service_fakturyweb_audit_log', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_service_fakturyweb_audit_log_user_id'), 'service_fakturyweb_audit_log', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_service_fakturyweb_audit_log_user_id'), table_name='service_fakturyweb_audit_log')
    op.drop_index(op.f('ix_service_fakturyweb_audit_log_tenant_id'), table_name='service_fakturyweb_audit_log')
    op.drop_index(op.f('ix_service_fakturyweb_audit_log_request_hash'), table_name='service_fakturyweb_audit_log')
    op.drop_index(op.f('ix_service_fakturyweb_audit_log_local_invoice_id'), table_name='service_fakturyweb_audit_log')
    op.drop_index(op.f('ix_service_fakturyweb_audit_log_id'), table_name='service_fakturyweb_audit_log')
    op.drop_index(op.f('ix_service_fakturyweb_audit_log_created_at'), table_name='service_fakturyweb_audit_log')
    op.drop_index(op.f('ix_service_fakturyweb_audit_log_action'), table_name='service_fakturyweb_audit_log')
    op.drop_table('service_fakturyweb_audit_log')
    
    op.drop_index(op.f('ix_service_fakturyweb_invoices_tenant_id'), table_name='service_fakturyweb_invoices')
    op.drop_index(op.f('ix_service_fakturyweb_invoices_service_workspace_id'), table_name='service_fakturyweb_invoices')
    op.drop_index(op.f('ix_service_fakturyweb_invoices_local_status'), table_name='service_fakturyweb_invoices')
    op.drop_index(op.f('ix_service_fakturyweb_invoices_id'), table_name='service_fakturyweb_invoices')
    op.drop_index(op.f('ix_service_fakturyweb_invoices_fakturyweb_number'), table_name='service_fakturyweb_invoices')
    op.drop_index(op.f('ix_service_fakturyweb_invoices_fakturyweb_code'), table_name='service_fakturyweb_invoices')
    op.drop_index(op.f('ix_service_fakturyweb_invoices_created_by_user_id'), table_name='service_fakturyweb_invoices')
    op.drop_index(op.f('ix_service_fakturyweb_invoices_created_at'), table_name='service_fakturyweb_invoices')
    op.drop_table('service_fakturyweb_invoices')
    
    op.drop_index(op.f('ix_service_fakturyweb_settings_tenant_id'), table_name='service_fakturyweb_settings')
    op.drop_index(op.f('ix_service_fakturyweb_settings_service_workspace_id'), table_name='service_fakturyweb_settings')
    op.drop_index(op.f('ix_service_fakturyweb_settings_id'), table_name='service_fakturyweb_settings')
    op.drop_table('service_fakturyweb_settings')
