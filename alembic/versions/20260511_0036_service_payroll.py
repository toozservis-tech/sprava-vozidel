"""service payroll module (employees, attendance, payslips, journal, JMHZ)

Revision ID: 20260511_0036
Revises: c55270029137
Create Date: 2026-05-11 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "20260511_0036"
down_revision = "c55270029137"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "payroll_offices" not in tables:
        op.create_table(
            "payroll_offices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("service_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("vs_cssz", sa.String(length=32), nullable=True),
            sa.Column("datovka_id", sa.String(length=64), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_payroll_offices_tenant_id", "payroll_offices", ["tenant_id"])
        op.create_index("ix_payroll_offices_service_id", "payroll_offices", ["service_id"])
        op.create_index("ix_payroll_offices_vs_cssz", "payroll_offices", ["vs_cssz"])
        op.create_index("ix_payroll_offices_is_active", "payroll_offices", ["is_active"])

    tables = set(inspect(bind).get_table_names())
    if "payroll_employees" not in tables:
        op.create_table(
            "payroll_employees",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("service_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("primary_office_id", sa.Integer(), sa.ForeignKey("payroll_offices.id"), nullable=True),
            sa.Column("first_name", sa.String(length=128), nullable=False),
            sa.Column("last_name", sa.String(length=128), nullable=False),
            sa.Column("birth_date", sa.Date(), nullable=False),
            sa.Column("birth_number", sa.String(length=32), nullable=True),
            sa.Column("gender", sa.String(length=16), nullable=True),
            sa.Column("street", sa.String(length=255), nullable=True),
            sa.Column("city", sa.String(length=128), nullable=True),
            sa.Column("postal_code", sa.String(length=16), nullable=True),
            sa.Column("country_code", sa.String(length=8), nullable=True),
            sa.Column("email", sa.String(length=320), nullable=True),
            sa.Column("phone", sa.String(length=64), nullable=True),
            sa.Column("tax_residency_country", sa.String(length=8), nullable=True),
            sa.Column("tax_resident", sa.Boolean(), nullable=True),
            sa.Column("education_level", sa.String(length=64), nullable=True),
            sa.Column("oic", sa.String(length=32), nullable=True),
            sa.Column("oic_assigned_at", sa.Date(), nullable=True),
            sa.Column("health_insurance_code", sa.String(length=16), nullable=True),
            sa.Column("disability_degree", sa.String(length=32), nullable=True),
            sa.Column("disability_from", sa.Date(), nullable=True),
            sa.Column("disability_to", sa.Date(), nullable=True),
            sa.Column("ztp_p", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("pension_type", sa.String(length=64), nullable=True),
            sa.Column("pension_from", sa.Date(), nullable=True),
            sa.Column("foreign_national", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("citizenship_code", sa.String(length=8), nullable=True),
            sa.Column("id_document_type", sa.String(length=64), nullable=True),
            sa.Column("id_document_number", sa.String(length=128), nullable=True),
            sa.Column("id_document_issue_country", sa.String(length=8), nullable=True),
            sa.Column("residence_permit_until", sa.Date(), nullable=True),
            sa.Column("bank_account", sa.String(length=64), nullable=True),
            sa.Column("iban", sa.String(length=64), nullable=True),
            sa.Column("swift", sa.String(length=32), nullable=True),
            sa.Column("contract_hours_per_week", sa.Float(), nullable=True),
            sa.Column("hourly_gross_rate", sa.Float(), nullable=True),
            sa.Column("default_ppv", sa.String(length=16), nullable=False, server_default="hpp"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_payroll_employees_tenant_id", "payroll_employees", ["tenant_id"])
        op.create_index("ix_payroll_employees_service_id", "payroll_employees", ["service_id"])
        op.create_index("ix_payroll_employees_primary_office_id", "payroll_employees", ["primary_office_id"])
        op.create_index("ix_payroll_employees_birth_date", "payroll_employees", ["birth_date"])
        op.create_index("ix_payroll_employees_is_active", "payroll_employees", ["is_active"])

    tables = set(inspect(bind).get_table_names())
    if "payroll_employee_offices" not in tables:
        op.create_table(
            "payroll_employee_offices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("employee_id", sa.Integer(), sa.ForeignKey("payroll_employees.id"), nullable=False),
            sa.Column("office_id", sa.Integer(), sa.ForeignKey("payroll_offices.id"), nullable=False),
            sa.UniqueConstraint("employee_id", "office_id", name="uq_payroll_employee_office"),
        )
        op.create_index("ix_payroll_employee_offices_tenant_id", "payroll_employee_offices", ["tenant_id"])
        op.create_index("ix_payroll_employee_offices_employee_id", "payroll_employee_offices", ["employee_id"])
        op.create_index("ix_payroll_employee_offices_office_id", "payroll_employee_offices", ["office_id"])

    tables = set(inspect(bind).get_table_names())
    if "payroll_attendance" not in tables:
        op.create_table(
            "payroll_attendance",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("service_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("employee_id", sa.Integer(), sa.ForeignKey("payroll_employees.id"), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("month", sa.Integer(), nullable=False),
            sa.Column("fond_hodin", sa.Float(), nullable=False, server_default="0"),
            sa.Column("odpracovano_hodin", sa.Float(), nullable=False, server_default="0"),
            sa.Column("dovolena_hodin", sa.Float(), nullable=False, server_default="0"),
            sa.Column("nemoc_hodin", sa.Float(), nullable=False, server_default="0"),
            sa.Column("prescas_hodin", sa.Float(), nullable=False, server_default="0"),
            sa.Column("neomluvena_absence_hodin", sa.Float(), nullable=False, server_default="0"),
            sa.Column("pritomnost_hodin", sa.Float(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("employee_id", "year", "month", name="uq_payroll_attendance_period"),
        )
        op.create_index("ix_payroll_attendance_tenant_id", "payroll_attendance", ["tenant_id"])
        op.create_index("ix_payroll_attendance_service_id", "payroll_attendance", ["service_id"])
        op.create_index("ix_payroll_attendance_employee_id", "payroll_attendance", ["employee_id"])
        op.create_index("ix_payroll_attendance_year", "payroll_attendance", ["year"])
        op.create_index("ix_payroll_attendance_month", "payroll_attendance", ["month"])

    tables = set(inspect(bind).get_table_names())
    if "payroll_payslips" not in tables:
        op.create_table(
            "payroll_payslips",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("service_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("employee_id", sa.Integer(), sa.ForeignKey("payroll_employees.id"), nullable=False),
            sa.Column("office_id", sa.Integer(), sa.ForeignKey("payroll_offices.id"), nullable=True),
            sa.Column("attendance_id", sa.Integer(), sa.ForeignKey("payroll_attendance.id"), nullable=True),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("month", sa.Integer(), nullable=False),
            sa.Column("typ_ppv", sa.String(length=16), nullable=False, server_default="hpp"),
            sa.Column("hruba_mzda", sa.Float(), nullable=False, server_default="0"),
            sa.Column("social_employee", sa.Float(), nullable=False, server_default="0"),
            sa.Column("health_employee", sa.Float(), nullable=False, server_default="0"),
            sa.Column("zalohova_dan", sa.Float(), nullable=False, server_default="0"),
            sa.Column("cista_mzda", sa.Float(), nullable=False, server_default="0"),
            sa.Column("k_vyplate", sa.Float(), nullable=False, server_default="0"),
            sa.Column("naklady_zamestnavatele", sa.Float(), nullable=False, server_default="0"),
            sa.Column("stav", sa.String(length=16), nullable=False, server_default="open"),
            sa.Column("datum_uzavreni", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("employee_id", "year", "month", name="uq_payroll_payslip_period"),
        )
        op.create_index("ix_payroll_payslips_tenant_id", "payroll_payslips", ["tenant_id"])
        op.create_index("ix_payroll_payslips_service_id", "payroll_payslips", ["service_id"])
        op.create_index("ix_payroll_payslips_employee_id", "payroll_payslips", ["employee_id"])
        op.create_index("ix_payroll_payslips_office_id", "payroll_payslips", ["office_id"])
        op.create_index("ix_payroll_payslips_attendance_id", "payroll_payslips", ["attendance_id"])
        op.create_index("ix_payroll_payslips_year", "payroll_payslips", ["year"])
        op.create_index("ix_payroll_payslips_month", "payroll_payslips", ["month"])
        op.create_index("ix_payroll_payslips_stav", "payroll_payslips", ["stav"])

    tables = set(inspect(bind).get_table_names())
    if "payroll_journals" not in tables:
        op.create_table(
            "payroll_journals",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("service_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("month", sa.Integer(), nullable=False),
            sa.Column("zamestnancu_pocet", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("stav", sa.String(length=32), nullable=False, server_default="cekani_na_export"),
            sa.Column("payment_order_generated", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("service_id", "year", "month", name="uq_payroll_journal_period"),
        )
        op.create_index("ix_payroll_journals_tenant_id", "payroll_journals", ["tenant_id"])
        op.create_index("ix_payroll_journals_service_id", "payroll_journals", ["service_id"])
        op.create_index("ix_payroll_journals_year", "payroll_journals", ["year"])
        op.create_index("ix_payroll_journals_month", "payroll_journals", ["month"])
        op.create_index("ix_payroll_journals_stav", "payroll_journals", ["stav"])

    tables = set(inspect(bind).get_table_names())
    if "payroll_jmhz_submissions" not in tables:
        op.create_table(
            "payroll_jmhz_submissions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("service_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("office_id", sa.Integer(), sa.ForeignKey("payroll_offices.id"), nullable=False),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("month", sa.Integer(), nullable=False),
            sa.Column("typ", sa.String(length=32), nullable=False, server_default="hlaseni"),
            sa.Column("pocet_zamestnancu", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("zip_file_path", sa.String(length=512), nullable=True),
            sa.Column("odeslano_dne", sa.DateTime(), nullable=True),
            sa.Column("stav", sa.String(length=32), nullable=False, server_default="nove"),
            sa.Column("response_notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_payroll_jmhz_submissions_tenant_id", "payroll_jmhz_submissions", ["tenant_id"])
        op.create_index("ix_payroll_jmhz_submissions_service_id", "payroll_jmhz_submissions", ["service_id"])
        op.create_index("ix_payroll_jmhz_submissions_office_id", "payroll_jmhz_submissions", ["office_id"])
        op.create_index("ix_payroll_jmhz_submissions_year", "payroll_jmhz_submissions", ["year"])
        op.create_index("ix_payroll_jmhz_submissions_month", "payroll_jmhz_submissions", ["month"])
        op.create_index("ix_payroll_jmhz_submissions_stav", "payroll_jmhz_submissions", ["stav"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    for name in (
        "payroll_jmhz_submissions",
        "payroll_journals",
        "payroll_payslips",
        "payroll_attendance",
        "payroll_employee_offices",
        "payroll_employees",
        "payroll_offices",
    ):
        if name in tables:
            op.drop_table(name)
