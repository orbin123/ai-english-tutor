"""create curriculum tables and link user_tasks

Revision ID: e6b355a12fa1
Revises: 123340a0545a
Create Date: 2026-04-28 17:09:50.294192

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql   # FIX: needed for ENUM(create_type=False)


# revision identifiers, used by Alembic.
revision: str = 'e6b355a12fa1'
down_revision: Union[str, Sequence[str], None] = '123340a0545a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'courses',
        sa.Column('slug', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=False),
        sa.Column('duration_weeks', sa.Integer(), nullable=False),
        sa.Column('target_level', sa.Enum('BEGINNER', 'INTERMEDIATE', 'ADVANCED', name='course_level_enum'), nullable=False),
        sa.Column('status', sa.Enum('DRAFT', 'ACTIVE', 'ARCHIVED', name='course_status_enum'), nullable=False),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_courses_slug'), 'courses', ['slug'], unique=True)
    op.create_index(op.f('ix_courses_status'), 'courses', ['status'], unique=False)

    op.create_table(
        'user_enrollments',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('current_week', sa.Integer(), nullable=False),
        sa.Column('current_day_in_week', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'PAUSED', 'COMPLETED', 'ABANDONED', name='enrollment_status_enum'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_user_enrollments_course_id'), 'user_enrollments', ['course_id'], unique=False)
    op.create_index(op.f('ix_user_enrollments_status'), 'user_enrollments', ['status'], unique=False)
    op.create_index(op.f('ix_user_enrollments_user_id'), 'user_enrollments', ['user_id'], unique=True)

    op.create_table(
        'enrollment_skill_history',
        sa.Column('enrollment_id', sa.Integer(), nullable=False),
        sa.Column('skill_id', sa.Integer(), nullable=False),
        # FIX: reuse the existing task_type_enum — don't recreate it.
        sa.Column(
            'last_activity_type',
            postgresql.ENUM(
                'READING', 'WRITING', 'SPEAKING', 'LISTENING',
                name='task_type_enum',
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column('times_practiced', sa.Integer(), nullable=False),
        sa.Column('last_practiced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['enrollment_id'], ['user_enrollments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('enrollment_id', 'skill_id', name='uq_enrollment_skill'),
    )
    op.create_index(op.f('ix_enrollment_skill_history_enrollment_id'), 'enrollment_skill_history', ['enrollment_id'], unique=False)
    op.create_index(op.f('ix_enrollment_skill_history_skill_id'), 'enrollment_skill_history', ['skill_id'], unique=False)

    # Link user_tasks to enrollments (nullable; SET NULL on enrollment delete).
    op.add_column('user_tasks', sa.Column('enrollment_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_user_tasks_enrollment_id'), 'user_tasks', ['enrollment_id'], unique=False)
    # FIX: give the FK an explicit name so downgrade can drop it cleanly.
    op.create_foreign_key(
        'fk_user_tasks_enrollment_id',
        'user_tasks', 'user_enrollments',
        ['enrollment_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    # FIX: use the explicit FK name we set in upgrade.
    op.drop_constraint('fk_user_tasks_enrollment_id', 'user_tasks', type_='foreignkey')
    op.drop_index(op.f('ix_user_tasks_enrollment_id'), table_name='user_tasks')
    op.drop_column('user_tasks', 'enrollment_id')

    op.drop_index(op.f('ix_enrollment_skill_history_skill_id'), table_name='enrollment_skill_history')
    op.drop_index(op.f('ix_enrollment_skill_history_enrollment_id'), table_name='enrollment_skill_history')
    op.drop_table('enrollment_skill_history')

    op.drop_index(op.f('ix_user_enrollments_user_id'), table_name='user_enrollments')
    op.drop_index(op.f('ix_user_enrollments_status'), table_name='user_enrollments')
    op.drop_index(op.f('ix_user_enrollments_course_id'), table_name='user_enrollments')
    op.drop_table('user_enrollments')

    op.drop_index(op.f('ix_courses_status'), table_name='courses')
    op.drop_index(op.f('ix_courses_slug'), table_name='courses')
    op.drop_table('courses')

    # FIX: clean up the new enum types so a re-upgrade doesn't fail.
    sa.Enum(name='enrollment_status_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='course_status_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='course_level_enum').drop(op.get_bind(), checkfirst=True)