"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("vehicle_plate", sa.String(length=20), nullable=True),
        sa.Column("api_key_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hw_model", sa.String(length=50), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("api_key_hash"),
    )
    op.create_index("ix_devices_api_key_hash", "devices", ["api_key_hash"])

    op.create_table(
        "captures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("h3_cell", sa.String(length=15), nullable=True),
        sa.Column("weather_label", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "weather_label IN ('seco', 'garoa', 'moderado', 'forte')",
            name="ck_captures_weather_label",
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_captures_captured_at", "captures", ["captured_at"])
    op.create_index("ix_captures_latitude", "captures", ["latitude"])
    op.create_index("ix_captures_longitude", "captures", ["longitude"])
    op.create_index("ix_captures_h3_cell", "captures", ["h3_cell"])
    op.create_index("ix_captures_device_id", "captures", ["device_id"])

    op.create_table(
        "media_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("capture_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["capture_id"], ["captures.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256"),
    )
    op.create_index("ix_media_files_capture_id", "media_files", ["capture_id"])
    op.create_index("ix_media_files_sha256", "media_files", ["sha256"])

    op.create_table(
        "ingestion_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("capture_id", sa.Integer(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("protocol", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["capture_id"], ["captures.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_logs_capture_id", "ingestion_logs", ["capture_id"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_logs_capture_id", table_name="ingestion_logs")
    op.drop_table("ingestion_logs")

    op.drop_index("ix_media_files_sha256", table_name="media_files")
    op.drop_index("ix_media_files_capture_id", table_name="media_files")
    op.drop_table("media_files")

    op.drop_index("ix_captures_device_id", table_name="captures")
    op.drop_index("ix_captures_h3_cell", table_name="captures")
    op.drop_index("ix_captures_longitude", table_name="captures")
    op.drop_index("ix_captures_latitude", table_name="captures")
    op.drop_index("ix_captures_captured_at", table_name="captures")
    op.drop_table("captures")

    op.drop_index("ix_devices_api_key_hash", table_name="devices")
    op.drop_table("devices")
