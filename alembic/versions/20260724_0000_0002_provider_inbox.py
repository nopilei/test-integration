"""Inbox для дедупликации входящих сообщений провайдера по message_id

Revision ID: 0002_provider_inbox
Revises: 0001_init
Create Date: 2026-07-24 00:00:00
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_provider_inbox"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processed_provider_messages",
        sa.Column("message_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_type", sa.String(length=64), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_processed_provider_messages_processed_at",
        "processed_provider_messages",
        ["processed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_processed_provider_messages_processed_at",
        table_name="processed_provider_messages",
    )
    op.drop_table("processed_provider_messages")
