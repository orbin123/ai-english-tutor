"""Data access for User, UserProfile, and OAuthAccount."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.modules.auth.models import (
    DEFAULT_ROLE_NAMES,
    OAuthAccount,
    Permission,
    Role,
    RolePermission,
    User,
    UserProfile,
    UserRole,
)
from app.modules.auth.permissions import DEFAULT_ROLE_PERMISSIONS, REQUIRED_PERMISSIONS


class UserRepository:
    """All DB access for the User table goes through this class."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # Reads
    def get_by_id(self, user_id: int) -> User | None:
        return (
            self.db.query(User)
            .options(
                selectinload(User.role_links)
                .joinedload(UserRole.role)
                .selectinload(Role.permission_links)
                .joinedload(RolePermission.permission),
            )
            .filter(User.id == user_id)
            .first()
        )

    def list_all(self) -> list[User]:
        return (
            self.db.query(User).order_by(User.created_at.desc(), User.id.desc()).all()
        )

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email.lower()).first()

    def email_exists(self, email: str) -> bool:
        return self.get_by_email(email) is not None

    # Writes
    def create(self, *, email: str, password_hash: str, name: str) -> User:
        user = User(
            email=email.lower(),
            password_hash=password_hash,
            name=name,
        )
        self.db.add(user)
        self.db.flush()  # populate user.id without committing
        return user

    def create_oauth_user(self, *, email: str, name: str) -> User:
        """Create a user that has no password (Google OAuth user)."""
        user = User(
            email=email.lower(),
            password_hash=None,
            name=name,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def delete(self, user: User) -> None:
        self.db.delete(user)

    def set_active(self, user: User, *, is_active: bool) -> User:
        user.is_active = is_active
        self.db.flush()
        return user


class RoleRepository:
    """DB access for application roles and user-role assignments."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_name(self, name: str) -> Role | None:
        return self.db.query(Role).filter(Role.name == name).first()

    def ensure_defaults(self) -> dict[str, Role]:
        roles: dict[str, Role] = {}
        for name in DEFAULT_ROLE_NAMES:
            role = self.get_by_name(name)
            if role is None:
                role = Role(name=name)
                self.db.add(role)
                self.db.flush()
            roles[name] = role
        permissions = self.ensure_permissions()
        for role_name, permission_keys in DEFAULT_ROLE_PERMISSIONS.items():
            role = roles[role_name]
            existing_keys = {
                key
                for (key,) in (
                    self.db.query(Permission.key)
                    .join(
                        RolePermission,
                        RolePermission.permission_id == Permission.id,
                    )
                    .filter(RolePermission.role_id == role.id)
                    .all()
                )
            }
            for permission_key in permission_keys:
                if permission_key in existing_keys:
                    continue
                self.db.add(
                    RolePermission(
                        role_id=role.id,
                        permission_id=permissions[permission_key].id,
                    )
                )
            self.db.flush()
            self.db.expire(role, ["permission_links"])
        return roles

    def ensure_permissions(self) -> dict[str, Permission]:
        permissions: dict[str, Permission] = {}
        for key, description in REQUIRED_PERMISSIONS:
            permission = self.get_permission_by_key(key)
            if permission is None:
                permission = Permission(key=key, description=description)
                self.db.add(permission)
                self.db.flush()
            permissions[key] = permission
        return permissions

    def list_roles(self) -> list[Role]:
        self.ensure_defaults()
        return (
            self.db.query(Role)
            .options(
                selectinload(Role.permission_links).joinedload(
                    RolePermission.permission
                )
            )
            .order_by(Role.name.asc())
            .all()
        )

    def list_permissions(self) -> list[Permission]:
        self.ensure_permissions()
        return self.db.query(Permission).order_by(Permission.key.asc()).all()

    def get_permission_by_key(self, key: str) -> Permission | None:
        return self.db.query(Permission).filter(Permission.key == key).first()

    def get_role(self, role_id: int) -> Role | None:
        return (
            self.db.query(Role)
            .options(
                selectinload(Role.permission_links).joinedload(
                    RolePermission.permission
                )
            )
            .filter(Role.id == role_id)
            .first()
        )

    def assign_role(self, *, user_id: int, role_name: str) -> UserRole:
        role = self.ensure_defaults()[role_name]
        existing = (
            self.db.query(UserRole)
            .filter(UserRole.user_id == user_id, UserRole.role_id == role.id)
            .first()
        )
        if existing is not None:
            return existing

        user_role = UserRole(user_id=user_id, role_id=role.id)
        self.db.add(user_role)
        self.db.flush()
        return user_role

    def replace_user_roles(self, *, user: User, role_names: set[str]) -> None:
        roles = self.ensure_defaults()
        existing = self.db.query(UserRole).filter(UserRole.user_id == user.id).all()
        for link in existing:
            self.db.delete(link)
        self.db.flush()
        for role_name in sorted(role_names):
            self.db.add(UserRole(user_id=user.id, role_id=roles[role_name].id))
        user.is_superuser = "super_admin" in role_names
        self.db.flush()
        self.db.expire(user, ["role_links"])

    def replace_role_permissions(
        self,
        *,
        role: Role,
        permission_keys: set[str],
    ) -> None:
        permissions = self.ensure_permissions()
        existing = (
            self.db.query(RolePermission)
            .filter(RolePermission.role_id == role.id)
            .all()
        )
        for link in existing:
            self.db.delete(link)
        self.db.flush()
        for permission_key in sorted(permission_keys):
            self.db.add(
                RolePermission(
                    role_id=role.id,
                    permission_id=permissions[permission_key].id,
                )
            )
        self.db.flush()
        self.db.expire(role, ["permission_links"])


class UserProfileRepository:
    """All DB access for UserProfile."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_user_id(self, user_id: int) -> UserProfile | None:
        return self.db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

    def create_default(self, user_id: int) -> UserProfile:
        """Create a profile with default values (used right after signup)."""
        profile = UserProfile(user_id=user_id)
        self.db.add(profile)
        self.db.flush()
        return profile

    def ensure_default(self, user_id: int) -> UserProfile:
        """Return the user's profile, creating a default one if it's missing.

        Every signup path creates a profile, but a few accounts predate that
        guarantee (the fresh-admin bootstrap, and users who first signed up
        with email/password before this backfill existed). Idempotent.
        """
        profile = self.get_by_user_id(user_id)
        if profile is None:
            profile = self.create_default(user_id)
        return profile

    def set_structured_personalisation(
        self,
        *,
        user_id: int,
        payload: dict[str, Any],
    ) -> UserProfile | None:
        """Write the structured personalisation JSON onto the profile.

        Stamps `structured_personalisation_updated_at` so we can detect
        staleness. Returns None if the profile doesn't exist (shouldn't
        happen in practice — every user has a profile from signup).
        """
        profile = self.get_by_user_id(user_id)
        if profile is None:
            return None
        profile.structured_personalisation = payload
        profile.structured_personalisation_updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return profile


class OAuthAccountRepository:
    """All DB access for OAuthAccount."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_provider(
        self, provider: str, provider_user_id: str
    ) -> OAuthAccount | None:
        """Find an existing OAuth link by provider + their user id."""
        return (
            self.db.query(OAuthAccount)
            .filter(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_user_id == provider_user_id,
            )
            .first()
        )

    def create(
        self, *, user_id: int, provider: str, provider_user_id: str
    ) -> OAuthAccount:
        account = OAuthAccount(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
        )
        self.db.add(account)
        self.db.flush()
        return account
