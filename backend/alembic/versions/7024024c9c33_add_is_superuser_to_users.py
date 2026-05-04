"""add_is_superuser_to_users

Revision ID: 7024024c9c33
Revises: 4c5845f73ebe
Create Date: 2026-05-04 09:44:15.704580

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7024024c9c33'
down_revision: Union[str, Sequence[str], None] = '4c5845f73ebe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SUPERUSER_EMAIL = "sarath19@example.com"
SUPERUSER_NAME = "Sarath"
SUPERUSER_PASSWORD_HASH = "$2b$12$V9ZrrPCYU1hFCwfs83GJ6.7g7gOWEAviwd2qV0BpHI6vi8x/j0KgC"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column('is_superuser', sa.Boolean(), server_default='false', nullable=False),
    )

    conn = op.get_bind()
    conn.execute(sa.text("UPDATE users SET is_superuser = false"))

    existing_user = conn.execute(
        sa.text(
            """
            UPDATE users
            SET
                name = :name,
                password_hash = :password_hash,
                is_superuser = true
            WHERE lower(email) = lower(:email)
            RETURNING id
            """
        ),
        {
            "email": SUPERUSER_EMAIL,
            "name": SUPERUSER_NAME,
            "password_hash": SUPERUSER_PASSWORD_HASH,
        },
    ).first()

    if existing_user is None:
        existing_user = conn.execute(
            sa.text(
                """
                INSERT INTO users (email, password_hash, name, is_superuser)
                VALUES (lower(:email), :password_hash, :name, true)
                RETURNING id
                """
            ),
            {
                "email": SUPERUSER_EMAIL,
                "name": SUPERUSER_NAME,
                "password_hash": SUPERUSER_PASSWORD_HASH,
            },
        ).first()

    user_id = existing_user.id
    conn.execute(
        sa.text(
            """
            INSERT INTO user_profiles (
                user_id,
                self_assessed_level,
                daily_time_minutes,
                content_exposure,
                goal,
                interests,
                diagnosis_completed
            )
            SELECT
                :user_id,
                'BEGINNER',
                15,
                'LOW',
                'CASUAL',
                '',
                false
            WHERE NOT EXISTS (
                SELECT 1
                FROM user_profiles
                WHERE user_id = :user_id
            )
            """
        ),
        {"user_id": user_id},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'is_superuser')
