"""Keep fresh-admin bootstrap pinned to the real Alembic head."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.modules.auth.fresh_admin_bootstrap import _EXPECTED_ALEMBIC_HEAD

_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


def test_expected_alembic_head_matches_script_directory() -> None:
    script = ScriptDirectory.from_config(Config(str(_ALEMBIC_INI)))
    assert _EXPECTED_ALEMBIC_HEAD == script.get_current_head()
