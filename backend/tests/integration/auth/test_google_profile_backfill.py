"""Google login backfills a learning profile for accounts that never got one.

Every signup path creates a `user_profiles` row, but a few accounts predate
that guarantee (the fresh-admin bootstrap, and old email/password signups).
Without a profile the diagnosis flow rejects the account, so the Google
find-or-create path repairs it.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.auth.service import AuthService
from tests.factories.users import make_user


def test_existing_email_user_without_profile_gets_one_on_google_login(
    db_session: Session,
) -> None:
    user = make_user(
        db_session,
        email="legacy@example.com",
        with_profile=False,
        verified=False,
    )
    db_session.commit()
    assert user.profile is None

    linked, is_new = AuthService(db_session).get_or_create_google_user(
        google_user_id="google-legacy-1",
        email="legacy@example.com",
        name="Legacy",
    )

    assert is_new is False
    assert linked.id == user.id
    db_session.refresh(user)
    assert user.profile is not None
    assert user.profile.diagnosis_completed is False


def test_oauth_linked_user_without_profile_gets_one_on_google_login(
    db_session: Session,
) -> None:
    user = make_user(db_session, email="linked@example.com", with_profile=False)
    AuthService(db_session).oauth_accounts.create(
        user_id=user.id,
        provider="google",
        provider_user_id="google-linked-1",
    )
    db_session.commit()
    assert user.profile is None

    linked, is_new = AuthService(db_session).get_or_create_google_user(
        google_user_id="google-linked-1",
        email="linked@example.com",
        name="Linked",
    )

    assert is_new is False
    assert linked.id == user.id
    db_session.refresh(user)
    assert user.profile is not None


def test_google_login_leaves_an_existing_profile_untouched(
    db_session: Session,
) -> None:
    user = make_user(db_session, email="has-profile@example.com")
    user.profile.display_name = "Keep Me"
    db_session.commit()
    profile_id = user.profile.id

    AuthService(db_session).get_or_create_google_user(
        google_user_id="google-has-profile-1",
        email="has-profile@example.com",
        name="Has Profile",
    )

    db_session.refresh(user)
    assert user.profile.id == profile_id
    assert user.profile.display_name == "Keep Me"
