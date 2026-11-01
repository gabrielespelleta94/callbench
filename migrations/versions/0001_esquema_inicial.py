"""Create huecos and citas

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "huecos",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("medico", sa.Text, nullable=False),
        sa.Column("libre", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "citas",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        # UNIQUE: the final guarantee against double booking lives in the database, not in the code
        sa.Column("hueco_id", sa.Integer, sa.ForeignKey("huecos.id"), nullable=False, unique=True),
        sa.Column("paciente", sa.Text, nullable=False),
        sa.Column("motivo", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column(
            "creada_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )


def downgrade() -> None:
    op.drop_table("citas")
    op.drop_table("huecos")
