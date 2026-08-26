"""add llm token usage to pentests and pr reviews

Revision ID: 7c1f2b8d9e41
Revises: 3bc90afb1f9b
Create Date: 2026-08-24 15:58:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c1f2b8d9e41"
down_revision: Union[str, Sequence[str], None] = "3bc90afb1f9b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pentests", sa.Column("llm_input_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pentests", sa.Column("llm_output_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pentests", sa.Column("llm_total_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pr_reviews", sa.Column("llm_input_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pr_reviews", sa.Column("llm_output_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("pr_reviews", sa.Column("llm_total_tokens", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("pr_reviews", "llm_total_tokens")
    op.drop_column("pr_reviews", "llm_output_tokens")
    op.drop_column("pr_reviews", "llm_input_tokens")
    op.drop_column("pentests", "llm_total_tokens")
    op.drop_column("pentests", "llm_output_tokens")
    op.drop_column("pentests", "llm_input_tokens")
