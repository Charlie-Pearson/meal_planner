"""Add leftover columns to MealPlan

Revision ID: abc123
Revises: [previous_migration_id]
Create Date: 2023-06-01 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'abc123'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add the new columns
    op.add_column('meal_plan', sa.Column('is_leftover', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('meal_plan', sa.Column('leftover_from_day', sa.String(length=10), nullable=True))
    op.add_column('meal_plan', sa.Column('leftover_from_meal_type', sa.String(length=20), nullable=True))
    
    # Create an index on the leftover columns for better query performance
    op.create_index('idx_meal_plan_leftover', 'meal_plan', ['is_leftover'])


def downgrade():
    # Drop the index first
    op.drop_index('idx_meal_plan_leftover', 'meal_plan')
    
    # Drop the columns
    op.drop_column('meal_plan', 'leftover_from_meal_type')
    op.drop_column('meal_plan', 'leftover_from_day')
    op.drop_column('meal_plan', 'is_leftover')
