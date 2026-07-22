"""Add run lifecycle fields

Revision ID: 8c0d4c8f0a2b
Revises: 0722637644cc
Create Date: 2026-07-21 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8c0d4c8f0a2b"
down_revision: Union[str, Sequence[str], None] = "0722637644cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    dialect_name = op.get_bind().dialect.name
    op.add_column(
        "order_runs",
        sa.Column("sleep_state", sa.String(), nullable=False, server_default="awake"),
    )
    op.add_column("order_runs", sa.Column("next_wake_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("order_runs", sa.Column("final_summary", sa.String(), nullable=True))
    op.add_column("order_runs", sa.Column("final_learnings", sa.String(), nullable=True))
    op.add_column("order_runs", sa.Column("final_recommendations", sa.String(), nullable=True))
    if dialect_name != "sqlite":
        op.alter_column("order_runs", "sleep_state", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("order_runs", "final_recommendations")
    op.drop_column("order_runs", "final_learnings")
    op.drop_column("order_runs", "final_summary")
    op.drop_column("order_runs", "next_wake_at")
    op.drop_column("order_runs", "sleep_state")
