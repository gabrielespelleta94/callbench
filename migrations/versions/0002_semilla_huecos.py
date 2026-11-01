"""Seed the clinic's 4 initial slots (slot 3 is already taken)

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Tests reseed with this same data (tests/conftest.py)
HUECOS = [
    ("2026-11-03 09:00+00", "Dr. Lopez", True),
    ("2026-11-03 09:30+00", "Dr. Lopez", True),
    ("2026-11-03 10:00+00", "Dr. Ruiz", False),
    ("2026-11-04 16:00+00", "Dr. Ruiz", True),
]


def upgrade() -> None:
    # Explicit ids 1..4 (OVERRIDING SYSTEM VALUE), then the sequence is advanced
    # so the next slot created gets id 5
    for i, (inicio, medico, libre) in enumerate(HUECOS, start=1):
        op.execute(
            "INSERT INTO huecos (id, inicio, medico, libre) OVERRIDING SYSTEM VALUE "
            f"VALUES ({i}, '{inicio}', '{medico}', {str(libre).lower()})"
        )
    op.execute("SELECT setval(pg_get_serial_sequence('huecos', 'id'), 4)")


def downgrade() -> None:
    op.execute("DELETE FROM huecos WHERE id BETWEEN 1 AND 4")
