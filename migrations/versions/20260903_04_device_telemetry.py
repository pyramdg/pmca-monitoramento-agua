"""Telemetria operacional enviada pelo ESP32."""

from alembic import op
import sqlalchemy as sa

revision = "20260903_04"
down_revision = "20260903_03"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("devices") as batch:
        batch.add_column(sa.Column("firmware_version", sa.String(32), nullable=True))
        batch.add_column(sa.Column("wifi_rssi", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("pending_queue", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("devices") as batch:
        batch.drop_column("pending_queue")
        batch.drop_column("wifi_rssi")
        batch.drop_column("firmware_version")
