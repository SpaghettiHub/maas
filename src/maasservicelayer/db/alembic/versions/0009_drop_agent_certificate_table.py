"""drop agent certificate table

Revision ID: 0009
Revises: 0008
Create Date: 2025-10-14 08:29:01.137516+00:00

"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("maasserver_agentcertificate")
    op.alter_column(
        "maasserver_agent",
        "rackcontroller_id",
        existing_type=sa.BIGINT(),
        nullable=True,
    )
    op.drop_constraint(
        "maasserver_agent_secret_key", "maasserver_agent", type_="unique"
    )
    op.drop_column("maasserver_agent", "secret")
    op.create_unique_constraint(
        None, "maasserver_agent", ["rack_id", "rackcontroller_id"]
    )


def downgrade() -> None: ...
