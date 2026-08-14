"""Bootstrap the sole administrator in an approved fresh-start database.

The command reads a small JSON object from stdin so the identity and password do
not appear in Git, command arguments, or the persistent production environment.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from pydantic import BaseModel, EmailStr, Field, SecretStr, ValidationError

from app.core.database import SessionLocal
from app.modules.auth.fresh_admin_bootstrap import (
    FreshAdminBootstrapError,
    bootstrap_fresh_admin,
)


_MAX_INPUT_BYTES = 16 * 1024


class _BootstrapInput(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=8, max_length=128)

    model_config = {"extra": "forbid"}


def _read_input() -> _BootstrapInput:
    raw = sys.stdin.buffer.read(_MAX_INPUT_BYTES + 1)
    if not raw or len(raw) > _MAX_INPUT_BYTES:
        raise ValueError("invalid bootstrap input")
    try:
        payload: Any = json.loads(raw)
        return _BootstrapInput.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("invalid bootstrap input") from exc


def main() -> int:
    try:
        payload = _read_input()
        with SessionLocal.begin() as db:
            result = bootstrap_fresh_admin(
                db,
                email=str(payload.email),
                name=payload.name,
                password=payload.password.get_secret_value(),
            )
    except (FreshAdminBootstrapError, ValueError) as exc:
        print(f"Fresh admin bootstrap refused: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print("Fresh admin bootstrap failed safely.", file=sys.stderr)
        return 1

    outcome = "created" if result.created else "verified"
    print(f"Fresh admin bootstrap {outcome} the sole administrator account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
