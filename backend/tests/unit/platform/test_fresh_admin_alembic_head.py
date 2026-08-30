"""Keep fresh-admin bootstrap pinned to the real Alembic head."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.modules.auth.fresh_admin_bootstrap import (
    _DROPPED_LEGACY_TABLES,
    _EXPECTED_ALEMBIC_HEAD,
)

_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


def test_expected_alembic_head_matches_script_directory() -> None:
    script = ScriptDirectory.from_config(Config(str(_ALEMBIC_INI)))
    assert _EXPECTED_ALEMBIC_HEAD == script.get_current_head()


def test_dropped_legacy_tables_are_still_registered_on_orm() -> None:
    from app import models as _models  # noqa: F401
    from app.core.database import Base

    assert _DROPPED_LEGACY_TABLES <= set(Base.metadata.tables)
