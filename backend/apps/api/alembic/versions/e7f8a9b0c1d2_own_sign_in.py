"""own sign-in: password hash, Google link, proven email, session version

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column("user", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.add_column("user", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_user_google_sub", "user", ["google_sub"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_google_sub", table_name="user")
    op.drop_column("user", "session_version")
    op.drop_column("user", "email_verified")
    op.drop_column("user", "google_sub")
    op.drop_column("user", "password_hash")
