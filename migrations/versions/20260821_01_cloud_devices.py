"""Base de produção, aparelhos e eventos offline idempotentes."""

from alembic import op
import sqlalchemy as sa

revision = "20260821_01"
down_revision = None
branch_labels = None
depends_on = None


def _create_devices():
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("api_key_hash", sa.String(64), nullable=False),
        sa.Column("api_key_expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("api_key_hash"),
    )
    op.create_index("ix_devices_user_id", "devices", ["user_id"])
    op.create_index("ix_devices_api_key_hash", "devices", ["api_key_hash"], unique=True)


def upgrade():
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("password_hash", sa.String(), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("api_key", sa.String(), nullable=True),
            sa.Column("api_key_expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("email"),
            sa.UniqueConstraint("api_key"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if "devices" not in tables:
        _create_devices()

    if "leituras" not in tables:
        op.create_table(
            "leituras",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
            ),
            sa.Column(
                "device_id", sa.Integer(), sa.ForeignKey("devices.id"), nullable=True
            ),
            sa.Column("event_id", sa.String(96), nullable=True),
            sa.Column("fluxo_litros", sa.Float(), nullable=False),
            sa.Column("consumo_total", sa.Float(), nullable=False),
            sa.Column("timestamp", sa.DateTime(), nullable=True),
            sa.Column("received_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("device_id", "event_id", name="uq_device_event"),
        )
        op.create_index("ix_leituras_timestamp", "leituras", ["timestamp"])
        op.create_index("ix_leituras_device_id", "leituras", ["device_id"])
    else:
        columns = {c["name"] for c in sa.inspect(connection).get_columns("leituras")}
        with op.batch_alter_table("leituras") as batch:
            if "device_id" not in columns:
                batch.add_column(sa.Column("device_id", sa.Integer(), nullable=True))
                batch.create_foreign_key(
                    "fk_leituras_device", "devices", ["device_id"], ["id"]
                )
            if "event_id" not in columns:
                batch.add_column(sa.Column("event_id", sa.String(96), nullable=True))
            if "received_at" not in columns:
                batch.add_column(sa.Column("received_at", sa.DateTime(), nullable=True))

        # Preenche dados antigos antes de tornar a coluna obrigatória.
        op.execute(
            sa.text(
                "UPDATE leituras SET received_at = timestamp WHERE received_at IS NULL"
            )
        )
        with op.batch_alter_table("leituras") as batch:
            batch.alter_column(
                "received_at", existing_type=sa.DateTime(), nullable=False
            )
            batch.create_index("ix_leituras_device_id", ["device_id"])
            batch.create_unique_constraint("uq_device_event", ["device_id", "event_id"])


def downgrade():
    with op.batch_alter_table("leituras") as batch:
        batch.drop_constraint("uq_device_event", type_="unique")
        batch.drop_index("ix_leituras_device_id")
        batch.drop_column("received_at")
        batch.drop_column("event_id")
        batch.drop_column("device_id")
    op.drop_table("devices")
