"""add planning tracking otp consent tables

Revision ID: a1b2c3d4e5f6
Revises: 9e5f6a7b8c9d
Create Date: 2026-10-05 15:38:39.086704
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9e5f6a7b8c9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('consentrecord',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('customer_id', sa.Uuid(), nullable=False),
    sa.Column('purpose', sqlmodel.sql.sqltypes.AutoString(length=40), nullable=False),
    sa.Column('granted', sa.Boolean(), nullable=False),
    sa.Column('lawful_basis', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False),
    sa.Column('recorded_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_consentrecord_customer_id'), 'consentrecord', ['customer_id'], unique=False)
    op.create_index(op.f('ix_consentrecord_tenant_id'), 'consentrecord', ['tenant_id'], unique=False)
    op.create_table('deliveryotp',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('delivery_job_id', sa.Uuid(), nullable=False),
    sa.Column('code_hash', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('expires_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('verified_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['delivery_job_id'], ['deliveryjob.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_deliveryotp_delivery_job_id'), 'deliveryotp', ['delivery_job_id'], unique=False)
    op.create_index(op.f('ix_deliveryotp_tenant_id'), 'deliveryotp', ['tenant_id'], unique=False)
    op.create_table('jobplan',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('delivery_job_id', sa.Uuid(), nullable=False),
    sa.Column('service_zone_id', sa.Uuid(), nullable=True),
    sa.Column('window_start', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
    sa.Column('window_end', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
    sa.Column('plus_code', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['delivery_job_id'], ['deliveryjob.id'], ),
    sa.ForeignKeyConstraint(['service_zone_id'], ['servicezone.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jobplan_delivery_job_id'), 'jobplan', ['delivery_job_id'], unique=True)
    op.create_index(op.f('ix_jobplan_service_zone_id'), 'jobplan', ['service_zone_id'], unique=False)
    op.create_index(op.f('ix_jobplan_tenant_id'), 'jobplan', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_jobplan_window_end'), 'jobplan', ['window_end'], unique=False)
    op.create_index(op.f('ix_jobplan_window_start'), 'jobplan', ['window_start'], unique=False)
    op.create_table('notificationdelivery',
    sa.Column('notification_id', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('body', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('last_error', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.Column('next_attempt_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['notification_id'], ['notification.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
    sa.PrimaryKeyConstraint('notification_id')
    )
    op.create_index(op.f('ix_notificationdelivery_next_attempt_at'), 'notificationdelivery', ['next_attempt_at'], unique=False)
    op.create_index(op.f('ix_notificationdelivery_tenant_id'), 'notificationdelivery', ['tenant_id'], unique=False)
    op.create_table('trackingtoken',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('delivery_job_id', sa.Uuid(), nullable=False),
    sa.Column('token', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('expires_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.Column('revoked', sa.Boolean(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['delivery_job_id'], ['deliveryjob.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trackingtoken_delivery_job_id'), 'trackingtoken', ['delivery_job_id'], unique=False)
    op.create_index(op.f('ix_trackingtoken_tenant_id'), 'trackingtoken', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_trackingtoken_token'), 'trackingtoken', ['token'], unique=True)
    op.create_table('stopcorrection',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('stop_id', sa.Uuid(), nullable=False),
    sa.Column('delivery_job_id', sa.Uuid(), nullable=False),
    sa.Column('source', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
    sa.Column('address_text', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
    sa.Column('landmark', sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
    sa.Column('delivery_notes', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('plus_code', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
    sa.Column('recipient_available', sa.Boolean(), nullable=True),
    sa.Column('location_confidence', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
    sa.Column('reason', sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.ForeignKeyConstraint(['delivery_job_id'], ['deliveryjob.id'], ),
    sa.ForeignKeyConstraint(['stop_id'], ['stop.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_stopcorrection_created_at'), 'stopcorrection', ['created_at'], unique=False)
    op.create_index(op.f('ix_stopcorrection_delivery_job_id'), 'stopcorrection', ['delivery_job_id'], unique=False)
    op.create_index(op.f('ix_stopcorrection_stop_id'), 'stopcorrection', ['stop_id'], unique=False)
    op.create_index(op.f('ix_stopcorrection_tenant_id'), 'stopcorrection', ['tenant_id'], unique=False)
    # Columns the application already uses but earlier migrations never created. Existing rows get a constant
    # default (portable across SQLite/Postgres) which is then backfilled from created_at where one exists.
    epoch = sa.text("'1970-01-01 00:00:00'")
    op.add_column('deliveryjob', sa.Column('updated_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False, server_default=epoch))
    op.execute("UPDATE deliveryjob SET updated_at = created_at")
    op.add_column('driver', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('driver', sa.Column('longitude', sa.Float(), nullable=True))
    op.add_column('driver', sa.Column('last_location_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True))
    op.add_column('driver', sa.Column('updated_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False, server_default=epoch))
    op.execute("UPDATE driver SET updated_at = created_at")
    op.add_column('idempotencyrecord', sa.Column('expires_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False, server_default=epoch))
    op.execute("UPDATE idempotencyrecord SET expires_at = created_at")
    op.create_index(op.f('ix_idempotencyrecord_expires_at'), 'idempotencyrecord', ['expires_at'], unique=False)

    # The audit trail is append-only: enforce it in the database as well as in the ORM.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
            CREATE OR REPLACE FUNCTION auditevent_append_only() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'auditevent rows are append-only';
            END;
            $$ LANGUAGE plpgsql;
        """)
        op.execute("CREATE TRIGGER auditevent_no_update_delete BEFORE UPDATE OR DELETE ON auditevent FOR EACH ROW EXECUTE FUNCTION auditevent_append_only()")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS auditevent_no_update_delete ON auditevent")
        op.execute("DROP FUNCTION IF EXISTS auditevent_append_only()")
    op.drop_index(op.f('ix_idempotencyrecord_expires_at'), table_name='idempotencyrecord')
    op.drop_column('idempotencyrecord', 'expires_at')
    op.drop_column('driver', 'updated_at')
    op.drop_column('driver', 'last_location_at')
    op.drop_column('driver', 'longitude')
    op.drop_column('driver', 'latitude')
    op.drop_column('deliveryjob', 'updated_at')
    op.drop_index(op.f('ix_stopcorrection_tenant_id'), table_name='stopcorrection')
    op.drop_index(op.f('ix_stopcorrection_stop_id'), table_name='stopcorrection')
    op.drop_index(op.f('ix_stopcorrection_delivery_job_id'), table_name='stopcorrection')
    op.drop_index(op.f('ix_stopcorrection_created_at'), table_name='stopcorrection')
    op.drop_table('stopcorrection')
    op.drop_index(op.f('ix_trackingtoken_token'), table_name='trackingtoken')
    op.drop_index(op.f('ix_trackingtoken_tenant_id'), table_name='trackingtoken')
    op.drop_index(op.f('ix_trackingtoken_delivery_job_id'), table_name='trackingtoken')
    op.drop_table('trackingtoken')
    op.drop_index(op.f('ix_notificationdelivery_tenant_id'), table_name='notificationdelivery')
    op.drop_index(op.f('ix_notificationdelivery_next_attempt_at'), table_name='notificationdelivery')
    op.drop_table('notificationdelivery')
    op.drop_index(op.f('ix_jobplan_window_start'), table_name='jobplan')
    op.drop_index(op.f('ix_jobplan_window_end'), table_name='jobplan')
    op.drop_index(op.f('ix_jobplan_tenant_id'), table_name='jobplan')
    op.drop_index(op.f('ix_jobplan_service_zone_id'), table_name='jobplan')
    op.drop_index(op.f('ix_jobplan_delivery_job_id'), table_name='jobplan')
    op.drop_table('jobplan')
    op.drop_index(op.f('ix_deliveryotp_tenant_id'), table_name='deliveryotp')
    op.drop_index(op.f('ix_deliveryotp_delivery_job_id'), table_name='deliveryotp')
    op.drop_table('deliveryotp')
    op.drop_index(op.f('ix_consentrecord_tenant_id'), table_name='consentrecord')
    op.drop_index(op.f('ix_consentrecord_customer_id'), table_name='consentrecord')
    op.drop_table('consentrecord')
