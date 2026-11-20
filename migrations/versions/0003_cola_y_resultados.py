"""Results and job queue: versiones, vueltas, trabajos, llamadas

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

AHORA = sa.text("now()")


def upgrade() -> None:
    # One agent version: label + commit + the STT/LLM/TTS combination it ran with
    op.create_table(
        "versiones",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("etiqueta", sa.Text, nullable=False),
        sa.Column("git_sha", sa.Text, nullable=False),
        sa.Column("config", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("creada_en", sa.DateTime(timezone=True), nullable=False, server_default=AHORA),
    )
    # One measurement round: a version x a list of scenarios x N attempts
    op.create_table(
        "vueltas",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("nombre", sa.Text, nullable=False, unique=True),
        sa.Column("version_id", sa.Integer, sa.ForeignKey("versiones.id"), nullable=False),
        sa.Column("escenarios", JSONB, nullable=False),
        sa.Column("repeticiones", sa.Integer, nullable=False),
        sa.Column("modalidad", sa.Text, nullable=False, server_default=sa.text("'texto'")),
        sa.Column("creada_en", sa.DateTime(timezone=True), nullable=False, server_default=AHORA),
    )
    # The queue: one job = one scenario file x one attempt number
    op.create_table(
        "trabajos",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("vuelta_id", sa.Integer, sa.ForeignKey("vueltas.id"), nullable=False),
        sa.Column("escenario", sa.Text, nullable=False),
        sa.Column("intento", sa.Integer, nullable=False),
        sa.Column("estado", sa.Text, nullable=False, server_default=sa.text("'pendiente'")),
        sa.Column("intentos", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("disponible_en", sa.DateTime(timezone=True), nullable=False, server_default=AHORA),
        sa.Column("lease_hasta", sa.DateTime(timezone=True)),
        sa.Column("worker", sa.Text),
        sa.Column("error", sa.Text),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=AHORA),
        sa.Column("terminado_en", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "estado IN ('pendiente', 'en_curso', 'hecho', 'fallido')", name="trabajos_estado"
        ),
        sa.UniqueConstraint("vuelta_id", "escenario", "intento"),
    )
    # Partial index: the claim query only looks at jobs that can still run
    op.create_index(
        "trabajos_por_tomar",
        "trabajos",
        ["estado", "disponible_en"],
        postgresql_where=sa.text("estado IN ('pendiente', 'en_curso')"),
    )
    # One scenario result. A retried job leaves one row per execution (`ejecucion`)
    op.create_table(
        "llamadas",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("trabajo_id", sa.Integer, sa.ForeignKey("trabajos.id"), nullable=False),
        sa.Column("vuelta_id", sa.Integer, sa.ForeignKey("vueltas.id"), nullable=False),
        sa.Column("escenario", sa.Text, nullable=False),
        sa.Column("intento", sa.Integer, nullable=False),
        sa.Column("ejecucion", sa.Integer, nullable=False),
        sa.Column("veredicto", sa.Text, nullable=False),
        sa.Column("causa", sa.Text),
        # Judge and deterministic asserts are stored apart, to count where they disagree
        sa.Column("aprobado_juez", sa.Boolean),
        sa.Column("confianza_juez", sa.Float),
        sa.Column("aprobado_asserts", sa.Boolean),
        sa.Column("asserts", JSONB),
        sa.Column("transcripcion", JSONB),
        sa.Column("metricas", JSONB),
        sa.Column("resultado", JSONB, nullable=False),
        sa.Column("duracion_ms", sa.Integer),
        sa.Column("creada_en", sa.DateTime(timezone=True), nullable=False, server_default=AHORA),
        sa.CheckConstraint(
            "veredicto IN ('aprobado', 'suspenso', 'infra')", name="llamadas_veredicto"
        ),
    )
    op.create_index("llamadas_por_vuelta", "llamadas", ["vuelta_id", "escenario"])


def downgrade() -> None:
    op.drop_table("llamadas")
    op.drop_table("trabajos")
    op.drop_table("vueltas")
    op.drop_table("versiones")
