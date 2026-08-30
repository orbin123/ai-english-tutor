"""Passwordless Azure PostgreSQL token wiring."""

from dataclasses import dataclass
from typing import Any

import pytest

from app.core.azure_postgres import (
    AZURE_POSTGRES_TOKEN_SCOPE,
    AzurePostgresTokenProvider,
    install_azure_postgres_auth,
)


@dataclass
class _FakeAccessToken:
    token: str


class _FakeCredential:
    def __init__(self, *tokens: str) -> None:
        self._tokens = iter(tokens)
        self.scopes: list[str] = []

    def get_token(self, scope: str, **_kwargs: Any) -> _FakeAccessToken:
        self.scopes.append(scope)
        return _FakeAccessToken(next(self._tokens))


def test_token_provider_uses_fixed_postgres_scope_and_refreshes() -> None:
    credential = _FakeCredential("token-one", "token-two")
    provider = AzurePostgresTokenProvider(credential)

    assert provider.get_password() == "token-one"
    assert provider.get_password() == "token-two"
    assert credential.scopes == [
        AZURE_POSTGRES_TOKEN_SCOPE,
        AZURE_POSTGRES_TOKEN_SCOPE,
    ]


def test_token_provider_rejects_empty_token() -> None:
    provider = AzurePostgresTokenProvider(_FakeCredential(""))

    with pytest.raises(RuntimeError, match="empty access token"):
        provider.get_password()


def test_sqlalchemy_hook_injects_token_per_new_connection(monkeypatch) -> None:
    credential = _FakeCredential("token-one", "token-two")
    provider = AzurePostgresTokenProvider(credential)
    captured: dict[str, Any] = {}
    fake_engine = object()

    def fake_listen(engine: object, event_name: str, listener: Any) -> None:
        captured.update(
            engine=engine,
            event_name=event_name,
            listener=listener,
        )

    monkeypatch.setattr("app.core.azure_postgres.event.listen", fake_listen)

    installed = install_azure_postgres_auth(fake_engine, provider)  # type: ignore[arg-type]
    assert installed is provider
    assert captured["engine"] is fake_engine
    assert captured["event_name"] == "do_connect"

    params: dict[str, Any] = {}
    captured["listener"](None, None, [], params)
    assert params == {"password": "token-one"}

    captured["listener"](None, None, [], params)
    assert params == {"password": "token-two"}


def test_apply_configured_database_auth_installs_hook_for_managed_identity(
    monkeypatch,
) -> None:
    from app.core import database as database_module

    calls: list[object] = []
    engine = object()
    monkeypatch.setattr(
        database_module.settings, "DATABASE_AUTH_MODE", "azure-managed-identity"
    )
    monkeypatch.setattr(
        database_module,
        "install_azure_postgres_auth",
        lambda bind: calls.append(bind),
    )

    assert database_module.apply_configured_database_auth(engine) is engine  # type: ignore[arg-type]
    assert calls == [engine]


def test_apply_configured_database_auth_skips_password_mode(monkeypatch) -> None:
    from app.core import database as database_module

    calls: list[object] = []
    engine = object()
    monkeypatch.setattr(database_module.settings, "DATABASE_AUTH_MODE", "password")
    monkeypatch.setattr(
        database_module,
        "install_azure_postgres_auth",
        lambda bind: calls.append(bind),
    )

    assert database_module.apply_configured_database_auth(engine) is engine  # type: ignore[arg-type]
    assert calls == []
