"""Fail-closed bootstrap for the single fresh-start administrator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import inspect, literal, select, text
from sqlalchemy.orm import Session

from app import models as _models  # noqa: F401 - register the complete ORM schema
from app.core.database import Base
from app.core.security import hash_password, verify_password
from app.modules.auth.models import (
    DEFAULT_ROLE_NAMES,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.modules.auth.permissions import DEFAULT_ROLE_PERMISSIONS, REQUIRED_PERMISSIONS
from app.modules.auth.repository import RoleRepository
from app.modules.blog.models import BlogPost
from app.modules.skills.models import Skill
from app.modules.skills.seed_data import SKILL_SEED


class FreshAdminBootstrapError(RuntimeError):
    """The database is not in the exact safe state required for bootstrap."""


@dataclass(frozen=True)
class FreshAdminBootstrapResult:
    """Non-sensitive bootstrap outcome."""

    created: bool
    user_id: int


# These tables contain data authored directly by migrations. Operational seeders
# must run only after this bootstrap has accepted the fresh database.
# Every other application table must be empty when this one-time command runs.
_CATALOG_TABLES = frozenset(
    {
        "blog_posts",
        "permissions",
        "role_permissions",
        "roles",
        "skills",
    }
)
_BOOTSTRAP_TABLES = frozenset({"users", "user_roles"})
_NON_ORM_TABLES = frozenset({"alembic_version"})
# Phase 8 dropped these ORM-still-registered tables from the migration graph.
# Fresh Azure databases match Alembic head without them; SQLite create_all tests
# still materialize them. Treat absence as allowed, presence as allowed.
_DROPPED_LEGACY_TABLES = frozenset({"courses", "user_enrollments"})
_ADVISORY_LOCK_ID = 4_792_061_151
_EXPECTED_ALEMBIC_HEAD = "t0u1v2w3x456"
_POST_MIGRATION_PERMISSION_KEYS = {
    key for key, _description in REQUIRED_PERMISSIONS
} - {"ai_quality.read", "reviews.read"}
_EXPECTED_BLOG_SLUGS = {
    "why-traditional-english-learning-fails-most-learners",
    "7-communication-skills-that-matter-more-than-grammar",
}


def bootstrap_fresh_admin(
    db: Session,
    *,
    email: str,
    name: str,
    password: str,
) -> FreshAdminBootstrapResult:
    """Create or verify the only account in an otherwise fresh database.

    The caller owns the transaction. No existing value is repaired or replaced:
    any mismatch fails so an operator cannot accidentally convert or overwrite a
    restored database.
    """

    normalized_email = email.strip().lower()
    normalized_name = name.strip()
    if not normalized_email or not normalized_name:
        raise FreshAdminBootstrapError("bootstrap identity is invalid")
    if not 8 <= len(password) <= 128:
        raise FreshAdminBootstrapError("bootstrap credential is invalid")

    db.flush()
    _lock_bootstrap_transaction(db)
    _validate_schema(db)
    roles = _prepare_role_catalog(db)
    _validate_migration_catalogs(db)
    _reject_unexpected_runtime_data(db)

    users = db.scalars(select(User).order_by(User.id)).all()
    if not users:
        user = User(
            email=normalized_email,
            password_hash=hash_password(password),
            name=normalized_name,
            is_superuser=True,
            is_active=True,
            email_verified=True,
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.flush()
        db.add_all(
            [
                UserRole(user_id=user.id, role_id=roles[ROLE_ADMIN].id),
                UserRole(user_id=user.id, role_id=roles[ROLE_SUPER_ADMIN].id),
            ]
        )
        db.flush()
        return FreshAdminBootstrapResult(created=True, user_id=user.id)

    if len(users) != 1:
        raise FreshAdminBootstrapError("unexpected users exist")

    user = users[0]
    actual_roles = set(
        db.scalars(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        ).all()
    )
    expected_roles = {ROLE_ADMIN, ROLE_SUPER_ADMIN}
    is_exact_match = (
        user.email == normalized_email
        and user.name == normalized_name
        and user.password_hash is not None
        and verify_password(password, user.password_hash)
        and user.is_superuser
        and user.is_active
        and user.email_verified
        and user.email_verified_at is not None
        and actual_roles == expected_roles
    )
    if not is_exact_match:
        raise FreshAdminBootstrapError("existing bootstrap account does not match")

    return FreshAdminBootstrapResult(created=False, user_id=user.id)


def _lock_bootstrap_transaction(db: Session) -> None:
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _ADVISORY_LOCK_ID},
        )


def _validate_schema(db: Session) -> None:
    expected = set(Base.metadata.tables)
    actual = set(inspect(db.connection()).get_table_names())
    missing = expected - actual - _DROPPED_LEGACY_TABLES
    unknown = actual - expected - _NON_ORM_TABLES
    if missing or unknown:
        raise FreshAdminBootstrapError(
            "database schema is not the expected migration head"
        )
    if "alembic_version" in actual:
        revisions = set(db.scalars(text("SELECT version_num FROM alembic_version")))
        if revisions != {_EXPECTED_ALEMBIC_HEAD}:
            raise FreshAdminBootstrapError(
                "database schema is not the expected migration head"
            )


def _prepare_role_catalog(db: Session) -> dict[str, Role]:
    roles = db.scalars(select(Role)).all()
    roles_by_name = {role.name: role for role in roles}
    if set(roles_by_name) != set(DEFAULT_ROLE_NAMES):
        raise FreshAdminBootstrapError(
            f"role catalog does not match application defaults: {sorted(roles_by_name)}"
        )

    permissions = db.scalars(select(Permission)).all()
    permission_keys = {permission.key for permission in permissions}
    current_permission_keys = {key for key, _description in REQUIRED_PERMISSIONS}
    if permission_keys not in (
        _POST_MIGRATION_PERMISSION_KEYS,
        current_permission_keys,
    ):
        raise FreshAdminBootstrapError(
            "permission catalog does not match application defaults"
        )

    actual_grants = set(
        db.execute(
            select(Role.name, Permission.key)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
        ).all()
    )
    expected_existing_grants = {
        (role_name, permission_key)
        for role_name, granted_keys in DEFAULT_ROLE_PERMISSIONS.items()
        for permission_key in granted_keys
        if permission_key in permission_keys
    }
    if actual_grants != expected_existing_grants:
        raise FreshAdminBootstrapError(
            "role permission grants do not match application defaults"
        )

    # Historical migrations predate two current permissions. Add only those
    # code-defined defaults after proving the starting catalog is recognized.
    prepared_roles = RoleRepository(db).ensure_defaults()
    prepared_keys = set(db.scalars(select(Permission.key)).all())
    if prepared_keys != current_permission_keys:
        raise FreshAdminBootstrapError(
            "permission catalog does not match application defaults"
        )
    return prepared_roles


def _validate_migration_catalogs(db: Session) -> None:
    actual_skills = set(
        db.execute(select(Skill.name, Skill.description, Skill.display_label)).all()
    )
    if actual_skills != set(SKILL_SEED):
        raise FreshAdminBootstrapError(
            "skill catalog does not match migration-authored data"
        )

    blog_rows = db.execute(select(BlogPost.slug, BlogPost.author_id)).all()
    if (
        {slug for slug, _author_id in blog_rows} != _EXPECTED_BLOG_SLUGS
        or any(author_id is not None for _slug, author_id in blog_rows)
        or len(blog_rows) != len(_EXPECTED_BLOG_SLUGS)
    ):
        raise FreshAdminBootstrapError(
            "blog catalog does not match migration-authored data"
        )


def _reject_unexpected_runtime_data(db: Session) -> None:
    allowed = _CATALOG_TABLES | _BOOTSTRAP_TABLES
    unexpected_tables = []
    for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
        if table.name in allowed:
            continue
        has_row = db.execute(select(literal(1)).select_from(table).limit(1)).first()
        if has_row is not None:
            unexpected_tables.append(table.name)
    if unexpected_tables:
        names = ", ".join(unexpected_tables)
        raise FreshAdminBootstrapError(f"unexpected runtime data exists in: {names}")
