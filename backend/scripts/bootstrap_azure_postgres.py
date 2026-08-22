"""Create the credential-free Azure PostgreSQL application identity and DB.

This is a one-time operator command for a newly provisioned server. It uses the
current Azure CLI login to acquire an Entra token in memory, maps the single VM
managed identity to a non-admin PostgreSQL role, and creates the empty
lingosai database owned by that role.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, replace
from enum import Enum
from uuid import UUID

import psycopg
from azure.identity import AzureCliCredential
from psycopg import Connection, sql


TOKEN_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"
APPLICATION_ROLE = "vm-lingosai-prod"
APPLICATION_DATABASE = "lingosai"
_SERVER_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")


class BootstrapRefused(RuntimeError):
    """The target is not the exact expected fresh-start state."""


@dataclass(frozen=True)
class RoleState:
    can_login: bool
    is_superuser: bool
    can_create_role: bool
    can_create_database: bool
    can_replicate: bool
    bypasses_rls: bool
    mapping_count: int
    principal_type: str | None
    object_id: str | None
    is_admin: int | None


class BootstrapAction(str, Enum):
    CREATE_PRINCIPAL_AND_DATABASE = "created principal and database"
    CREATE_DATABASE = "resumed after principal creation"
    VERIFY = "verified existing empty bootstrap state"


def validate_inputs(
    server_name: str,
    administrator_principal: str,
    vm_object_id: str,
) -> str:
    if not _SERVER_RE.fullmatch(server_name):
        raise BootstrapRefused("invalid PostgreSQL server name")
    if (
        administrator_principal != administrator_principal.strip()
        or not administrator_principal.isprintable()
        or not 3 <= len(administrator_principal) <= 120
    ):
        raise BootstrapRefused("invalid Entra administrator principal name")
    try:
        parsed_object_id = UUID(vm_object_id)
    except ValueError as exc:
        raise BootstrapRefused("invalid VM managed-identity object ID") from exc
    if parsed_object_id.int == 0:
        raise BootstrapRefused("invalid VM managed-identity object ID")
    normalized_object_id = str(parsed_object_id)
    return normalized_object_id


def validate_role_state(role: RoleState, expected_object_id: str) -> None:
    expected = RoleState(
        can_login=True,
        is_superuser=False,
        can_create_role=False,
        can_create_database=False,
        can_replicate=False,
        bypasses_rls=False,
        mapping_count=1,
        principal_type="service",
        object_id=expected_object_id.lower(),
        is_admin=0,
    )
    normalized = replace(
        role,
        principal_type=(role.principal_type.lower() if role.principal_type else None),
        object_id=role.object_id.lower() if role.object_id else None,
    )
    if normalized != expected:
        raise BootstrapRefused(
            "the application role exists with an unexpected privilege or Entra mapping"
        )


def choose_action(
    role: RoleState | None,
    database_owner: str | None,
    expected_object_id: str,
) -> BootstrapAction:
    if role is None:
        if database_owner is not None:
            raise BootstrapRefused(
                "the application database exists without the expected role"
            )
        return BootstrapAction.CREATE_PRINCIPAL_AND_DATABASE

    validate_role_state(role, expected_object_id)
    if database_owner is None:
        return BootstrapAction.CREATE_DATABASE
    if database_owner != APPLICATION_ROLE:
        raise BootstrapRefused("the application database has an unexpected owner")
    return BootstrapAction.VERIFY


def _read_role_state(connection: Connection[tuple[object, ...]]) -> RoleState | None:
    role_row = connection.execute(
        """
        SELECT rolcanlogin, rolsuper, rolcreaterole, rolcreatedb,
               rolreplication, rolbypassrls
        FROM pg_catalog.pg_roles
        WHERE rolname = %s
        """,
        (APPLICATION_ROLE,),
    ).fetchone()
    mapping_rows = connection.execute(
        """
        SELECT principal_type::text, object_id::text, is_admin::integer
        FROM pg_catalog.pgaadauth_list_principals(false) AS principals(
            role_name,
            principal_type,
            object_id,
            tenant_id,
            is_mfa,
            is_admin
        )
        WHERE role_name = %s
        """,
        (APPLICATION_ROLE,),
    ).fetchall()

    if role_row is None:
        if mapping_rows:
            raise BootstrapRefused(
                "an Entra mapping exists without the application role"
            )
        return None

    mapping = mapping_rows[0] if len(mapping_rows) == 1 else (None, None, None)
    return RoleState(
        can_login=bool(role_row[0]),
        is_superuser=bool(role_row[1]),
        can_create_role=bool(role_row[2]),
        can_create_database=bool(role_row[3]),
        can_replicate=bool(role_row[4]),
        bypasses_rls=bool(role_row[5]),
        mapping_count=len(mapping_rows),
        principal_type=str(mapping[0]) if mapping[0] is not None else None,
        object_id=str(mapping[1]) if mapping[1] is not None else None,
        is_admin=int(str(mapping[2])) if mapping[2] is not None else None,
    )


def _read_database_owner(
    connection: Connection[tuple[object, ...]],
) -> str | None:
    row = connection.execute(
        """
        SELECT pg_catalog.pg_get_userbyid(datdba)
        FROM pg_catalog.pg_database
        WHERE datname = %s
        """,
        (APPLICATION_DATABASE,),
    ).fetchone()
    return str(row[0]) if row is not None else None


def _require_administrator(
    connection: Connection[tuple[object, ...]],
    expected_principal: str,
) -> None:
    row = connection.execute(
        """
        SELECT current_user,
               rolcreatedb,
               rolcreaterole,
               pg_catalog.pg_has_role(
                   current_user,
                   'azure_pg_admin',
                   'member'
               )
        FROM pg_catalog.pg_roles
        WHERE rolname = current_user
        """
    ).fetchone()
    if (
        row is None
        or str(row[0]) != expected_principal
        or not bool(row[1])
        or not bool(row[2])
        or not bool(row[3])
    ):
        raise BootstrapRefused(
            "the current token is not the approved Entra PostgreSQL administrator"
        )


def _require_empty_database(
    *,
    server_name: str,
    administrator_principal: str,
    access_token: str,
) -> None:
    with psycopg.connect(
        host=f"{server_name}.postgres.database.azure.com",
        port=5432,
        dbname=APPLICATION_DATABASE,
        user=administrator_principal,
        password=access_token,
        sslmode="require",
        connect_timeout=10,
        application_name="lingosai-identity-bootstrap-verify",
    ) as connection:
        row = connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_class AS class
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = class.relnamespace
            WHERE namespace.nspname = 'public'
              AND class.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
            """
        ).fetchone()
        if row is None or int(row[0]) != 0:
            raise BootstrapRefused(
                "the application database is not empty; identity bootstrap is closed"
            )


