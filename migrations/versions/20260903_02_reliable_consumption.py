"""Consumo confiável no servidor e detecção de fluxo contínuo."""

from alembic import op
import sqlalchemy as sa

revision = "20260903_02"
down_revision = "20260821_01"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("devices") as batch:
        batch.add_column(sa.Column("last_reported_total", sa.Float(), nullable=True))
        batch.add_column(
            sa.Column(
                "calculated_consumption",
                sa.Float(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column("continuous_flow_since", sa.DateTime(), nullable=True)
        )

    with op.batch_alter_table("leituras") as batch:
        batch.add_column(
            sa.Column("volume_delta", sa.Float(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("calculated_consumption", sa.Float(), nullable=True))

    # Mantém o total que já aparecia no painel como ponto inicial da nova conta.
    op.execute(
        sa.text(
            "UPDATE leituras SET calculated_consumption = consumo_total "
            "WHERE calculated_consumption IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE devices SET "
            "last_reported_total = ("
            "  SELECT l.consumo_total FROM leituras l "
            "  WHERE l.device_id = devices.id "
            "  ORDER BY l.timestamp DESC, l.id DESC LIMIT 1"
            "), calculated_consumption = COALESCE(("
            "  SELECT l.consumo_total FROM leituras l "
            "  WHERE l.device_id = devices.id "
            "  ORDER BY l.timestamp DESC, l.id DESC LIMIT 1"
            "), 0)"
        )
    )


def downgrade():
    with op.batch_alter_table("leituras") as batch:
        batch.drop_column("calculated_consumption")
        batch.drop_column("volume_delta")

    with op.batch_alter_table("devices") as batch:
        batch.drop_column("continuous_flow_since")
        batch.drop_column("calculated_consumption")
        batch.drop_column("last_reported_total")
