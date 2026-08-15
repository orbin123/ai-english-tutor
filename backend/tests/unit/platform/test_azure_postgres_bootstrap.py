from __future__ import annotations

import pytest

from scripts import bootstrap_azure_postgres as bootstrap_module
from scripts.bootstrap_azure_postgres import (
    APPLICATION_ROLE,
    BootstrapAction,
    BootstrapRefused,
    RoleState,
    choose_action,
    validate_inputs,
    validate_role_state,
)


VM_OBJECT_ID = "11111111-2222-3333-4444-555555555555"


def _expected_role(**overrides: object) -> RoleState:
    values: dict[str, object] = {
        "can_login": True,
        "is_superuser": False,
        "can_create_role": False,
        "can_create_database": False,
        "can_replicate": False,
        "bypasses_rls": False,
        "mapping_count": 1,
        "principal_type": "service",
        "object_id": VM_OBJECT_ID,
        "is_admin": 0,
    }
    values.update(overrides)
    return RoleState(**values)  # type: ignore[arg-type]


def test_validate_inputs_normalizes_object_id() -> None:
    assert (
        validate_inputs(
            "lingosai-test-postgres",
            "lingosai-postgres-administrators",
            VM_OBJECT_ID.upper(),
        )
        == VM_OBJECT_ID
    )


@pytest.mark.parametrize(
    ("server", "administrator", "object_id"),
    [
        ("Bad_Server", "approved-group", VM_OBJECT_ID),
        ("valid-server", "x", VM_OBJECT_ID),
        ("valid-server", " approved-group", VM_OBJECT_ID),
        ("valid-server", "approved-group", "not-a-uuid"),
        (
            "valid-server",
            "approved-group",
            "00000000-0000-0000-0000-000000000000",
        ),
    ],
)
def test_validate_inputs_rejects_unreviewed_identifiers(
    server: str,
    administrator: str,
    object_id: str,
) -> None:
    with pytest.raises(BootstrapRefused):
        validate_inputs(server, administrator, object_id)


def test_choose_action_for_pristine_server() -> None:
    assert (
        choose_action(None, None, VM_OBJECT_ID)
        is BootstrapAction.CREATE_PRINCIPAL_AND_DATABASE
    )


def test_choose_action_can_resume_exact_partial_creation() -> None:
    assert (
        choose_action(_expected_role(), None, VM_OBJECT_ID)
        is BootstrapAction.CREATE_DATABASE
    )


def test_choose_action_verifies_exact_empty_bootstrap_state() -> None:
    assert (
        choose_action(_expected_role(), APPLICATION_ROLE, VM_OBJECT_ID)
        is BootstrapAction.VERIFY
    )


@pytest.mark.parametrize(
    "role",
    [
        _expected_role(can_login=False),
        _expected_role(is_superuser=True),
        _expected_role(can_create_role=True),
        _expected_role(can_create_database=True),
        _expected_role(mapping_count=2),
        _expected_role(principal_type="group"),
        _expected_role(object_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
        _expected_role(is_admin=1),
    ],
)
def test_role_verification_rejects_privilege_or_mapping_drift(
    role: RoleState,
) -> None:
    with pytest.raises(BootstrapRefused):
        validate_role_state(role, VM_OBJECT_ID)


def test_choose_action_rejects_database_without_role() -> None:
    with pytest.raises(BootstrapRefused, match="without the expected role"):
        choose_action(None, APPLICATION_ROLE, VM_OBJECT_ID)


def test_choose_action_rejects_wrong_database_owner() -> None:
    with pytest.raises(BootstrapRefused, match="unexpected owner"):
        choose_action(_expected_role(), "other-owner", VM_OBJECT_ID)


def test_main_redacts_unexpected_connection_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "bootstrap_azure_postgres",
            "--server-name",
            "lingosai-test-postgres",
            "--administrator-principal",
            "approved-admin-group",
            "--vm-object-id",
            VM_OBJECT_ID,
        ],
    )

    def _fail(**_: str) -> BootstrapAction:
        raise RuntimeError("sensitive provider detail")

    monkeypatch.setattr(bootstrap_module, "bootstrap", _fail)

    assert bootstrap_module.main() == 1
    captured = capsys.readouterr()
    assert "failed safely" in captured.err
    assert "sensitive provider detail" not in captured.err
