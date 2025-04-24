"""add account_id to LockedMeal

Revision ID: 20250418_add_account_id_to_lockedmeal
Revises: b0e57c8d613d_add_shoppinglistitem_model
Create Date: 2025-04-18 12:15:56
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250418_add_account_id_to_lockedmeal'
down_revision = 'b0e57c8d613d'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('locked_meal', sa.Column('account_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_lockedmeal_account', 'locked_meal', 'account', ['account_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_lockedmeal_account', 'locked_meal', type_='foreignkey')
    op.drop_column('locked_meal', 'account_id')
