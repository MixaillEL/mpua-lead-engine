"""add web_search source type

Revision ID: 24dbc667ca6f
Revises: 5ccaaffd2b6d
Create Date: 2026-09-11 16:35:53.481952

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '24dbc667ca6f'
down_revision: Union[str, None] = '5ccaaffd2b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sources.source_type is a non-native Enum (VARCHAR(20), no CHECK
    # constraint), so adding SourceType.web_search to the Python enum
    # requires no DDL change. This revision documents the schema-level
    # no-op and keeps the migration history in sync with the model.
    pass


def downgrade() -> None:
    pass
