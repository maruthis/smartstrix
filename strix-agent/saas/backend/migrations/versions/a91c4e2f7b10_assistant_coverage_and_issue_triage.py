"""assistant coverage summary and issue triage/provenance

Revision ID: a91c4e2f7b10
Revises: 7c1f2b8d9e41
Create Date: 2026-09-10 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a91c4e2f7b10"
down_revision: Union[str, Sequence[str], None] = "7c1f2b8d9e41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pentests", sa.Column("coverage", sa.JSON(), nullable=True))
    op.add_column("issues", sa.Column("disposition", sa.String(), nullable=False, server_default="pending"))
    op.add_column("issues", sa.Column("disposition_note", sa.Text(), nullable=True))
    op.add_column("issues", sa.Column("file_path", sa.String(), nullable=True))
    op.add_column("issues", sa.Column("line_number", sa.Integer(), nullable=True))
    op.add_column("issues", sa.Column("specialist_name", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("issues", "specialist_name")
    op.drop_column("issues", "line_number")
    op.drop_column("issues", "file_path")
    op.drop_column("issues", "disposition_note")
    op.drop_column("issues", "disposition")
    op.drop_column("pentests", "coverage")