def bootstrap(
    *,
    server_name: str,
    administrator_principal: str,
    vm_object_id: str,
) -> BootstrapAction:
    normalized_object_id = validate_inputs(
        server_name,
        administrator_principal,
        vm_object_id,
    )
    credential = AzureCliCredential()
    access_token = credential.get_token(TOKEN_SCOPE).token
    if not access_token:
        raise BootstrapRefused("Azure CLI did not return a PostgreSQL token")

    with psycopg.connect(
        host=f"{server_name}.postgres.database.azure.com",
        port=5432,
        dbname="postgres",
        user=administrator_principal,
        password=access_token,
        sslmode="require",
        connect_timeout=10,
        application_name="lingosai-identity-bootstrap",
        autocommit=True,
    ) as connection:
        _require_administrator(connection, administrator_principal)
        role = _read_role_state(connection)
        database_owner = _read_database_owner(connection)
        action = choose_action(role, database_owner, normalized_object_id)

        if action is BootstrapAction.CREATE_PRINCIPAL_AND_DATABASE:
            connection.execute(
                """
                SELECT *
                FROM pg_catalog.pgaadauth_create_principal_with_oid(
                    %s, %s, 'service', false, false
                )
                """,
                (APPLICATION_ROLE, normalized_object_id),
            ).fetchone()
            role = _read_role_state(connection)
            if role is None:
                raise BootstrapRefused("application principal creation was not visible")
            validate_role_state(role, normalized_object_id)

        if action in {
            BootstrapAction.CREATE_PRINCIPAL_AND_DATABASE,
            BootstrapAction.CREATE_DATABASE,
        }:
            connection.execute(
                sql.SQL(
                    "CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0"
                ).format(
                    sql.Identifier(APPLICATION_DATABASE),
                    sql.Identifier(APPLICATION_ROLE),
                )
            )

        role = _read_role_state(connection)
        if role is None:
            raise BootstrapRefused("application role disappeared during verification")
        validate_role_state(role, normalized_object_id)
        database_owner = _read_database_owner(connection)
        if database_owner != APPLICATION_ROLE:
            raise BootstrapRefused("application database ownership verification failed")

    _require_empty_database(
        server_name=server_name,
        administrator_principal=administrator_principal,
        access_token=access_token,
    )
    return action


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap the Azure PostgreSQL managed-identity role and database."
    )
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--administrator-principal", required=True)
    parser.add_argument("--vm-object-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        action = bootstrap(
            server_name=args.server_name,
            administrator_principal=args.administrator_principal,
            vm_object_id=args.vm_object_id,
        )
    except BootstrapRefused as exc:
        print(f"Azure PostgreSQL identity bootstrap refused: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print("Azure PostgreSQL identity bootstrap failed safely.", file=sys.stderr)
        return 1

    print(f"Azure PostgreSQL identity bootstrap {action.value}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
