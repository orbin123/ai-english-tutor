"""Passwordless Azure PostgreSQL authentication for SQLAlchemy.

Azure Database for PostgreSQL accepts a Microsoft Entra access token in the
password field. SQLAlchemy's ``do_connect`` hook is used so every new DBAPI
connection receives a current token without ever storing it in settings or the
engine URL.
"""

from typing import Any, Protocol, cast

from sqlalchemy import event
from sqlalchemy.engine import Engine

AZURE_POSTGRES_TOKEN_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"


class _AccessToken(Protocol):
    token: str


class _TokenCredential(Protocol):
    def get_token(self, *scopes: str, **kwargs: Any) -> _AccessToken: ...


class AzurePostgresTokenProvider:
    """Retrieve PostgreSQL access tokens from the ambient Azure identity."""

    def __init__(self, credential: _TokenCredential | None = None) -> None:
        self._credential = credential

    def get_password(self) -> str:
        """Return a current token for one new PostgreSQL connection."""
        credential = self._credential
        if credential is None:
            from azure.identity import DefaultAzureCredential

            credential = cast(_TokenCredential, DefaultAzureCredential())
            self._credential = credential

        token = credential.get_token(AZURE_POSTGRES_TOKEN_SCOPE).token
        if not token:
            raise RuntimeError("Azure PostgreSQL returned an empty access token")
        return token


def install_azure_postgres_auth(
    engine: Engine,
    token_provider: AzurePostgresTokenProvider | None = None,
) -> AzurePostgresTokenProvider:
    """Inject a fresh Entra token before each new DBAPI connection."""
    provider = token_provider or AzurePostgresTokenProvider()

    def provide_token(
        _dialect: Any,
        _connection_record: Any,
        _connection_args: list[Any],
        connection_params: dict[str, Any],
    ) -> None:
        connection_params["password"] = provider.get_password()

    event.listen(engine, "do_connect", provide_token)
    return provider
