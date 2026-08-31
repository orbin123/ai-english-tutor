"""Fresh-start administrator bootstrap safety tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.admin.models import AIEvaluation
from app.modules.auth.fresh_admin_bootstrap import (
    FreshAdminBootstrapError,
    bootstrap_fresh_admin,
)
from app.modules.auth.models import (
    DEFAULT_ROLE_NAMES,
    ROLE_ADMIN,
    ROLE_LEARNER,
    ROLE_SUPER_ADMIN,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.modules.auth.permissions import DEFAULT_ROLE_PERMISSIONS, REQUIRED_PERMISSIONS
from app.modules.blog.models import BlogPost
from app.modules.skills.models import Skill
from app.modules.skills.seed_data import SKILL_SEED


EMAIL = "owner@example.com"
NAME = "Owner"
PASSWORD = "a-strong-test-password"
POST_MIGRATION_MISSING_PERMISSIONS = {"ai_quality.read", "reviews.read"}


def _seed_role_catalog(db: Session) -> dict[str, Role]:
    roles = {name: Role(name=name) for name in DEFAULT_ROLE_NAMES}
    permissions = {
        key: Permission(key=key, description=description)
        for key, description in REQUIRED_PERMISSIONS
        if key not in POST_MIGRATION_MISSING_PERMISSIONS
    }
    db.add_all([*roles.values(), *permissions.values()])
    db.flush()
    for role_name, permission_keys in DEFAULT_ROLE_PERMISSIONS.items():
        for permission_key in permission_keys:
            if permission_key in POST_MIGRATION_MISSING_PERMISSIONS:
                continue
            db.add(
                RolePermission(
                    role_id=roles[role_name].id,
                    permission_id=permissions[permission_key].id,
                )
            )
    db.flush()
    return roles


def _seed_migration_catalogs(db: Session) -> dict[str, Role]:
    roles = _seed_role_catalog(db)
    db.add_all(
        [
            Skill(name=name, description=description, display_label=display_label)
            for name, description, display_label in SKILL_SEED
        ]
    )
    db.add_all(
        [
            BlogPost(
                title="Migration post one",
                slug="why-traditional-english-learning-fails-most-learners",
                content="Migration-authored content",
                status="published",
            ),
            BlogPost(
                title="Migration post two",
                slug="7-communication-skills-that-matter-more-than-grammar",
                content="Migration-authored content",
                status="published",
            ),
        ]
    )
    db.flush()
    return roles


def test_bootstrap_creates_only_verified_admin_account(db_session: Session) -> None:
    _seed_migration_catalogs(db_session)

    result = bootstrap_fresh_admin(
        db_session, email=EMAIL, name=NAME, password=PASSWORD
    )

    user = db_session.scalar(select(User))
    assert result.created is True
    assert user is not None
    assert user.id == result.user_id
    assert user.email == EMAIL
    assert user.name == NAME
    assert user.is_active is True
    assert user.is_superuser is True
    assert user.email_verified is True
    assert user.email_verified_at is not None
    # A learning profile is created so the diagnosis flow accepts this account.
    assert user.profile is not None
    assert user.profile.diagnosis_completed is False
    assert {link.role.name for link in user.role_links} == {
        ROLE_ADMIN,
        ROLE_SUPER_ADMIN,
    }
    assert ROLE_LEARNER not in user.role_names()
    assert set(db_session.scalars(select(Permission.key)).all()) == {
        key for key, _description in REQUIRED_PERMISSIONS
    }


def test_bootstrap_is_idempotent_without_rewriting_credentials(
    db_session: Session,
) -> None:
    _seed_migration_catalogs(db_session)
    first = bootstrap_fresh_admin(db_session, email=EMAIL, name=NAME, password=PASSWORD)
    db_session.commit()
    password_hash = db_session.get(User, first.user_id).password_hash  # type: ignore[union-attr]

    second = bootstrap_fresh_admin(
        db_session, email=EMAIL, name=NAME, password=PASSWORD
    )

    assert second.created is False
    assert second.user_id == first.user_id
    assert db_session.scalar(select(func.count()).select_from(User)) == 1
    assert db_session.get(User, first.user_id).password_hash == password_hash  # type: ignore[union-attr]


def test_bootstrap_refuses_an_unexpected_user(db_session: Session) -> None:
    _seed_migration_catalogs(db_session)
    db_session.add(
        User(
            email="unexpected@example.com",
            password_hash=hash_password(PASSWORD),
            name="Unexpected",
        )
    )

    with pytest.raises(FreshAdminBootstrapError, match="does not match"):
        bootstrap_fresh_admin(db_session, email=EMAIL, name=NAME, password=PASSWORD)


def test_bootstrap_refuses_existing_learner_role(db_session: Session) -> None:
    roles = _seed_migration_catalogs(db_session)
    user = User(
        email=EMAIL,
        password_hash=hash_password(PASSWORD),
        name=NAME,
        is_superuser=True,
        is_active=True,
        email_verified=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.flush()
    for role_name in (ROLE_LEARNER, ROLE_ADMIN, ROLE_SUPER_ADMIN):
        db_session.add(UserRole(user_id=user.id, role_id=roles[role_name].id))

    with pytest.raises(FreshAdminBootstrapError, match="does not match"):
        bootstrap_fresh_admin(db_session, email=EMAIL, name=NAME, password=PASSWORD)


def test_bootstrap_refuses_unexpected_runtime_data(db_session: Session) -> None:
    _seed_migration_catalogs(db_session)
    db_session.add(
        AIEvaluation(
            target_type="feedback",
            judge_model="test-model",
            eval_mode="offline",
        )
    )

    with pytest.raises(FreshAdminBootstrapError, match="ai_evaluations"):
        bootstrap_fresh_admin(db_session, email=EMAIL, name=NAME, password=PASSWORD)


def test_bootstrap_refuses_a_modified_role_catalog(db_session: Session) -> None:
    _seed_migration_catalogs(db_session)
    db_session.add(Role(name="unexpected"))

    with pytest.raises(FreshAdminBootstrapError, match="role catalog"):
        bootstrap_fresh_admin(db_session, email=EMAIL, name=NAME, password=PASSWORD)
