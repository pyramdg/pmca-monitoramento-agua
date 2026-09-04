"""Meta mensal e tarifa de água configuráveis por usuário."""

from alembic import op
import sqlalchemy as sa

revision = "20260903_03"
down_revision = "20260903_02"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("monthly_goal_liters", sa.Float(), nullable=True))
        batch.add_column(sa.Column("water_price_per_m3", sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_column("water_price_per_m3")
        batch.drop_column("monthly_goal_liters")
