"""add openstreetmap source type

Revision ID: 531c7e1034ad
Revises: c12e08024a2d
Create Date: 2026-09-11 15:39:50.134429

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '531c7e1034ad'
down_revision: Union[str, None] = 'c12e08024a2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sources.source_type is a non-native Enum (VARCHAR(20), no CHECK
    # constraint), so adding SourceType.openstreetmap to the Python enum
    # requires no DDL change. This revision documents the schema-level
    # no-op and keeps the migration history in sync with the model.
    pass


def downgrade() -> None:
    pass
